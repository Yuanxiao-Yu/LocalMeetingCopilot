from __future__ import annotations

from meeting_types import TranscriptEntry
from performance_stats import (
    build_performance_stats,
    format_metric_line,
    format_source_mix,
    metric_progress_percent,
)


def test_build_performance_stats_tracks_recent_latency_distribution() -> None:
    entries = [
        _entry(asr_ms=300, llm_ms=900, queue_ms=100),
        _entry(asr_ms=500, llm_ms=1200, queue_ms=200),
        _entry(asr_ms=700, llm_ms=1600, queue_ms=300),
    ]

    stats = build_performance_stats(entries, preset="fast", window_size=3)

    assert stats.sample_count == 3
    assert stats.asr.avg_ms == 500
    assert stats.asr.p95_ms == 700
    assert stats.llm.max_ms == 1600
    assert stats.queue.latest_ms == 300
    assert stats.total.p95_ms == 2600
    assert format_source_mix(stats) == "LLM 3 | cache 0 | local 0"


def test_build_performance_stats_counts_cache_and_local_without_llm_bucket() -> None:
    entries = [
        _entry(asr_ms=300, llm_ms=900, queue_ms=100),
        _entry(asr_ms=0, llm_ms=20, queue_ms=0, source="cache"),
        _entry(asr_ms=0, llm_ms=10, queue_ms=0, source="local"),
    ]

    stats = build_performance_stats(entries, preset="fast", window_size=5)

    assert stats.llm_count == 1
    assert stats.cache_hit_count == 1
    assert stats.local_count == 1
    assert stats.llm.count == 1
    assert stats.llm.avg_ms == 900
    assert stats.total.count == 3


def test_performance_stats_respects_window_size() -> None:
    entries = [
        _entry(asr_ms=100, llm_ms=100, queue_ms=0),
        _entry(asr_ms=200, llm_ms=200, queue_ms=0),
        _entry(asr_ms=300, llm_ms=300, queue_ms=0),
    ]

    stats = build_performance_stats(entries, preset="balanced", window_size=2)

    assert stats.sample_count == 2
    assert stats.asr.avg_ms == 250
    assert stats.total.latest_ms == 600


def test_metric_formatting_and_progress() -> None:
    stats = build_performance_stats(
        [_entry(asr_ms=450, llm_ms=900, queue_ms=350)],
        preset="fast",
    )

    assert format_metric_line(stats.asr) == "ASR: now 0.5s | avg 0.5s\np95 0.5s | max 0.5s"
    assert metric_progress_percent(stats.total) == 57


def _entry(
    *,
    asr_ms: int,
    llm_ms: int,
    queue_ms: int,
    source: str = "llm",
) -> TranscriptEntry:
    captured_at = 10.0
    asr_started_at = captured_at
    asr_completed_at = asr_started_at + (asr_ms / 1000)
    translation_queued_at = asr_completed_at
    translation_dequeued_at = translation_queued_at + (queue_ms / 1000)
    translation_started_at = translation_dequeued_at
    translation_completed_at = translation_started_at + (llm_ms / 1000)
    return TranscriptEntry(
        speaker="Remote Participant",
        original_text="Wir starten.",
        chinese_translation="我们开始。",
        captured_at=captured_at,
        asr_started_at=asr_started_at,
        asr_completed_at=asr_completed_at,
        translation_queued_at=translation_queued_at,
        translation_dequeued_at=translation_dequeued_at,
        translation_started_at=translation_started_at,
        translation_first_token_at=translation_started_at + 0.1,
        translation_completed_at=translation_completed_at,
        translation_source=source,
    )
