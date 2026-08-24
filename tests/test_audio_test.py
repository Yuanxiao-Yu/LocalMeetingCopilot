from __future__ import annotations

from io import StringIO
from types import SimpleNamespace

import numpy as np

from audio_engine import EnergyVADSegmenter
from audio_test import AudioProbeStats, format_probe_status, level_bar, run_audio_test
from config import AppConfig


def test_level_bar_scales_with_rms() -> None:
    assert level_bar(0.0, width=4) == "[....]"
    assert level_bar(0.06, width=4) == "[####]"


def test_audio_probe_stats_tracks_vad_events() -> None:
    config = AppConfig(
        audio_sample_rate=1000,
        audio_chunk_ms=100,
        vad_energy_threshold=0.05,
        vad_min_speech_ms=200,
        vad_silence_ms=200,
        vad_pre_roll_ms=100,
    )
    vad = EnergyVADSegmenter(config)
    stats = AudioProbeStats(
        label="mic",
        vad_backend="energy",
        input_sample_rate=1000,
        target_sample_rate=1000,
    )
    silence = np.zeros(100, dtype=np.float32)
    voice = np.full(100, 0.2, dtype=np.float32)

    for chunk in [silence, voice, voice, voice, silence, silence]:
        stats.accept_chunk(chunk, vad, now=1.0)

    assert stats.chunks == 6
    assert stats.peak >= 0.2
    assert stats.speech_starts == 1
    assert stats.completed_segments == 1


def test_format_probe_status_includes_last_status() -> None:
    config = AppConfig()
    vad = EnergyVADSegmenter(config)
    stats = AudioProbeStats(
        label="mic",
        vad_backend="energy",
        input_sample_rate=config.audio_sample_rate,
        target_sample_rate=config.audio_sample_rate,
    )
    stats.record_status("overflow")

    probe = SimpleNamespace(label="Mic", stats=stats, vad=vad)

    assert "status=overflow" in format_probe_status(probe, now=1.0)


def test_run_audio_test_returns_error_when_tracks_disabled() -> None:
    output = StringIO()
    config = AppConfig(capture_mic_enabled=False, capture_remote_enabled=False)

    result = run_audio_test(config=config, duration_seconds=0.1, output=output)

    assert result == 1
    assert "No audio tracks enabled" in output.getvalue()
