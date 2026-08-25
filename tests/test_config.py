from config import (
    AppConfig,
    apply_model_preset,
    apply_vad_sensitivity,
    load_config,
    load_runtime_settings,
    normalise_meeting_profile,
    normalise_translation_style,
    normalise_vad_mode,
    save_runtime_settings,
)


def test_config_directories_exist() -> None:
    config = load_config()
    assert config.log_dir.exists()
    assert config.model_cache_dir.exists()
    assert config.ollama_model


def test_german_profile_forces_german_asr() -> None:
    config = load_config(profile="de")

    assert config.meeting_profile == "de"
    assert config.asr_allowed_languages == ("de",)
    assert config.asr_force_language == "de"
    assert "Nebensatz" in config.translator_profile_instruction


def test_mixed_profile_keeps_auto_detection() -> None:
    config = load_config(profile="de-en")

    assert config.meeting_profile == "de-en"
    assert config.asr_allowed_languages == ("de", "en")
    assert config.asr_force_language is None
    assert config.asr_default_language == "de"


def test_profile_aliases() -> None:
    assert normalise_meeting_profile("german") == "de"
    assert normalise_meeting_profile("mixed") == "de-en"


def test_model_preset_updates_asr_settings() -> None:
    config = AppConfig()

    apply_model_preset(config, "accurate")

    assert config.model_preset == "accurate"
    assert config.asr_model_size == "medium"
    assert config.asr_beam_size == 3
    assert config.context_window_size == 8
    assert config.translation_num_predict == 256
    assert config.vad_sensitivity == 40


def test_vad_sensitivity_updates_latency_controls() -> None:
    config = AppConfig()

    apply_vad_sensitivity(config, 90)

    assert config.vad_sensitivity == 90
    assert config.vad_silence_ms <= 350
    assert config.partial_interval_ms <= 800


def test_translation_style_validation() -> None:
    assert normalise_translation_style("natural") == "natural"


def test_vad_mode_validation() -> None:
    assert normalise_vad_mode("silero") == "silero"
    assert normalise_vad_mode(None) == "auto"


def test_runtime_settings_roundtrip(tmp_path) -> None:
    config = AppConfig(
        settings_file=tmp_path / "settings.json",
        meeting_profile="de",
        model_preset="balanced",
        translation_style="literal",
        mic_device_index=2,
        remote_device_index=4,
        privacy_mode=True,
        auto_summary_on_end=False,
        partial_skip_when_asr_busy=False,
        warmup_enabled=False,
        shutdown_wait_ms=2500,
        structured_glossary_enabled=False,
        glossary_max_terms=4,
        translation_cache_enabled=False,
        translation_cache_persist_enabled=False,
        translation_cache_max_entries=32,
        translation_cache_ttl_days=7,
        performance_logging_enabled=False,
        speaker_aliases={"Remote Participant": "Anna Schmidt"},
    )

    path = save_runtime_settings(config)
    loaded = load_runtime_settings(path)

    assert loaded["meeting_profile"] == "de"
    assert loaded["model_preset"] == "balanced"
    assert loaded["translation_style"] == "literal"
    assert loaded["mic_device_index"] == 2
    assert loaded["remote_device_index"] == 4
    assert loaded["privacy_mode"] is True
    assert loaded["auto_summary_on_end"] is False
    assert loaded["partial_skip_when_asr_busy"] is False
    assert loaded["warmup_enabled"] is False
    assert loaded["shutdown_wait_ms"] == 2500
    assert loaded["structured_glossary_enabled"] is False
    assert loaded["glossary_max_terms"] == 4
    assert loaded["translation_cache_enabled"] is False
    assert loaded["translation_cache_persist_enabled"] is False
    assert loaded["translation_cache_max_entries"] == 32
    assert loaded["translation_cache_ttl_days"] == 7
    assert loaded["performance_logging_enabled"] is False
    assert loaded["speaker_aliases"] == {"Remote Participant": "Anna Schmidt"}


def test_profile_terms_include_custom_file(tmp_path) -> None:
    config = AppConfig(profile_terms_dir=tmp_path, custom_terms_file=tmp_path / "custom_terms.txt")
    (tmp_path / "de-en_terms.txt").write_text("Project Phoenix\n", encoding="utf-8")
    config.custom_terms_file.write_text("Musterkunde\n", encoding="utf-8")

    assert "Project Phoenix" in config.profile_terms_text
    assert "Musterkunde" in config.asr_hotwords
    assert "Musterkunde" not in config.translator_profile_instruction
