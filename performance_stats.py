from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from math import ceil
from statistics import fmean

from meeting_types import TranscriptEntry

LATENCY_TARGETS_MS: dict[str, dict[str, float]] = {
    "fast": {
        "asr": 900.0,
        "llm": 1800.0,
        "queue": 700.0,
        "total": 3000.0,
    },
    "balanced": {
        "asr": 1400.0,
        "llm": 2800.0,
        "queue": 900.0,
        "total": 4500.0,
    },
    "accurate": {
        "asr": 2300.0,
        "llm": 4500.0,
        "queue": 1200.0,
        "total": 7000.0,
    },
}


@dataclass(frozen=True, slots=True)
class LatencyMetricStats:
    name: str
    count: int
    latest_ms: float | None
    avg_ms: float | None
    p95_ms: float | None
    max_ms: float | None
    target_ms: float


@dataclass(frozen=True, slots=True)
class PerformanceStats:
    sample_count: int
    window_size: int
    llm_count: int
    cache_hit_count: int
    local_count: int
    asr: LatencyMetricStats
    llm: LatencyMetricStats
    queue: LatencyMetricStats
    total: LatencyMetricStats


def build_performance_stats(
    entries: Sequence[TranscriptEntry],
    *,
    preset: str,
    window_size: int = 20,
) -> PerformanceStats:
    window = list(entries[-max(1, window_size) :])
    targets = LATENCY_TARGETS_MS.get(preset, LATENCY_TARGETS_MS["fast"])
    return PerformanceStats(
        sample_count=len(window),
        window_size=max(1, window_size),
        llm_count=sum(1 for entry in window if entry.translation_source == "llm"),
        cache_hit_count=sum(1 for entry in window if entry.translation_source == "cache"),
        local_count=sum(1 for entry in window if entry.translation_source == "local"),
        asr=_metric(
            "ASR",
            (entry.asr_latency_ms for entry in window),
            target_ms=targets["asr"],
        ),
        llm=_metric(
            "LLM",
            (
                entry.translation_latency_ms
                for entry in window
                if entry.translation_source == "llm"
            ),
            target_ms=targets["llm"],
        ),
        queue=_metric(
            "Queue",
            (entry.translation_queue_latency_ms for entry in window),
            target_ms=targets["queue"],
        ),
        total=_metric(
            "Total",
            (entry.total_latency_ms for entry in window),
            target_ms=targets["total"],
        ),
    )


def metric_progress_percent(metric: LatencyMetricStats) -> int:
    value = metric.p95_ms if metric.p95_ms is not None else metric.avg_ms
    if value is None or metric.target_ms <= 0:
        return 0
    return max(0, min(100, round((value / metric.target_ms) * 100)))


def format_metric_line(metric: LatencyMetricStats) -> str:
    if metric.count == 0:
        return f"{metric.name}: n/a"
    return (
        f"{metric.name}: now {_format_ms(metric.latest_ms)} | "
        f"avg {_format_ms(metric.avg_ms)}\n"
        f"p95 {_format_ms(metric.p95_ms)} | "
        f"max {_format_ms(metric.max_ms)}"
    )


def format_source_mix(stats: PerformanceStats) -> str:
    return f"LLM {stats.llm_count} | cache {stats.cache_hit_count} | local {stats.local_count}"


def _metric(
    name: str,
    values: Iterable[float | None],
    *,
    target_ms: float,
) -> LatencyMetricStats:
    clean = [round(float(value), 3) for value in values if value is not None]
    if not clean:
        return LatencyMetricStats(
            name=name,
            count=0,
            latest_ms=None,
            avg_ms=None,
            p95_ms=None,
            max_ms=None,
            target_ms=target_ms,
        )
    return LatencyMetricStats(
        name=name,
        count=len(clean),
        latest_ms=clean[-1],
        avg_ms=round(fmean(clean), 3),
        p95_ms=_percentile_nearest_rank(clean, 95),
        max_ms=max(clean),
        target_ms=target_ms,
    )


def _percentile_nearest_rank(values: Sequence[float], percentile: int) -> float:
    if not values:
        raise ValueError("values must not be empty")
    ordered = sorted(values)
    rank = max(1, ceil((percentile / 100) * len(ordered)))
    return ordered[min(len(ordered), rank) - 1]


def _format_ms(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value / 1000:0.1f}s"
