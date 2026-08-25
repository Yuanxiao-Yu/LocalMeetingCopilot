from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from time import perf_counter
from typing import Any
from uuid import uuid4

import numpy as np


@dataclass(slots=True)
class TranscriptDraft:
    speaker: str
    text: str
    language_code: str = "auto"
    track_type: str = "mock"
    is_partial: bool = False
    start_time: float = 0.0
    end_time: float = 0.0
    audio_data: np.ndarray | None = None
    confidence: float | None = None
    captured_at: float = field(default_factory=perf_counter)
    asr_started_at: float | None = None
    asr_completed_at: float | None = None
    translation_queued_at: float | None = None
    translation_dequeued_at: float | None = None
    translation_started_at: float | None = None
    translation_first_token_at: float | None = None
    translation_completed_at: float | None = None
    translation_source: str = "llm"


@dataclass(slots=True)
class TranscriptEntry:
    speaker: str
    original_text: str
    chinese_translation: str
    language_code: str = "auto"
    track_type: str = "mock"
    start_time: float = 0.0
    end_time: float = 0.0
    confidence: float | None = None
    captured_at: float | None = None
    asr_started_at: float | None = None
    asr_completed_at: float | None = None
    translation_queued_at: float | None = None
    translation_dequeued_at: float | None = None
    translation_started_at: float | None = None
    translation_first_token_at: float | None = None
    translation_completed_at: float | None = None
    translation_source: str = "llm"
    created_at: datetime = field(default_factory=datetime.now)
    entry_id: str = field(default_factory=lambda: uuid4().hex)

    @property
    def timestamp(self) -> str:
        return self.created_at.strftime("%H:%M:%S")

    @property
    def duration_label(self) -> str:
        if self.end_time <= self.start_time:
            return ""
        return f"{self.start_time:0.1f}-{self.end_time:0.1f}s"

    @property
    def asr_latency_ms(self) -> float | None:
        return _duration_ms(self.asr_started_at, self.asr_completed_at)

    @property
    def translation_latency_ms(self) -> float | None:
        return _duration_ms(self.translation_started_at, self.translation_completed_at)

    @property
    def translation_queue_latency_ms(self) -> float | None:
        return _duration_ms(self.translation_queued_at, self.translation_dequeued_at)

    @property
    def translation_first_token_latency_ms(self) -> float | None:
        return _duration_ms(self.translation_started_at, self.translation_first_token_at)

    @property
    def total_latency_ms(self) -> float | None:
        return _duration_ms(self.captured_at, self.translation_completed_at)

    @property
    def latency_label(self) -> str:
        parts: list[str] = []
        if self.asr_latency_ms is not None:
            parts.append(f"ASR {self.asr_latency_ms / 1000:0.1f}s")
        if self.translation_source == "cache":
            parts.append("cache hit")
        elif self.translation_source == "local":
            parts.append("local")
        elif self.translation_latency_ms is not None:
            parts.append(f"LLM {self.translation_latency_ms / 1000:0.1f}s")
        if self.total_latency_ms is not None:
            parts.append(f"total {self.total_latency_ms / 1000:0.1f}s")
        return " / ".join(parts)

    @property
    def performance_label(self) -> str:
        parts: list[str] = []
        audio_ms = _duration_ms(self.start_time, self.end_time)
        if audio_ms is not None:
            parts.append(f"audio {audio_ms / 1000:0.1f}s")
        if self.translation_queue_latency_ms is not None:
            parts.append(f"queue {self.translation_queue_latency_ms / 1000:0.1f}s")
        if self.asr_latency_ms is not None:
            parts.append(f"ASR {self.asr_latency_ms / 1000:0.1f}s")
        if self.translation_first_token_latency_ms is not None:
            parts.append(f"first {self.translation_first_token_latency_ms / 1000:0.1f}s")
        if self.translation_source in {"cache", "local"}:
            parts.append(self.translation_source)
        elif self.translation_latency_ms is not None:
            parts.append(f"LLM {self.translation_latency_ms / 1000:0.1f}s")
        if self.total_latency_ms is not None:
            parts.append(f"total {self.total_latency_ms / 1000:0.1f}s")
        return " | ".join(parts)

    def to_json_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["created_at"] = self.created_at.isoformat(timespec="seconds")
        return data

    def to_markdown(self) -> str:
        duration = f" `{self.duration_label}`" if self.duration_label else ""
        confidence = f" confidence={self.confidence:0.2f}" if self.confidence is not None else ""
        latency = f" latency={self.latency_label}" if self.latency_label else ""
        return (
            f"- **[{self.timestamp}] [{self.speaker}]**{duration}{confidence}{latency}\n"
            f"  - Original: {self.original_text}\n"
            f"  - 中文: {self.chinese_translation}"
        )


def _duration_ms(start: float | None, end: float | None) -> float | None:
    if start is None or end is None or end < start:
        return None
    return (end - start) * 1000
