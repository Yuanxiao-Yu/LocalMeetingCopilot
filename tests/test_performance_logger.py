from __future__ import annotations

import json

from config import AppConfig
from meeting_types import TranscriptEntry
from performance_logger import PerformanceTimelineLogger, build_performance_record


def test_build_performance_record_omits_transcript_text() -> None:
    entry = TranscriptEntry(
        speaker="Remote Participant",
        original_text="private source text",
        chinese_translation="私密翻译",
        language_code="de",
        track_type="loopback",
        start_time=2.0,
        end_time=4.5,
        captured_at=10.0,
        asr_started_at=10.1,
        asr_completed_at=10.6,
        translation_queued_at=10.7,
        translation_dequeued_at=11.0,
        translation_started_at=11.1,
        translation_first_token_at=11.35,
        translation_completed_at=12.3,
    )

    record = build_performance_record(entry, AppConfig(meeting_profile="de"))
    dumped = json.dumps(record, ensure_ascii=False)

    assert record["audio_seconds"] == 2.5
    assert record["asr_ms"] == 500
    assert record["translation_queue_ms"] == 300
    assert record["llm_first_token_ms"] == 250
    assert "private source text" not in dumped
    assert "私密翻译" not in dumped


def test_performance_logger_appends_jsonl(tmp_path) -> None:
    config = AppConfig(log_dir=tmp_path / "logs", performance_log_dir=tmp_path / "performance")
    entry = TranscriptEntry(
        speaker="Me",
        original_text="Test",
        chinese_translation="测试",
        translation_completed_at=1.0,
    )

    path = PerformanceTimelineLogger(config).append_entry(entry)

    assert path is not None
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["speaker"] == "Me"


def test_performance_logger_skips_privacy_mode(tmp_path) -> None:
    config = AppConfig(
        privacy_mode=True,
        performance_log_dir=tmp_path / "performance",
    )
    entry = TranscriptEntry(speaker="Me", original_text="Test", chinese_translation="测试")

    path = PerformanceTimelineLogger(config).append_entry(entry)

    assert path is None
    assert not config.performance_log_dir.exists()
