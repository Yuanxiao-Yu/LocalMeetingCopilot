from __future__ import annotations

import json
import os
import platform
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

LANGUAGE_PROFILE_ALIASES = {
    "de": "de",
    "german": "de",
    "deutsch": "de",
    "en": "en",
    "english": "en",
    "de-en": "de-en",
    "en-de": "de-en",
    "de_en": "de-en",
    "en_de": "de-en",
    "mixed": "de-en",
    "bilingual": "de-en",
}

LANGUAGE_PROFILES: dict[str, dict[str, Any]] = {
    "de": {
        "label": "Pure German",
        "allowed_languages": ("de",),
        "force_language": "de",
        "default_language": "de",
        "asr_prompt": (
            "Deutschsprachiges Business-Meeting. Erwarte klare deutsche Fachbegriffe, "
            "Nebensaetze, Modalverben, Projektstatus, Datenpipeline, Dashboard, Migration, "
            "Rollout, Kunde, Tabelle, Risiko, Aufgabe, Deadline."
        ),
        "hotwords": (
            "Datenpipeline Dashboard Migration Rollout Kunde Kundentabelle Datenqualitaet "
            "Qualitaet Risiko Deadline Aufgabe Entscheidung Abhaengigkeit Blocker Freigabe "
            "Deployment Produktion Entwicklung Schnittstelle Anforderung"
        ),
        "translator_instruction": (
            "The meeting profile is German-only. Treat the source as German unless the text is clearly English. "
            "Pay special attention to Nebensatz, separable verbs, modal verbs, compound nouns, and business/project context."
        ),
    },
    "en": {
        "label": "Pure English",
        "allowed_languages": ("en",),
        "force_language": "en",
        "default_language": "en",
        "asr_prompt": (
            "English business meeting. Expect project status, data pipeline, dashboard, migration, rollout, "
            "customer table, quality, risk, action item, deadline, blocker, dependency, deployment."
        ),
        "hotwords": (
            "data pipeline dashboard migration rollout customer table data quality risk deadline "
            "action item decision dependency blocker approval deployment production staging requirement"
        ),
        "translator_instruction": (
            "The meeting profile is English-only. Translate concise spoken English into natural Simplified Chinese, preserving business intent."
        ),
    },
    "de-en": {
        "label": "German + English",
        "allowed_languages": ("de", "en"),
        "force_language": None,
        "default_language": "de",
        "asr_prompt": (
            "Bilingual German and English business meeting. Speakers may switch between German and English. "
            "Expect project, data, dashboard, migration, rollout, risk, deadline, dependency, action item."
        ),
        "hotwords": (
            "Datenpipeline data pipeline Dashboard Migration Rollout customer Kunde Kundentabelle "
            "data quality Datenqualitaet risk Risiko deadline Aufgabe action item dependency Abhaengigkeit blocker"
        ),
        "translator_instruction": (
            "The meeting profile is German-English mixed. Detect whether the sentence is German or English, then translate to natural Simplified Chinese. "
            "For German, reconstruct Nebensatz and compound nouns carefully."
        ),
    },
}

MODEL_PRESET_ALIASES = {
    "fast": "fast",
    "balanced": "balanced",
    "accurate": "accurate",
}

MODEL_PRESETS: dict[str, dict[str, Any]] = {
    "fast": {
        "label": "Fast",
        "asr_model_size": "base",
        "asr_beam_size": 1,
        "asr_file_beam_size": 2,
        "vad_sensitivity": 85,
        "context_window_size": 4,
        "translation_num_predict": 128,
    },
    "balanced": {
        "label": "Balanced",
        "asr_model_size": "small",
        "asr_beam_size": 1,
        "asr_file_beam_size": 3,
        "vad_sensitivity": 65,
        "context_window_size": 6,
        "translation_num_predict": 160,
    },
    "accurate": {
        "label": "Accurate",
        "asr_model_size": "medium",
        "asr_beam_size": 3,
        "asr_file_beam_size": 5,
        "vad_sensitivity": 40,
        "context_window_size": 8,
        "translation_num_predict": 256,
    },
}

TRANSLATION_STYLES: dict[str, str] = {
    "literal": "Prefer precise literal meaning. Do not over-summarize. Preserve technical details and negations.",
    "meeting": "Use concise meeting-note Chinese. Preserve decisions, owners, risks, deadlines, and action intent.",
    "natural": "Use natural spoken Simplified Chinese while preserving the source meaning and business nuance.",
}

DEFAULT_HALLUCINATION_PHRASES: tuple[str, ...] = (
    "thanks for watching",
    "thank you for watching",
    "danke fürs zuschauen",
    "danke fürs zusehen",
    "untertitel von",
    "amara.org",
    "subscribe to",
    "like and subscribe",
    "字幕",
    "谢谢观看",
    "感谢观看",
    "请不吝点赞",
    "شكرا للمشاهدة",
)

GERMAN_CLAUSE_MARKERS: tuple[str, ...] = (
    "weil",
    "dass",
    "wenn",
    "obwohl",
    "damit",
    "waehrend",
    "während",
    "bevor",
    "nachdem",
    "falls",
    "ob",
    "sobald",
    "solange",
    "indem",
)

_PROJECT_ROOT = Path(__file__).resolve().parent
_SETTINGS_FILENAME = "settings.json"


class AppConfig(BaseModel):
    app_name: str = "LocalMeetingCopilot"
    project_root: Path = Field(default_factory=lambda: _PROJECT_ROOT)
    log_dir: Path = Field(default_factory=lambda: _PROJECT_ROOT / "logs")
    model_cache_dir: Path = Field(default_factory=lambda: _PROJECT_ROOT / "models")
    settings_file: Path = Field(default_factory=lambda: _PROJECT_ROOT / _SETTINGS_FILENAME)

    meeting_profile: str = "de-en"
    model_preset: str = "fast"
    translation_style: str = "meeting"
    asr_model_size: str = "base"
    asr_device: str = "cpu"
    asr_compute_type: str = "int8"
    asr_beam_size: int = 1
    asr_file_beam_size: int = 3
    asr_min_audio_seconds: float = 0.55
    asr_allowed_languages: tuple[str, ...] = ("de", "en", "zh")
    asr_default_language: str = "de"
    asr_force_language: str | None = None
    asr_retry_disallowed_language: bool = True
    asr_condition_on_previous_text: bool = False
    asr_hallucination_phrases: tuple[str, ...] = DEFAULT_HALLUCINATION_PHRASES
    partial_subtitles_enabled: bool = True
    partial_interval_ms: int = 1200
    partial_min_audio_seconds: float = 1.05
    partial_asr_beam_size: int = 1
    partial_asr_vad_filter: bool = False
    partial_skip_when_asr_busy: bool = True
    merge_short_sentences_enabled: bool = True
    merge_short_sentence_chars: int = 42
    merge_short_sentence_ms: int = 650
    german_clause_merge_enabled: bool = True
    german_clause_merge_ms: int = 900
    german_clause_markers: tuple[str, ...] = GERMAN_CLAUSE_MARKERS
    audio_sample_rate: int = 16_000
    audio_chunk_ms: int = 320
    vad_mode: str = "auto"
    vad_sensitivity: int = 85
    silero_threshold: float = 0.48
    vad_threshold: float = 0.5
    vad_energy_threshold: float = 0.012
    vad_min_speech_ms: int = 360
    vad_silence_ms: int = 550
    vad_pre_roll_ms: int = 240
    vad_max_sentence_seconds: float = 24.0
    mic_device_index: int | None = None
    loopback_device_index: int | None = None
    remote_device_index: int | None = None
    remote_device_keywords: tuple[str, ...] = (
        "blackhole",
        "background music",
        "microsoft teams audio",
        "zoom audio",
        "loopback",
    )
    visual_scan_enabled: bool = True
    visual_window_keywords: tuple[str, ...] = ("teams", "zoom")
    visual_ocr_min_confidence: float = 0.42
    visual_speaker_cache_seconds: float = 20.0

    ollama_model: str = "qwen2.5:3b-instruct"
    ollama_host: str = "http://127.0.0.1:11434"
    ollama_timeout_seconds: float = 60.0
    context_window_size: int = 8
    translation_num_predict: int = 128
    translation_streaming_enabled: bool = True
    structured_glossary_enabled: bool = True
    glossary_max_terms: int = 8
    translation_cache_enabled: bool = True
    translation_cache_persist_enabled: bool = True
    translation_cache_max_entries: int = 2000
    translation_cache_ttl_days: int = 30
    summary_num_predict: int = 800
    translation_queue_limit: int = 12
    summary_max_transcript_chars: int = 18_000
    auto_summary_on_end: bool = True
    auto_export_on_end: bool = True
    save_reports_enabled: bool = True
    privacy_mode: bool = False
    debug_audio_enabled: bool = False
    capture_mic_enabled: bool = True
    capture_remote_enabled: bool = True
    latency_diagnostics_enabled: bool = True
    performance_logging_enabled: bool = True
    warmup_enabled: bool = True
    shutdown_wait_ms: int = 8000
    speaker_aliases: dict[str, str] = Field(default_factory=dict)

    profile_terms_dir: Path = Field(default_factory=lambda: _PROJECT_ROOT / "profiles")
    custom_terms_file: Path = Field(
        default_factory=lambda: _PROJECT_ROOT / "profiles" / "custom_terms.txt"
    )
    debug_audio_dir: Path = Field(
        default_factory=lambda: _PROJECT_ROOT / "logs" / "debug_audio"
    )
    translation_cache_file: Path = Field(
        default_factory=lambda: _PROJECT_ROOT / "logs" / "cache" / "translation_cache.jsonl"
    )
    performance_log_dir: Path = Field(
        default_factory=lambda: _PROJECT_ROOT / "logs" / "performance"
    )

    overlay_width: int = 920
    overlay_height: int = 150
    overlay_opacity: float = 0.94

    @property
    def is_windows(self) -> bool:
        return platform.system().lower() == "windows"

    @property
    def is_macos(self) -> bool:
        return platform.system().lower() == "darwin"

    def ensure_directories(self) -> None:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.model_cache_dir.mkdir(parents=True, exist_ok=True)
        self.profile_terms_dir.mkdir(parents=True, exist_ok=True)
        if self.debug_audio_enabled:
            self.debug_audio_dir.mkdir(parents=True, exist_ok=True)
        if (
            self.translation_cache_enabled
            and self.translation_cache_persist_enabled
            and not self.privacy_mode
        ):
            self.translation_cache_file.parent.mkdir(parents=True, exist_ok=True)
        if self.performance_logging_enabled and not self.privacy_mode:
            self.performance_log_dir.mkdir(parents=True, exist_ok=True)

    @property
    def language_profile_label(self) -> str:
        return str(LANGUAGE_PROFILES[self.meeting_profile]["label"])

    @property
    def asr_initial_prompt(self) -> str:
        parts = [str(LANGUAGE_PROFILES[self.meeting_profile]["asr_prompt"])]
        terms = self.profile_terms_text
        if terms:
            parts.append(f"Known meeting terms and names: {terms}")
        return "\n".join(parts)

    @property
    def asr_hotwords(self) -> str:
        terms = self.profile_terms_text
        base = str(LANGUAGE_PROFILES[self.meeting_profile]["hotwords"])
        return f"{base} {terms}".strip()

    @property
    def translator_profile_instruction(self) -> str:
        instruction = str(LANGUAGE_PROFILES[self.meeting_profile]["translator_instruction"])
        style = TRANSLATION_STYLES[self.translation_style]
        return f"{instruction} {style}"

    @property
    def model_preset_label(self) -> str:
        return str(MODEL_PRESETS[self.model_preset]["label"])

    @property
    def profile_terms_text(self) -> str:
        return " ".join(_read_terms_files(self.profile_terms_files()))

    def profile_terms_files(self) -> tuple[Path, ...]:
        return (
            self.profile_terms_dir / f"{self.meeting_profile}_terms.txt",
            self.custom_terms_file,
        )


def load_config(
    profile: str | None = None,
    preset: str | None = None,
    translation_style: str | None = None,
) -> AppConfig:
    saved = load_runtime_settings()
    meeting_profile = normalise_meeting_profile(
        profile or os.getenv("LMC_MEETING_PROFILE") or _setting_str(saved, "meeting_profile", "de-en")
    )
    model_preset = normalise_model_preset(
        preset or os.getenv("LMC_MODEL_PRESET") or _setting_str(saved, "model_preset", "fast")
    )
    style = normalise_translation_style(
        translation_style
        or os.getenv("LMC_TRANSLATION_STYLE")
        or _setting_str(saved, "translation_style", "meeting")
    )
    profile_settings = LANGUAGE_PROFILES[meeting_profile]
    preset_settings = MODEL_PRESETS[model_preset]
    env_force_language = _optional_language(os.getenv("LMC_ASR_FORCE_LANGUAGE"))
    env_allowed_languages = _optional_language_tuple(os.getenv("LMC_ASR_ALLOWED_LANGUAGES"))
    config = AppConfig(
        meeting_profile=meeting_profile,
        model_preset=model_preset,
        translation_style=style,
        asr_model_size=os.getenv("LMC_ASR_MODEL_SIZE", preset_settings["asr_model_size"]),
        asr_device=os.getenv("LMC_ASR_DEVICE", "cpu"),
        asr_compute_type=os.getenv("LMC_ASR_COMPUTE_TYPE", "int8"),
        asr_beam_size=_optional_int(os.getenv("LMC_ASR_BEAM_SIZE"))
        or preset_settings["asr_beam_size"],
        asr_file_beam_size=_optional_int(os.getenv("LMC_ASR_FILE_BEAM_SIZE"))
        or preset_settings["asr_file_beam_size"],
        asr_allowed_languages=env_allowed_languages or profile_settings["allowed_languages"],
        asr_default_language=os.getenv("LMC_ASR_DEFAULT_LANGUAGE", profile_settings["default_language"]),
        asr_force_language=env_force_language
        if env_force_language is not None
        else profile_settings["force_language"],
        vad_sensitivity=_optional_int(os.getenv("LMC_VAD_SENSITIVITY"))
        or _setting_int(saved, "vad_sensitivity")
        or int(preset_settings["vad_sensitivity"]),
        ollama_model=os.getenv("LMC_OLLAMA_MODEL", "qwen2.5:3b-instruct"),
        ollama_host=os.getenv("LMC_OLLAMA_HOST", "http://127.0.0.1:11434"),
        ollama_timeout_seconds=_optional_float(os.getenv("LMC_OLLAMA_TIMEOUT_SECONDS")) or 60.0,
        context_window_size=_optional_int(os.getenv("LMC_CONTEXT_WINDOW_SIZE"))
        or int(preset_settings["context_window_size"]),
        translation_num_predict=_optional_int(os.getenv("LMC_TRANSLATION_NUM_PREDICT"))
        or int(preset_settings["translation_num_predict"]),
        translation_streaming_enabled=_optional_bool(
            os.getenv("LMC_TRANSLATION_STREAMING"),
            _setting_bool(saved, "translation_streaming_enabled", True),
        ),
        structured_glossary_enabled=_optional_bool(
            os.getenv("LMC_STRUCTURED_GLOSSARY"),
            _setting_bool(saved, "structured_glossary_enabled", True),
        ),
        glossary_max_terms=_optional_int(os.getenv("LMC_GLOSSARY_MAX_TERMS"))
        or _setting_int(saved, "glossary_max_terms")
        or 8,
        translation_cache_enabled=_optional_bool(
            os.getenv("LMC_TRANSLATION_CACHE"),
            _setting_bool(saved, "translation_cache_enabled", True),
        ),
        translation_cache_persist_enabled=_optional_bool(
            os.getenv("LMC_TRANSLATION_CACHE_PERSIST"),
            _setting_bool(saved, "translation_cache_persist_enabled", True),
        ),
        translation_cache_max_entries=_optional_int(os.getenv("LMC_TRANSLATION_CACHE_MAX_ENTRIES"))
        or _setting_int(saved, "translation_cache_max_entries")
        or 2000,
        translation_cache_ttl_days=_optional_int(os.getenv("LMC_TRANSLATION_CACHE_TTL_DAYS"))
        or _setting_int(saved, "translation_cache_ttl_days")
        or 30,
        auto_summary_on_end=_optional_bool(
            os.getenv("LMC_AUTO_SUMMARY_ON_END"),
            _setting_bool(saved, "auto_summary_on_end", True),
        ),
        auto_export_on_end=_optional_bool(
            os.getenv("LMC_AUTO_EXPORT_ON_END"),
            _setting_bool(saved, "auto_export_on_end", True),
        ),
        mic_device_index=_optional_int(os.getenv("LMC_MIC_DEVICE_INDEX"))
        if os.getenv("LMC_MIC_DEVICE_INDEX") is not None
        else _setting_int(saved, "mic_device_index"),
        loopback_device_index=_optional_int(os.getenv("LMC_LOOPBACK_DEVICE_INDEX"))
        if os.getenv("LMC_LOOPBACK_DEVICE_INDEX") is not None
        else _setting_int(saved, "loopback_device_index"),
        remote_device_index=_optional_int(os.getenv("LMC_REMOTE_DEVICE_INDEX"))
        if os.getenv("LMC_REMOTE_DEVICE_INDEX") is not None
        else _setting_int(saved, "remote_device_index"),
        save_reports_enabled=_optional_bool(
            os.getenv("LMC_SAVE_REPORTS"),
            _setting_bool(saved, "save_reports_enabled", True),
        ),
        privacy_mode=_optional_bool(
            os.getenv("LMC_PRIVACY_MODE"),
            _setting_bool(saved, "privacy_mode", False),
        ),
        debug_audio_enabled=_optional_bool(
            os.getenv("LMC_DEBUG_AUDIO"),
            _setting_bool(saved, "debug_audio_enabled", False),
        ),
        capture_mic_enabled=_optional_bool(
            os.getenv("LMC_CAPTURE_MIC"),
            _setting_bool(saved, "capture_mic_enabled", True),
        ),
        capture_remote_enabled=_optional_bool(
            os.getenv("LMC_CAPTURE_REMOTE"),
            _setting_bool(saved, "capture_remote_enabled", True),
        ),
        partial_subtitles_enabled=_optional_bool(
            os.getenv("LMC_PARTIAL_SUBTITLES"),
            _setting_bool(saved, "partial_subtitles_enabled", True),
        ),
        partial_skip_when_asr_busy=_optional_bool(
            os.getenv("LMC_PARTIAL_SKIP_WHEN_ASR_BUSY"),
            _setting_bool(saved, "partial_skip_when_asr_busy", True),
        ),
        performance_logging_enabled=_optional_bool(
            os.getenv("LMC_PERFORMANCE_LOGGING"),
            _setting_bool(saved, "performance_logging_enabled", True),
        ),
        warmup_enabled=_optional_bool(
            os.getenv("LMC_WARMUP"),
            _setting_bool(saved, "warmup_enabled", True),
        ),
        shutdown_wait_ms=_optional_int(os.getenv("LMC_SHUTDOWN_WAIT_MS"))
        or _setting_int(saved, "shutdown_wait_ms")
        or 8000,
        vad_mode=normalise_vad_mode(os.getenv("LMC_VAD_MODE") or _setting_str(saved, "vad_mode", "auto")),
        speaker_aliases=_setting_speaker_aliases(saved),
    )
    apply_vad_sensitivity(config, config.vad_sensitivity)
    if (env_vad_silence_ms := _optional_int(os.getenv("LMC_VAD_SILENCE_MS"))) is not None:
        config.vad_silence_ms = env_vad_silence_ms
    config.ensure_directories()
    return config


def load_runtime_settings(path: str | Path | None = None) -> dict[str, Any]:
    settings_path = Path(path) if path else _PROJECT_ROOT / _SETTINGS_FILENAME
    if not settings_path.exists():
        return {}
    try:
        payload = json.loads(settings_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def runtime_settings_payload(config: AppConfig) -> dict[str, Any]:
    return {
        "meeting_profile": config.meeting_profile,
        "model_preset": config.model_preset,
        "translation_style": config.translation_style,
        "mic_device_index": config.mic_device_index,
        "loopback_device_index": config.loopback_device_index,
        "remote_device_index": config.remote_device_index,
        "capture_mic_enabled": config.capture_mic_enabled,
        "capture_remote_enabled": config.capture_remote_enabled,
        "save_reports_enabled": config.save_reports_enabled,
        "privacy_mode": config.privacy_mode,
        "debug_audio_enabled": config.debug_audio_enabled,
        "partial_subtitles_enabled": config.partial_subtitles_enabled,
        "partial_skip_when_asr_busy": config.partial_skip_when_asr_busy,
        "performance_logging_enabled": config.performance_logging_enabled,
        "warmup_enabled": config.warmup_enabled,
        "shutdown_wait_ms": config.shutdown_wait_ms,
        "vad_mode": config.vad_mode,
        "vad_sensitivity": config.vad_sensitivity,
        "translation_streaming_enabled": config.translation_streaming_enabled,
        "structured_glossary_enabled": config.structured_glossary_enabled,
        "glossary_max_terms": config.glossary_max_terms,
        "translation_cache_enabled": config.translation_cache_enabled,
        "translation_cache_persist_enabled": config.translation_cache_persist_enabled,
        "translation_cache_max_entries": config.translation_cache_max_entries,
        "translation_cache_ttl_days": config.translation_cache_ttl_days,
        "auto_summary_on_end": config.auto_summary_on_end,
        "auto_export_on_end": config.auto_export_on_end,
        "speaker_aliases": dict(sorted(config.speaker_aliases.items())),
    }


def save_runtime_settings(config: AppConfig, path: str | Path | None = None) -> Path:
    settings_path = Path(path) if path else config.settings_file
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(
        json.dumps(runtime_settings_payload(config), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return settings_path


def normalise_meeting_profile(value: str | None) -> str:
    if value in (None, ""):
        return "de-en"
    key = value.lower().strip()
    if key not in LANGUAGE_PROFILE_ALIASES:
        valid = ", ".join(sorted(LANGUAGE_PROFILES))
        raise ValueError(f"Unknown meeting profile {value!r}. Use one of: {valid}")
    return LANGUAGE_PROFILE_ALIASES[key]


def apply_meeting_profile(config: AppConfig, profile: str) -> None:
    meeting_profile = normalise_meeting_profile(profile)
    profile_settings = LANGUAGE_PROFILES[meeting_profile]
    config.meeting_profile = meeting_profile
    config.asr_allowed_languages = profile_settings["allowed_languages"]
    config.asr_default_language = str(profile_settings["default_language"])
    force_language = profile_settings["force_language"]
    config.asr_force_language = str(force_language) if force_language else None


def normalise_model_preset(value: str | None) -> str:
    if value in (None, ""):
        return "fast"
    key = value.lower().strip()
    if key not in MODEL_PRESET_ALIASES:
        valid = ", ".join(sorted(MODEL_PRESETS))
        raise ValueError(f"Unknown model preset {value!r}. Use one of: {valid}")
    return MODEL_PRESET_ALIASES[key]


def apply_model_preset(config: AppConfig, preset: str) -> None:
    model_preset = normalise_model_preset(preset)
    settings = MODEL_PRESETS[model_preset]
    config.model_preset = model_preset
    config.asr_model_size = str(settings["asr_model_size"])
    config.asr_beam_size = int(settings["asr_beam_size"])
    config.asr_file_beam_size = int(settings["asr_file_beam_size"])
    config.context_window_size = int(settings["context_window_size"])
    config.translation_num_predict = int(settings["translation_num_predict"])
    apply_vad_sensitivity(config, int(settings["vad_sensitivity"]))


def apply_vad_sensitivity(config: AppConfig, sensitivity: int) -> None:
    clamped = max(0, min(100, int(sensitivity)))
    ratio = clamped / 100
    config.vad_sensitivity = clamped
    config.vad_energy_threshold = round(0.018 - (0.012 * ratio), 4)
    config.vad_min_speech_ms = int(520 - (280 * ratio))
    config.vad_silence_ms = int(720 - (420 * ratio))
    config.partial_interval_ms = int(1300 - (600 * ratio))
    config.partial_min_audio_seconds = round(1.2 - (0.55 * ratio), 2)
    config.merge_short_sentence_ms = int(760 - (260 * ratio))
    config.german_clause_merge_ms = int(980 - (280 * ratio))


def normalise_translation_style(value: str | None) -> str:
    if value in (None, ""):
        return "meeting"
    key = value.lower().strip()
    if key not in TRANSLATION_STYLES:
        valid = ", ".join(sorted(TRANSLATION_STYLES))
        raise ValueError(f"Unknown translation style {value!r}. Use one of: {valid}")
    return key


def normalise_vad_mode(value: str | None) -> str:
    if value in (None, ""):
        return "auto"
    key = value.lower().strip()
    if key not in {"auto", "energy", "silero"}:
        raise ValueError("Unknown VAD mode. Use one of: auto, energy, silero")
    return key


def _setting_str(settings: dict[str, Any], key: str, default: str) -> str:
    value = settings.get(key, default)
    return str(value) if value not in (None, "") else default


def _setting_int(settings: dict[str, Any], key: str) -> int | None:
    value = settings.get(key)
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _setting_bool(settings: dict[str, Any], key: str, default: bool) -> bool:
    value = settings.get(key, default)
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return default
    return str(value).lower().strip() in {"1", "true", "yes", "on"}


def _setting_speaker_aliases(settings: dict[str, Any]) -> dict[str, str]:
    aliases = settings.get("speaker_aliases")
    if not isinstance(aliases, dict):
        return {}
    cleaned: dict[str, str] = {}
    for raw_key, raw_value in aliases.items():
        key = str(raw_key).strip()
        value = str(raw_value).strip()
        if key and value:
            cleaned[key] = value
    return cleaned


def _optional_int(value: str | None) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def _optional_float(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _optional_language(value: str | None) -> str | None:
    if value in (None, ""):
        return None
    return value.lower().strip()


def _optional_language_tuple(value: str | None) -> tuple[str, ...] | None:
    if value in (None, ""):
        return None
    return tuple(part.strip().lower() for part in value.split(",") if part.strip())


def _optional_bool(value: str | None, default: bool) -> bool:
    if value in (None, ""):
        return default
    return value.lower().strip() in {"1", "true", "yes", "on"}


def _read_terms_files(paths: tuple[Path, ...]) -> list[str]:
    terms: list[str] = []
    for path in paths:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            terms.append(stripped)
    return terms
