from config import AppConfig
from main import (
    apply_dashboard_settings,
    is_german_clause_fragment,
    should_skip_partial_transcription,
)


def test_german_clause_fragment_detects_subordinate_start() -> None:
    assert is_german_clause_fragment("weil die Datenpipeline noch instabil ist", ("weil", "dass"))


def test_german_clause_fragment_detects_unfinished_connector() -> None:
    assert is_german_clause_fragment("Wir starten erst dann wenn", ("wenn",))


def test_german_clause_fragment_ignores_complete_plain_sentence() -> None:
    assert not is_german_clause_fragment("Wir starten morgen.", ("weil", "dass", "wenn"))


def test_partial_transcription_skips_when_final_asr_is_busy() -> None:
    assert should_skip_partial_transcription(
        asr_busy_count=1,
        partial_busy_tracks=set(),
        track_type="mic",
        skip_when_asr_busy=True,
    )


def test_partial_transcription_can_ignore_asr_busy_guard() -> None:
    assert not should_skip_partial_transcription(
        asr_busy_count=1,
        partial_busy_tracks=set(),
        track_type="mic",
        skip_when_asr_busy=False,
    )


def test_partial_transcription_skips_busy_track() -> None:
    assert should_skip_partial_transcription(
        asr_busy_count=0,
        partial_busy_tracks={"remote"},
        track_type="remote",
        skip_when_asr_busy=False,
    )


def test_dashboard_preset_change_uses_preset_vad_default() -> None:
    config = AppConfig(model_preset="fast", vad_sensitivity=85)
    model_changed, tuning_changed = apply_dashboard_settings(
        config,
        _dashboard_settings(preset="accurate", vad_sensitivity=85),
        {},
    )

    assert model_changed is True
    assert tuning_changed is True
    assert config.model_preset == "accurate"
    assert config.asr_model_size == "medium"
    assert config.vad_sensitivity == 40


def test_dashboard_vad_change_keeps_manual_vad_when_preset_is_same() -> None:
    config = AppConfig(model_preset="fast", vad_sensitivity=85)

    apply_dashboard_settings(config, _dashboard_settings(vad_sensitivity=70), {})

    assert config.model_preset == "fast"
    assert config.vad_sensitivity == 70


def _dashboard_settings(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "profile": "de",
        "preset": "fast",
        "style": "meeting",
        "mic_device_index": None,
        "remote_device_index": None,
        "capture_mic_enabled": True,
        "capture_remote_enabled": True,
        "save_reports_enabled": True,
        "privacy_mode": False,
        "debug_audio_enabled": False,
        "auto_summary_on_end": True,
        "vad_sensitivity": 85,
    }
    payload.update(overrides)
    return payload
