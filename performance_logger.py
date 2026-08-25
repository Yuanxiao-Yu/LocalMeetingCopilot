from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from config import AppConfig
from meeting_types import TranscriptEntry


class PerformanceTimelineLogger:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def append_entry(self, entry: TranscriptEntry) -> Path | None:
        if not self.config.performance_logging_enabled or self.config.privacy_mode:
            return None
        path = performance_log_path(self.config, entry.created_at)
        path.parent.mkdir(parents=True, exist_ok=True)
        record = build_performance_record(entry, self.config)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        return path


def performance_log_path(config: AppConfig, when: datetime | None = None) -> Path:
    stamp = (when or datetime.now()).strftime("%Y%m%d")
    return config.performance_log_dir / f"performance_{stamp}.jsonl"


def build_performance_record(entry: TranscriptEntry, config: AppConfig) -> dict[str, Any]:
    return {
        "created_at": entry.created_at.isoformat(timespec="seconds"),
        "entry_id": entry.entry_id,
        "speaker": entry.speaker,
        "track_type": entry.track_type,
        "language_code": entry.language_code,
        "confidence": entry.confidence,
        "profile": config.meeting_profile,
        "preset": config.model_preset,
        "translation_style": config.translation_style,
        "asr_model_size": config.asr_model_size,
        "asr_device": config.asr_device,
        "asr_compute_type": config.asr_compute_type,
        "ollama_model": config.ollama_model,
        "translation_source": entry.translation_source,
        "original_chars": len(entry.original_text),
        "translation_chars": len(entry.chinese_translation),
        "audio_seconds": _duration_seconds(entry.start_time, entry.end_time),
        "capture_to_asr_start_ms": _duration_ms(entry.captured_at, entry.asr_started_at),
        "asr_ms": _rounded(entry.asr_latency_ms),
        "asr_to_queue_ms": _duration_ms(entry.asr_completed_at, entry.translation_queued_at),
        "translation_queue_ms": _rounded(entry.translation_queue_latency_ms),
        "translation_dispatch_ms": _duration_ms(
            entry.translation_dequeued_at,
            entry.translation_started_at,
        ),
        "llm_first_token_ms": _rounded(entry.translation_first_token_latency_ms),
        "translation_ms": _rounded(entry.translation_latency_ms),
        "total_ms": _rounded(entry.total_latency_ms),
        "cache_hit": entry.translation_source == "cache",
    }


def _duration_ms(start: float | None, end: float | None) -> float | None:
    if start is None or end is None or end < start:
        return None
    return round((end - start) * 1000, 3)


def _duration_seconds(start: float, end: float) -> float | None:
    if end <= start:
        return None
    return round(end - start, 3)


def _rounded(value: float | None) -> float | None:
    return None if value is None else round(value, 3)
