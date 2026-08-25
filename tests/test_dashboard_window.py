from __future__ import annotations

from ui.dashboard_window import _audio_level_text, _rms_to_percent


def test_rms_to_percent_clamps_meter_value() -> None:
    assert _rms_to_percent(0.0) == 0
    assert _rms_to_percent(0.04, reference=0.08) == 50
    assert _rms_to_percent(0.5, reference=0.08) == 100


def test_audio_level_text_marks_speech_state() -> None:
    assert _audio_level_text("Mic", 0.0123, True) == "Mic: 0.012 speech"
    assert _audio_level_text("Remote", 0.0, False) == "Remote: 0.000 idle"
