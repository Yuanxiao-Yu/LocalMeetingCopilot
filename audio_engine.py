from __future__ import annotations

import platform
import queue
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime

import numpy as np
import sounddevice as sd
from PySide6.QtCore import QObject, QTimer, Signal
from scipy.signal import resample_poly

from config import AppConfig, load_config
from meeting_types import TranscriptDraft


@dataclass(slots=True)
class MockLine:
    speaker: str
    text: str
    language_code: str
    pause_ms: int = 1800


MOCK_SCRIPT: tuple[MockLine, ...] = (
    MockLine(
        "Remote Participant",
        "Wir sollten die Migration erst dann starten, wenn die Datenpipeline stabil ist.",
        "de",
    ),
    MockLine(
        "Me",
        "Ich kann die Datenqualität heute Abend prüfen und morgen ein kurzes Update geben.",
        "de",
    ),
    MockLine(
        "Remote Participant",
        "Could you also check whether the new dashboard still uses the old customer table?",
        "en",
    ),
    MockLine(
        "Remote Participant",
        "Wenn wir das bis Freitag klären, können wir nächste Woche mit dem Rollout beginnen.",
        "de",
    ),
)


@dataclass(slots=True)
class CompletedSpeech:
    audio_data: np.ndarray
    start_time: float
    end_time: float


class EnergyVADSegmenter:
    backend_name = "energy"

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.sample_rate = config.audio_sample_rate
        self.threshold = config.vad_energy_threshold
        self.min_speech_samples = int(config.vad_min_speech_ms / 1000 * self.sample_rate)
        self.silence_samples = int(config.vad_silence_ms / 1000 * self.sample_rate)
        self.pre_roll_chunks = max(
            1,
            int(config.vad_pre_roll_ms / max(config.audio_chunk_ms, 1)),
        )
        self.max_samples = int(config.vad_max_sentence_seconds * self.sample_rate)
        self._pre_roll: deque[np.ndarray] = deque(maxlen=self.pre_roll_chunks)
        self._speech_chunks: list[np.ndarray] = []
        self._speech_samples = 0
        self._silent_samples = 0
        self._current_sample = 0
        self._speech_start_sample = 0
        self.in_speech = False

    def reset(self) -> None:
        self._pre_roll.clear()
        self._speech_chunks.clear()
        self._speech_samples = 0
        self._silent_samples = 0
        self._current_sample = 0
        self._speech_start_sample = 0
        self.in_speech = False

    def accept(self, chunk: np.ndarray) -> tuple[bool, CompletedSpeech | None, float]:
        mono = _to_mono_float32(chunk)
        rms = _rms(mono)
        is_voice = rms >= self.threshold
        started = False
        completed: CompletedSpeech | None = None

        if is_voice and not self.in_speech:
            self.in_speech = True
            started = True
            pre_roll_samples = sum(part.size for part in self._pre_roll)
            self._speech_start_sample = max(0, self._current_sample - pre_roll_samples)
            self._speech_chunks = [part.copy() for part in self._pre_roll]
            self._speech_samples = pre_roll_samples
            self._silent_samples = 0

        if self.in_speech:
            self._speech_chunks.append(mono)
            self._speech_samples += mono.size
            self._silent_samples = self._silent_samples + mono.size if not is_voice else 0

            silence_reached = self._silent_samples >= self.silence_samples
            max_reached = self._speech_samples >= self.max_samples
            if silence_reached or max_reached:
                completed = self._complete_sentence()
        else:
            self._pre_roll.append(mono)

        self._current_sample += mono.size
        return started, completed, rms

    def flush(self) -> CompletedSpeech | None:
        if not self.in_speech or self._speech_samples < self.min_speech_samples:
            self.reset()
            return None
        return self._complete_sentence()

    def preview_audio(self) -> CompletedSpeech | None:
        if not self.in_speech or self._speech_samples < self.min_speech_samples or not self._speech_chunks:
            return None
        audio = np.concatenate(self._speech_chunks).astype(np.float32, copy=False)
        start = self._speech_start_sample / self.sample_rate
        end = (self._speech_start_sample + audio.size) / self.sample_rate
        return CompletedSpeech(audio_data=audio, start_time=start, end_time=end)

    def _complete_sentence(self) -> CompletedSpeech | None:
        audio = np.concatenate(self._speech_chunks).astype(np.float32, copy=False)
        start = self._speech_start_sample / self.sample_rate
        end = (self._speech_start_sample + audio.size) / self.sample_rate
        self._speech_chunks = []
        self._speech_samples = 0
        self._silent_samples = 0
        self.in_speech = False
        self._pre_roll.clear()
        if audio.size < self.min_speech_samples:
            return None
        return CompletedSpeech(audio_data=audio, start_time=start, end_time=end)


class SileroVADSegmenter:
    backend_name = "silero"

    def __init__(self, config: AppConfig) -> None:
        if config.audio_sample_rate != 16_000:
            raise RuntimeError("Silero VAD requires 16000 Hz audio")

        try:
            from silero_vad import VADIterator, load_silero_vad  # type: ignore[import-not-found]
        except Exception as exc:
            raise RuntimeError("silero-vad is not installed") from exc

        self.config = config
        self.sample_rate = config.audio_sample_rate
        self.frame_samples = 512
        self.min_speech_samples = int(config.vad_min_speech_ms / 1000 * self.sample_rate)
        self.max_samples = int(config.vad_max_sentence_seconds * self.sample_rate)
        self.pre_roll_chunks = max(1, int(config.vad_pre_roll_ms / 32))
        self._model = load_silero_vad(onnx=True)
        self._iterator = VADIterator(
            self._model,
            threshold=config.silero_threshold,
            sampling_rate=self.sample_rate,
            min_silence_duration_ms=config.vad_silence_ms,
            speech_pad_ms=config.vad_pre_roll_ms,
        )
        self._pending = np.zeros(0, dtype=np.float32)
        self._pre_roll: deque[np.ndarray] = deque(maxlen=self.pre_roll_chunks)
        self._speech_chunks: list[np.ndarray] = []
        self._speech_samples = 0
        self._current_sample = 0
        self._speech_start_sample = 0
        self.in_speech = False

    def reset(self) -> None:
        self._iterator.reset_states()
        self._pending = np.zeros(0, dtype=np.float32)
        self._pre_roll.clear()
        self._speech_chunks.clear()
        self._speech_samples = 0
        self._current_sample = 0
        self._speech_start_sample = 0
        self.in_speech = False

    def accept(self, chunk: np.ndarray) -> tuple[bool, CompletedSpeech | None, float]:
        mono = _to_mono_float32(chunk)
        if self._pending.size:
            mono = np.concatenate([self._pending, mono]).astype(np.float32, copy=False)
            self._pending = np.zeros(0, dtype=np.float32)

        started = False
        completed: CompletedSpeech | None = None
        max_rms = _rms(mono)
        usable = (mono.size // self.frame_samples) * self.frame_samples
        if usable < mono.size:
            self._pending = mono[usable:].copy()

        for offset in range(0, usable, self.frame_samples):
            frame = np.ascontiguousarray(mono[offset : offset + self.frame_samples])
            max_rms = max(max_rms, _rms(frame))
            event = self._iterator(frame)
            if isinstance(event, dict) and "start" in event and not self.in_speech:
                self.in_speech = True
                started = True
                pre_roll_samples = sum(part.size for part in self._pre_roll)
                self._speech_start_sample = max(0, self._current_sample - pre_roll_samples)
                self._speech_chunks = [part.copy() for part in self._pre_roll]
                self._speech_samples = pre_roll_samples

            if self.in_speech:
                self._speech_chunks.append(frame)
                self._speech_samples += frame.size

            if isinstance(event, dict) and "end" in event and self.in_speech:
                completed = self._complete_sentence()
            elif self.in_speech and self._speech_samples >= self.max_samples:
                completed = self._complete_sentence()
                self._iterator.reset_states()

            if not completed and not self.in_speech:
                self._pre_roll.append(frame)
            self._current_sample += frame.size
            if completed:
                break

        return started, completed, max_rms

    def flush(self) -> CompletedSpeech | None:
        if self._pending.size and self.in_speech:
            self._speech_chunks.append(self._pending.copy())
            self._speech_samples += self._pending.size
            self._current_sample += self._pending.size
        self._pending = np.zeros(0, dtype=np.float32)
        if not self.in_speech or self._speech_samples < self.min_speech_samples:
            self.reset()
            return None
        return self._complete_sentence()

    def preview_audio(self) -> CompletedSpeech | None:
        if not self.in_speech or self._speech_samples < self.min_speech_samples or not self._speech_chunks:
            return None
        audio = np.concatenate(self._speech_chunks).astype(np.float32, copy=False)
        start = self._speech_start_sample / self.sample_rate
        end = (self._speech_start_sample + audio.size) / self.sample_rate
        return CompletedSpeech(audio_data=audio, start_time=start, end_time=end)

    def _complete_sentence(self) -> CompletedSpeech | None:
        audio = np.concatenate(self._speech_chunks).astype(np.float32, copy=False)
        start = self._speech_start_sample / self.sample_rate
        end = (self._speech_start_sample + audio.size) / self.sample_rate
        self._speech_chunks = []
        self._speech_samples = 0
        self.in_speech = False
        self._pre_roll.clear()
        if audio.size < self.min_speech_samples:
            return None
        return CompletedSpeech(audio_data=audio, start_time=start, end_time=end)


def create_vad_segmenter(config: AppConfig) -> EnergyVADSegmenter | SileroVADSegmenter:
    if config.vad_mode in {"auto", "silero"}:
        try:
            return SileroVADSegmenter(config)
        except Exception:
            pass
    return EnergyVADSegmenter(config)


class WindowsLoopbackCapture:
    def __init__(self, config: AppConfig, event_queue: queue.Queue[tuple[str, object]]) -> None:
        self.config = config
        self.event_queue = event_queue
        self.sample_rate = config.audio_sample_rate
        self.channels = 2
        self.device_name = "default WASAPI loopback"
        self._blocksize = int(self.sample_rate * config.audio_chunk_ms / 1000)
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._pyaudio_module: object | None = None
        self._pa: object | None = None
        self._stream: object | None = None
        self._sample_dtype = np.float32

    def start(self) -> None:
        if platform.system().lower() != "windows":
            raise RuntimeError("WASAPI loopback capture is only available on Windows")

        try:
            import pyaudiowpatch as pyaudio  # type: ignore[import-not-found]
        except Exception as exc:
            raise RuntimeError("pyaudiowpatch is not installed") from exc

        self._pyaudio_module = pyaudio
        self._pa = pyaudio.PyAudio()
        device = _select_wasapi_loopback_device(self._pa, pyaudio, self.config.loopback_device_index)
        self.sample_rate = int(float(device.get("defaultSampleRate", self.config.audio_sample_rate)))
        self.channels = max(
            1,
            int(device.get("maxInputChannels") or device.get("maxOutputChannels") or 2),
        )
        self.device_name = str(device.get("name") or "WASAPI loopback")
        self._blocksize = max(1, int(self.sample_rate * self.config.audio_chunk_ms / 1000))
        self._stream = self._open_stream(pyaudio, int(device["index"]))
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._read_loop,
            name="LocalMeetingCopilotLoopback",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=1.5)
        self._thread = None

        if self._stream is not None:
            try:
                if hasattr(self._stream, "stop_stream"):
                    self._stream.stop_stream()
                if hasattr(self._stream, "close"):
                    self._stream.close()
            finally:
                self._stream = None

        if self._pa is not None:
            try:
                if hasattr(self._pa, "terminate"):
                    self._pa.terminate()
            finally:
                self._pa = None

    def _open_stream(self, pyaudio: object, device_index: int) -> object:
        if self._pa is None:
            raise RuntimeError("PyAudio is not initialised")

        attempts = (
            (pyaudio.paFloat32, np.float32),
            (pyaudio.paInt16, np.int16),
        )
        last_exc: Exception | None = None
        for audio_format, dtype in attempts:
            try:
                stream = self._pa.open(
                    format=audio_format,
                    channels=self.channels,
                    rate=self.sample_rate,
                    input=True,
                    input_device_index=device_index,
                    frames_per_buffer=self._blocksize,
                )
                self._sample_dtype = dtype
                return stream
            except Exception as exc:
                last_exc = exc

        raise RuntimeError(f"Unable to open WASAPI loopback stream: {last_exc}")

    def _read_loop(self) -> None:
        if self._stream is None:
            return

        while not self._stop_event.is_set():
            try:
                raw = self._stream.read(self._blocksize, exception_on_overflow=False)
            except Exception as exc:
                if not self._stop_event.is_set():
                    self.event_queue.put(("status", f"Loopback read failed: {exc}"))
                break

            samples = np.frombuffer(raw, dtype=self._sample_dtype)
            if samples.size == 0:
                continue
            if self._sample_dtype == np.int16:
                audio = samples.astype(np.float32) / 32768.0
            else:
                audio = samples.astype(np.float32, copy=False)

            if self.channels > 1:
                usable = (audio.size // self.channels) * self.channels
                if usable == 0:
                    continue
                audio = audio[:usable].reshape(-1, self.channels).mean(axis=1)
            self.event_queue.put(("chunk", np.ascontiguousarray(audio)))


class AudioEngine(QObject):
    mic_chunk_received = Signal(object)
    loopback_chunk_received = Signal(object)
    speech_started = Signal(str)
    partial_speech_ready = Signal(object)
    sentence_completed = Signal(object)
    audio_level_changed = Signal(str, float, bool)

    preview_updated = Signal(str, str)
    status_changed = Signal(str)
    finished = Signal()

    def __init__(self, config: AppConfig | None = None, mode: str = "mock") -> None:
        super().__init__()
        self.config = config or load_config()
        self.mode = mode
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._emit_next_mock_line)
        self._mic_timer = QTimer(self)
        self._mic_timer.setInterval(40)
        self._mic_timer.timeout.connect(self._drain_mic_queue)
        self._loopback_timer = QTimer(self)
        self._loopback_timer.setInterval(40)
        self._loopback_timer.timeout.connect(self._drain_loopback_queue)
        self._script_index = 0
        self._started_at = time.monotonic()
        self._running = False
        self._mic_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self._loopback_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self._mic_stream: sd.InputStream | None = None
        self._remote_stream: sd.InputStream | None = None
        self._loopback_capture: WindowsLoopbackCapture | None = None
        self._mic_vad = create_vad_segmenter(self.config)
        self._loopback_vad = create_vad_segmenter(self.config)
        self._last_partial_emit_at: dict[str, float] = {"mic": 0.0, "loopback": 0.0}
        self._mic_input_sample_rate = self.config.audio_sample_rate
        self._loopback_input_sample_rate = self.config.audio_sample_rate
        self._visual_tracker: object | None = None

    def start(self) -> None:
        self._running = True
        if self.mode == "mock":
            self._script_index = 0
            self._started_at = time.monotonic()
            self.status_changed.emit("Mock meeting started")
            self._emit_next_mock_line()
            return

        if self.mode == "mic":
            self._start_mic_capture()
            return

        if self.mode == "mac_live" and platform.system().lower() != "darwin":
            self.status_changed.emit("macOS live mode is only available on macOS.")
            self.finished.emit()
            return

        if self.mode == "mac_live":
            self._start_macos_live_capture()
            return

        if self.mode == "live" and platform.system().lower() != "windows":
            self.status_changed.emit("Live loopback is Windows-only. Use --mock, --mic, or --wav on macOS.")
            self.finished.emit()
            return

        if self.mode == "live":
            self._start_live_capture()
            return

        self.status_changed.emit(f"Unknown audio mode: {self.mode}")
        self.finished.emit()

    def stop(self) -> None:
        self._running = False
        self._timer.stop()
        self._mic_timer.stop()
        self._loopback_timer.stop()
        self._stop_mic_stream()
        self._stop_loopback_capture()
        self.status_changed.emit("Audio source stopped")
        self.finished.emit()

    def _emit_next_mock_line(self) -> None:
        if not self._running:
            return
        if self._script_index >= len(MOCK_SCRIPT):
            self._running = False
            self._timer.stop()
            self.status_changed.emit("Mock meeting finished")
            self.finished.emit()
            return

        line = MOCK_SCRIPT[self._script_index]
        elapsed = time.monotonic() - self._started_at
        track_type = "mic" if line.speaker == "Me" else "loopback"
        fake_audio = _fake_audio_chunk(self.config.audio_sample_rate)

        if track_type == "mic":
            self.mic_chunk_received.emit(fake_audio)
        else:
            self.loopback_chunk_received.emit(fake_audio)
        self.speech_started.emit(track_type)

        words = line.text.split()
        preview = ""
        for word in words:
            preview = f"{preview} {word}".strip()
            self.preview_updated.emit(line.speaker, preview)

        self.sentence_completed.emit(
            TranscriptDraft(
                speaker=line.speaker,
                text=line.text,
                language_code=line.language_code,
                track_type=track_type,
                start_time=elapsed,
                end_time=elapsed + 2.0,
            )
        )
        self._script_index += 1
        self._timer.start(line.pause_ms)

    def _start_live_capture(self) -> None:
        self._started_at = time.monotonic()
        mic_started = (
            self._start_mic_capture(finish_on_failure=False, reset_clock=False)
            if self.config.capture_mic_enabled
            else False
        )
        loopback_started = (
            self._start_loopback_capture() if self.config.capture_remote_enabled else False
        )

        if not mic_started and not loopback_started:
            self.status_changed.emit("Live capture failed: no microphone or loopback source available")
            self.finished.emit()
            return

        if mic_started and loopback_started:
            self.status_changed.emit("Live capture started: mic + WASAPI loopback")
        elif loopback_started:
            self.status_changed.emit("Live capture started: WASAPI loopback only")
        else:
            self.status_changed.emit("Live capture started: microphone only; loopback unavailable")

    def _start_macos_live_capture(self) -> None:
        self._started_at = time.monotonic()
        mic_started = (
            self._start_mic_capture(finish_on_failure=False, reset_clock=False)
            if self.config.capture_mic_enabled
            else False
        )
        remote_started = (
            self._start_remote_input_capture() if self.config.capture_remote_enabled else False
        )

        if not mic_started and not remote_started:
            self.status_changed.emit("macOS live failed: no microphone or remote input source available")
            self.finished.emit()
            return

        if mic_started and remote_started:
            self.status_changed.emit("macOS live started: mic + remote input")
        elif remote_started:
            self.status_changed.emit("macOS live started: remote input only")
        else:
            self.status_changed.emit("macOS live started: microphone only; set LMC_REMOTE_DEVICE_INDEX for remote")

    def _start_mic_capture(
        self,
        *,
        finish_on_failure: bool = True,
        reset_clock: bool = True,
    ) -> bool:
        self._mic_vad.reset()
        if reset_clock:
            self._started_at = time.monotonic()
        self._mic_input_sample_rate = self.config.audio_sample_rate
        try:
            self._mic_stream = self._open_mic_stream(self.config.audio_sample_rate)
        except Exception as preferred_exc:
            try:
                device_info = sd.query_devices(self.config.mic_device_index, "input")
                fallback_rate = int(device_info["default_samplerate"])
                self._mic_stream = self._open_mic_stream(fallback_rate)
                self.status_changed.emit(
                    f"Mic opened at {fallback_rate} Hz; resampling to {self.config.audio_sample_rate} Hz"
                )
            except Exception as fallback_exc:
                self.status_changed.emit(
                    f"Microphone unavailable: {preferred_exc}; fallback failed: {fallback_exc}"
                )
                if finish_on_failure:
                    self.finished.emit()
                return False

        device = (
            "default microphone"
            if self.config.mic_device_index is None
            else f"device {self.config.mic_device_index}"
        )
        if self._mic_input_sample_rate == self.config.audio_sample_rate:
            self.status_changed.emit(f"Mic capture started: {device} | VAD: {self._mic_vad.backend_name}")
        self.preview_updated.emit("Me", "Listening...")
        self._mic_timer.start()
        return True

    def _open_mic_stream(self, sample_rate: int) -> sd.InputStream:
        self._mic_input_sample_rate = sample_rate
        blocksize = int(sample_rate * self.config.audio_chunk_ms / 1000)
        stream = sd.InputStream(
            samplerate=sample_rate,
            blocksize=blocksize,
            channels=1,
            dtype="float32",
            device=self.config.mic_device_index,
            callback=self._on_mic_audio,
        )
        stream.start()
        return stream

    def _stop_mic_stream(self) -> None:
        if self._mic_stream is None:
            return
        try:
            self._mic_stream.stop()
            self._mic_stream.close()
        except Exception as exc:
            self.status_changed.emit(f"Microphone stop warning: {exc}")
        finally:
            self._mic_stream = None
            self._drain_mic_queue(force=True)
            completed = self._mic_vad.flush()
            if completed:
                self._emit_completed_mic_sentence(completed)

    def _on_mic_audio(self, indata, frames, time_info, status) -> None:  # noqa: ANN001
        if status:
            self._mic_queue.put(("status", str(status)))
        self._mic_queue.put(("chunk", np.asarray(indata, dtype=np.float32).copy()))

    def _drain_mic_queue(self, *, force: bool = False) -> None:
        if not self._running and not force:
            return
        while True:
            try:
                kind, payload = self._mic_queue.get_nowait()
            except queue.Empty:
                break

            if kind == "status":
                self.status_changed.emit(f"Mic status: {payload}")
                continue

            chunk = self._normalise_mic_chunk(payload)
            self.mic_chunk_received.emit(chunk)
            started, completed, rms = self._mic_vad.accept(chunk)
            self.audio_level_changed.emit("mic", rms, self._mic_vad.in_speech)
            if started:
                self.speech_started.emit("mic")
                self.preview_updated.emit("Me", "Listening...")
            if self._mic_vad.in_speech:
                self._maybe_emit_partial_sentence("mic", "Me", self._mic_vad)
                if not self.config.partial_subtitles_enabled:
                    self.preview_updated.emit("Me", f"Listening... level {rms:0.3f}")
            if completed:
                self._emit_completed_mic_sentence(completed)

    def _normalise_mic_chunk(self, payload: object) -> np.ndarray:
        chunk = _to_mono_float32(payload)
        if self._mic_input_sample_rate == self.config.audio_sample_rate:
            return chunk
        return _resample_audio(chunk, self._mic_input_sample_rate, self.config.audio_sample_rate)

    def _start_loopback_capture(self) -> bool:
        self._loopback_vad.reset()
        self._loopback_input_sample_rate = self.config.audio_sample_rate
        self._loopback_capture = WindowsLoopbackCapture(self.config, self._loopback_queue)
        try:
            self._loopback_capture.start()
        except Exception as exc:
            self.status_changed.emit(f"WASAPI loopback unavailable: {exc}")
            self._loopback_capture = None
            return False

        self._loopback_input_sample_rate = self._loopback_capture.sample_rate
        self.status_changed.emit(
            f"Loopback capture started: {self._loopback_capture.device_name} | VAD: {self._loopback_vad.backend_name}"
        )
        self.preview_updated.emit("Remote Participant", "Listening...")
        self._loopback_timer.start()
        return True

    def _start_remote_input_capture(self) -> bool:
        self._loopback_vad.reset()
        selected = _select_remote_input_device(self.config)
        if selected is None:
            self.status_changed.emit(
                "Remote input unavailable: set LMC_REMOTE_DEVICE_INDEX to a BlackHole/Teams/Zoom audio input"
            )
            return False

        device_index = int(selected["index"])
        self._loopback_input_sample_rate = self.config.audio_sample_rate
        try:
            self._remote_stream = self._open_remote_stream(device_index, self.config.audio_sample_rate)
        except Exception as preferred_exc:
            try:
                fallback_rate = int(float(selected["default_samplerate"]))
                self._remote_stream = self._open_remote_stream(device_index, fallback_rate)
                self.status_changed.emit(
                    f"Remote input opened at {fallback_rate} Hz; resampling to {self.config.audio_sample_rate} Hz"
                )
            except Exception as fallback_exc:
                self.status_changed.emit(
                    f"Remote input unavailable: {preferred_exc}; fallback failed: {fallback_exc}"
                )
                self._remote_stream = None
                return False

        self.status_changed.emit(
            f"Remote input capture started: [{device_index}] {selected['name']} | VAD: {self._loopback_vad.backend_name}"
        )
        self.preview_updated.emit("Remote Participant", "Listening...")
        self._loopback_timer.start()
        return True

    def _open_remote_stream(self, device_index: int, sample_rate: int) -> sd.InputStream:
        self._loopback_input_sample_rate = sample_rate
        device_info = dict(sd.query_devices(device_index))
        channels = max(1, min(2, int(device_info.get("max_input_channels", 1))))
        blocksize = int(sample_rate * self.config.audio_chunk_ms / 1000)
        stream = sd.InputStream(
            samplerate=sample_rate,
            blocksize=blocksize,
            channels=channels,
            dtype="float32",
            device=device_index,
            callback=self._on_loopback_audio,
        )
        stream.start()
        return stream

    def _stop_loopback_capture(self) -> None:
        if self._loopback_capture is not None:
            try:
                self._loopback_capture.stop()
            except Exception as exc:
                self.status_changed.emit(f"Loopback stop warning: {exc}")
            finally:
                self._loopback_capture = None

        if self._remote_stream is not None:
            try:
                self._remote_stream.stop()
                self._remote_stream.close()
            except Exception as exc:
                self.status_changed.emit(f"Remote input stop warning: {exc}")
            finally:
                self._remote_stream = None

        self._drain_loopback_queue(force=True)
        completed = self._loopback_vad.flush()
        if completed:
            self._emit_completed_loopback_sentence(completed)

    def _on_loopback_audio(self, indata, frames, time_info, status) -> None:  # noqa: ANN001
        if status:
            self._loopback_queue.put(("status", f"Remote input status: {status}"))
        self._loopback_queue.put(("chunk", np.asarray(indata, dtype=np.float32).copy()))

    def _drain_loopback_queue(self, *, force: bool = False) -> None:
        if not self._running and not force:
            return
        while True:
            try:
                kind, payload = self._loopback_queue.get_nowait()
            except queue.Empty:
                break

            if kind == "status":
                self.status_changed.emit(str(payload))
                continue

            chunk = self._normalise_loopback_chunk(payload)
            self.loopback_chunk_received.emit(chunk)
            started, completed, rms = self._loopback_vad.accept(chunk)
            self.audio_level_changed.emit("loopback", rms, self._loopback_vad.in_speech)
            if started:
                self.speech_started.emit("loopback")
                self.preview_updated.emit("Remote Participant", "Listening...")
            if self._loopback_vad.in_speech:
                self._maybe_emit_partial_sentence("loopback", "Remote Participant", self._loopback_vad)
                if not self.config.partial_subtitles_enabled:
                    self.preview_updated.emit("Remote Participant", f"Listening... level {rms:0.3f}")
            if completed:
                self._emit_completed_loopback_sentence(completed)

    def _normalise_loopback_chunk(self, payload: object) -> np.ndarray:
        chunk = _to_mono_float32(payload)
        if self._loopback_input_sample_rate == self.config.audio_sample_rate:
            return chunk
        return _resample_audio(chunk, self._loopback_input_sample_rate, self.config.audio_sample_rate)

    def _maybe_emit_partial_sentence(
        self,
        track_type: str,
        speaker: str,
        vad: EnergyVADSegmenter | SileroVADSegmenter,
    ) -> None:
        if not self.config.partial_subtitles_enabled:
            return
        now = time.monotonic()
        interval = max(0.2, self.config.partial_interval_ms / 1000)
        if now - self._last_partial_emit_at.get(track_type, 0.0) < interval:
            return
        completed = vad.preview_audio()
        if completed is None:
            return
        start, end = self._current_sentence_times(completed)
        self._last_partial_emit_at[track_type] = now
        self.partial_speech_ready.emit(
            TranscriptDraft(
                speaker=speaker,
                text="",
                language_code="auto",
                track_type=track_type,
                is_partial=True,
                start_time=start,
                end_time=end,
                audio_data=completed.audio_data.copy(),
            )
        )

    def _emit_completed_mic_sentence(self, completed: CompletedSpeech) -> None:
        start, end = self._current_sentence_times(completed)
        self._maybe_write_debug_audio("mic", completed.audio_data)
        self.status_changed.emit("Mic sentence captured; transcribing")
        self.sentence_completed.emit(
            TranscriptDraft(
                speaker="Me",
                text="",
                language_code="auto",
                track_type="mic",
                start_time=start,
                end_time=end,
                audio_data=completed.audio_data,
            )
        )

    def _emit_completed_loopback_sentence(self, completed: CompletedSpeech) -> None:
        speaker = self._detect_remote_speaker()
        start, end = self._current_sentence_times(completed)
        self._maybe_write_debug_audio("loopback", completed.audio_data)
        self.status_changed.emit(f"Loopback sentence captured [{speaker}]; transcribing")
        self.sentence_completed.emit(
            TranscriptDraft(
                speaker=speaker,
                text="",
                language_code="auto",
                track_type="loopback",
                start_time=start,
                end_time=end,
                audio_data=completed.audio_data,
            )
        )

    def _current_sentence_times(self, completed: CompletedSpeech) -> tuple[float, float]:
        elapsed_offset = time.monotonic() - self._started_at
        duration = completed.end_time - completed.start_time
        start = max(0.0, elapsed_offset - duration)
        end = start + duration
        return start, end

    def _detect_remote_speaker(self) -> str:
        if self._visual_tracker is None:
            from visual_tracker import VisualSpeakerTracker

            self._visual_tracker = VisualSpeakerTracker(self.config)

        try:
            detect_active_speaker = self._visual_tracker.detect_active_speaker
            speaker = str(detect_active_speaker()).strip()
        except Exception as exc:
            self.status_changed.emit(f"Speaker OCR fallback: {exc}")
            return "Remote Participant"
        return speaker or "Remote Participant"

    def _maybe_write_debug_audio(self, track_type: str, audio: np.ndarray) -> None:
        if not self.config.debug_audio_enabled or audio.size == 0:
            return
        try:
            from scipy.io import wavfile

            self.config.debug_audio_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            path = self.config.debug_audio_dir / f"{stamp}_{track_type}.wav"
            clipped = np.clip(audio, -1.0, 1.0)
            pcm = (clipped * 32767).astype(np.int16)
            wavfile.write(path, self.config.audio_sample_rate, pcm)
        except Exception as exc:
            self.status_changed.emit(f"Debug audio save warning: {exc}")


def _fake_audio_chunk(sample_rate: int) -> np.ndarray:
    t = np.linspace(0, 0.32, int(sample_rate * 0.32), endpoint=False)
    return (0.05 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def _to_mono_float32(chunk: object) -> np.ndarray:
    audio = np.asarray(chunk, dtype=np.float32)
    if audio.ndim == 2:
        audio = audio.mean(axis=1)
    return np.ascontiguousarray(audio.reshape(-1))


def _rms(audio: np.ndarray) -> float:
    if audio.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(audio.astype(np.float32)))))


def _resample_audio(audio: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    if audio.size == 0 or source_rate == target_rate:
        return audio.astype(np.float32, copy=False)
    gcd = int(np.gcd(source_rate, target_rate))
    up = target_rate // gcd
    down = source_rate // gcd
    return resample_poly(audio, up, down).astype(np.float32, copy=False)


def _select_remote_input_device(config: AppConfig) -> dict[str, object] | None:
    if config.remote_device_index is not None:
        device = _sounddevice_input_by_index(config.remote_device_index)
        if device is None:
            raise RuntimeError(f"Device {config.remote_device_index} is not an input device")
        return device

    candidates = _remote_input_device_candidates(config)
    return candidates[0] if candidates else None


def _remote_input_device_candidates(config: AppConfig) -> list[dict[str, object]]:
    keywords = tuple(keyword.lower() for keyword in config.remote_device_keywords)
    candidates: list[dict[str, object]] = []
    for index, device in enumerate(sd.query_devices()):
        item = dict(device)
        if int(item.get("max_input_channels", 0)) <= 0:
            continue
        if config.mic_device_index is not None and index == config.mic_device_index:
            continue

        name = str(item.get("name") or "")
        lower_name = name.lower()
        if any(keyword in lower_name for keyword in keywords):
            item["index"] = index
            candidates.append(item)

    return candidates


def _sounddevice_input_by_index(index: int) -> dict[str, object] | None:
    try:
        device = dict(sd.query_devices(index))
    except Exception:
        return None
    if int(device.get("max_input_channels", 0)) <= 0:
        return None
    device["index"] = index
    return device


def _select_wasapi_loopback_device(
    pa: object,
    pyaudio: object,
    explicit_index: int | None,
) -> dict[str, object]:
    if explicit_index is not None:
        return dict(pa.get_device_info_by_index(explicit_index))

    candidates = _loopback_device_candidates(pa)
    default_output = _default_wasapi_output_device(pa, pyaudio)
    if default_output and bool(default_output.get("isLoopbackDevice")):
        return default_output

    if default_output:
        default_name = _normalise_device_name(str(default_output.get("name") or ""))
        for candidate in candidates:
            candidate_name = _normalise_device_name(str(candidate.get("name") or ""))
            if default_name and (default_name in candidate_name or candidate_name in default_name):
                return candidate

    if candidates:
        return candidates[0]

    raise RuntimeError("No WASAPI loopback recording device found")


def _loopback_device_candidates(pa: object) -> list[dict[str, object]]:
    generator = getattr(pa, "get_loopback_device_info_generator", None)
    if callable(generator):
        return [dict(device) for device in generator()]

    candidates: list[dict[str, object]] = []
    get_count = pa.get_device_count
    get_device = pa.get_device_info_by_index
    for index in range(int(get_count())):
        device = dict(get_device(index))
        name = str(device.get("name") or "").lower()
        if bool(device.get("isLoopbackDevice")) or "loopback" in name:
            candidates.append(device)
    return candidates


def _default_wasapi_output_device(pa: object, pyaudio: object) -> dict[str, object] | None:
    try:
        host_info = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
        default_index = int(host_info["defaultOutputDevice"])
        if default_index >= 0:
            return dict(pa.get_device_info_by_index(default_index))
    except Exception:
        return None
    return None


def _normalise_device_name(name: str) -> str:
    return (
        name.lower()
        .replace("[loopback]", "")
        .replace("loopback", "")
        .replace("(", " ")
        .replace(")", " ")
        .replace("-", " ")
        .strip()
    )
