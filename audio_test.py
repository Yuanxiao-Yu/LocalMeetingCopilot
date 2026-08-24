from __future__ import annotations

import platform
import queue
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TextIO

import numpy as np
import sounddevice as sd

from audio_engine import (
    WindowsLoopbackCapture,
    _resample_audio,
    _select_remote_input_device,
    _to_mono_float32,
    create_vad_segmenter,
)
from config import AppConfig, load_config


@dataclass
class AudioProbeStats:
    label: str
    vad_backend: str
    input_sample_rate: int
    target_sample_rate: int
    chunks: int = 0
    rms: float = 0.0
    peak: float = 0.0
    speech_starts: int = 0
    completed_segments: int = 0
    completed_seconds: float = 0.0
    in_speech: bool = False
    last_status: str = ""
    first_chunk_at: float | None = None
    last_chunk_at: float | None = None

    def accept_chunk(self, chunk: object, vad: Any, now: float | None = None) -> None:
        timestamp = time.monotonic() if now is None else now
        audio = _to_mono_float32(chunk)
        if self.input_sample_rate != self.target_sample_rate:
            audio = _resample_audio(audio, self.input_sample_rate, self.target_sample_rate)

        started, completed, rms = vad.accept(audio)
        self.chunks += 1
        self.rms = rms
        self.peak = max(self.peak, rms)
        self.in_speech = bool(getattr(vad, "in_speech", False))
        self.first_chunk_at = self.first_chunk_at or timestamp
        self.last_chunk_at = timestamp
        if started:
            self.speech_starts += 1
        if completed is not None:
            self.completed_segments += 1
            self.completed_seconds += max(0.0, completed.end_time - completed.start_time)
            self.in_speech = bool(getattr(vad, "in_speech", False))

    def record_status(self, status: object) -> None:
        text = str(status).strip()
        if text:
            self.last_status = text

    def record_flush(self, completed: object | None) -> None:
        if completed is None:
            return
        self.completed_segments += 1
        start_time = float(getattr(completed, "start_time", 0.0))
        end_time = float(getattr(completed, "end_time", 0.0))
        self.completed_seconds += max(0.0, end_time - start_time)


@dataclass
class AudioProbe:
    key: str
    label: str
    device_label: str
    event_queue: queue.Queue[tuple[str, object]]
    vad: Any
    stats: AudioProbeStats
    stop: Callable[[], None]


def run_audio_test(
    config: AppConfig | None = None,
    profile: str | None = None,
    preset: str | None = None,
    style: str | None = None,
    duration_seconds: float = 12.0,
    output: TextIO | None = None,
) -> int:
    cfg = config or load_config(profile=profile, preset=preset, translation_style=style)
    out = output or sys.stdout
    duration = max(0.5, float(duration_seconds))
    probes = _start_enabled_probes(cfg, out)
    if not probes:
        print("No audio tracks enabled or available for testing.", file=out)
        return 1

    print("", file=out)
    print(f"Audio test running for {duration:0.1f}s. Speak into the mic and play meeting audio.", file=out)
    print("Press Ctrl+C to stop early.", file=out)

    deadline = time.monotonic() + duration
    last_print = 0.0
    try:
        while time.monotonic() < deadline:
            for probe in probes:
                drain_probe(probe)
            now = time.monotonic()
            if now - last_print >= 0.5:
                remaining = max(0.0, deadline - now)
                print(f"\nRemaining {remaining:0.1f}s", file=out)
                for probe in probes:
                    print(format_probe_status(probe, now=now), file=out)
                last_print = now
            time.sleep(0.05)
    except KeyboardInterrupt:
        print("\nAudio test stopped by user.", file=out)
    finally:
        for probe in probes:
            drain_probe(probe)
            probe.stats.record_flush(probe.vad.flush())
            try:
                probe.stop()
            except Exception as exc:
                probe.stats.record_status(f"stop warning: {exc}")

    print("", file=out)
    print("Audio test summary", file=out)
    for probe in probes:
        print(format_probe_summary(probe), file=out)
    if not any(probe.stats.chunks for probe in probes):
        print("Warning: no audio chunks were received. Check OS permissions and device indexes.", file=out)
    return 0


def drain_probe(probe: AudioProbe) -> None:
    while True:
        try:
            kind, payload = probe.event_queue.get_nowait()
        except queue.Empty:
            break
        if kind == "status":
            probe.stats.record_status(payload)
        elif kind == "chunk":
            probe.stats.accept_chunk(payload, probe.vad)


def format_probe_status(probe: AudioProbe, now: float | None = None) -> str:
    timestamp = time.monotonic() if now is None else now
    stats = probe.stats
    age = "never" if stats.last_chunk_at is None else f"{timestamp - stats.last_chunk_at:0.1f}s"
    state = "speech" if stats.in_speech else "idle"
    status = f" status={stats.last_status}" if stats.last_status else ""
    return (
        f"{probe.label}: {state:6} rms={stats.rms:0.4f} peak={stats.peak:0.4f} "
        f"{level_bar(stats.rms)} chunks={stats.chunks} starts={stats.speech_starts} "
        f"cuts={stats.completed_segments} last={age}{status}"
    )


def format_probe_summary(probe: AudioProbe) -> str:
    stats = probe.stats
    return (
        f"- {probe.label} [{probe.device_label}] VAD={stats.vad_backend}, "
        f"chunks={stats.chunks}, peak={stats.peak:0.4f}, "
        f"speech_starts={stats.speech_starts}, cuts={stats.completed_segments}, "
        f"speech_seconds={stats.completed_seconds:0.2f}"
    )


def level_bar(rms: float, width: int = 18, reference: float = 0.06) -> str:
    safe_reference = max(reference, 0.0001)
    filled = min(width, max(0, int((rms / safe_reference) * width)))
    return "[" + "#" * filled + "." * (width - filled) + "]"


def _start_enabled_probes(config: AppConfig, output: TextIO) -> list[AudioProbe]:
    probes: list[AudioProbe] = []
    if config.capture_mic_enabled:
        _try_append_probe(probes, lambda: _start_mic_probe(config), output)
    else:
        print("Mic track disabled by config/CLI.", file=output)

    if config.capture_remote_enabled:
        system_name = platform.system().lower()
        if system_name == "windows":
            _try_append_probe(probes, lambda: _start_windows_loopback_probe(config), output)
        elif system_name == "darwin":
            _try_append_probe(probes, lambda: _start_macos_remote_probe(config), output)
        else:
            print("Remote track test is only implemented for Windows and macOS.", file=output)
    else:
        print("Remote track disabled by config/CLI.", file=output)
    return probes


def _try_append_probe(
    probes: list[AudioProbe],
    factory: Callable[[], AudioProbe],
    output: TextIO,
) -> None:
    try:
        probe = factory()
    except Exception as exc:
        print(f"Audio probe unavailable: {exc}", file=output)
        return
    probes.append(probe)
    print(f"Started {probe.label}: {probe.device_label}", file=output)


def _start_mic_probe(config: AppConfig) -> AudioProbe:
    return _start_sounddevice_probe(
        config=config,
        key="mic",
        label="[Me] Mic",
        device_index=config.mic_device_index,
        channels=1,
    )


def _start_macos_remote_probe(config: AppConfig) -> AudioProbe:
    selected = _select_remote_input_device(config)
    if selected is None:
        raise RuntimeError(
            "no remote input candidate; set LMC_REMOTE_DEVICE_INDEX to BlackHole/Teams/Zoom"
        )
    channels = max(1, min(2, int(selected.get("max_input_channels", 1))))
    return _start_sounddevice_probe(
        config=config,
        key="remote",
        label="[Remote] Input",
        device_index=int(selected["index"]),
        channels=channels,
    )


def _start_sounddevice_probe(
    *,
    config: AppConfig,
    key: str,
    label: str,
    device_index: int | None,
    channels: int,
) -> AudioProbe:
    event_queue: queue.Queue[tuple[str, object]] = queue.Queue()
    device_info = _query_input_device(device_index)
    device_label = _device_label(device_info, device_index)
    stream, sample_rate = _open_sounddevice_stream(
        config=config,
        event_queue=event_queue,
        device_index=device_index,
        channels=channels,
        fallback_rate=int(float(device_info.get("default_samplerate", config.audio_sample_rate))),
    )
    vad = create_vad_segmenter(config)
    stats = AudioProbeStats(
        label=label,
        vad_backend=str(getattr(vad, "backend_name", "unknown")),
        input_sample_rate=sample_rate,
        target_sample_rate=config.audio_sample_rate,
    )
    return AudioProbe(
        key=key,
        label=label,
        device_label=f"{device_label} @ {sample_rate} Hz",
        event_queue=event_queue,
        vad=vad,
        stats=stats,
        stop=lambda: _stop_sounddevice_stream(stream),
    )


def _start_windows_loopback_probe(config: AppConfig) -> AudioProbe:
    event_queue: queue.Queue[tuple[str, object]] = queue.Queue()
    capture = WindowsLoopbackCapture(config, event_queue)
    capture.start()
    vad = create_vad_segmenter(config)
    stats = AudioProbeStats(
        label="[Remote] WASAPI",
        vad_backend=str(getattr(vad, "backend_name", "unknown")),
        input_sample_rate=capture.sample_rate,
        target_sample_rate=config.audio_sample_rate,
    )
    return AudioProbe(
        key="remote",
        label="[Remote] WASAPI",
        device_label=f"{capture.device_name} @ {capture.sample_rate} Hz",
        event_queue=event_queue,
        vad=vad,
        stats=stats,
        stop=capture.stop,
    )


def _open_sounddevice_stream(
    *,
    config: AppConfig,
    event_queue: queue.Queue[tuple[str, object]],
    device_index: int | None,
    channels: int,
    fallback_rate: int,
) -> tuple[sd.InputStream, int]:
    try:
        return (
            _create_sounddevice_stream(
                event_queue=event_queue,
                sample_rate=config.audio_sample_rate,
                block_ms=config.audio_chunk_ms,
                device_index=device_index,
                channels=channels,
            ),
            config.audio_sample_rate,
        )
    except Exception as preferred_exc:
        if fallback_rate == config.audio_sample_rate:
            raise
        try:
            return (
                _create_sounddevice_stream(
                    event_queue=event_queue,
                    sample_rate=fallback_rate,
                    block_ms=config.audio_chunk_ms,
                    device_index=device_index,
                    channels=channels,
                ),
                fallback_rate,
            )
        except Exception as fallback_exc:
            raise RuntimeError(
                f"preferred {config.audio_sample_rate} Hz failed: {preferred_exc}; "
                f"fallback {fallback_rate} Hz failed: {fallback_exc}"
            ) from fallback_exc


def _create_sounddevice_stream(
    *,
    event_queue: queue.Queue[tuple[str, object]],
    sample_rate: int,
    block_ms: int,
    device_index: int | None,
    channels: int,
) -> sd.InputStream:
    blocksize = max(1, int(sample_rate * block_ms / 1000))

    def callback(indata, _frames, _time_info, status) -> None:  # noqa: ANN001
        if status:
            event_queue.put(("status", str(status)))
        event_queue.put(("chunk", np.asarray(indata, dtype=np.float32).copy()))

    stream = sd.InputStream(
        samplerate=sample_rate,
        blocksize=blocksize,
        channels=channels,
        dtype="float32",
        device=device_index,
        callback=callback,
    )
    stream.start()
    return stream


def _query_input_device(device_index: int | None) -> dict[str, object]:
    return dict(sd.query_devices(device_index, "input"))


def _device_label(device: dict[str, object], device_index: int | None) -> str:
    index = "default" if device_index is None else str(device_index)
    name = str(device.get("name") or "unknown input")
    return f"[{index}] {name}"


def _stop_sounddevice_stream(stream: sd.InputStream) -> None:
    stream.stop()
    stream.close()
