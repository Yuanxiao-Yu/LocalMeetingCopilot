from meeting_types import TranscriptEntry
from summarizer import MeetingSummarizer


def test_markdown_report_contains_personal_section() -> None:
    summarizer = MeetingSummarizer()
    summarizer.add_entry(
        TranscriptEntry(
            speaker="Me",
            original_text="Ich kann das morgen prüfen.",
            chinese_translation="我可以明天检查这个。",
            language_code="de",
        )
    )

    report = summarizer.build_markdown_report()

    assert "# 2. 针对 [Me] 的专属任务与待办" in report
    assert "我可以明天检查这个。" in report


def test_markdown_report_can_include_ai_summary() -> None:
    summarizer = MeetingSummarizer()
    summarizer.add_entry(
        TranscriptEntry(
            speaker="Remote Participant",
            original_text="Could you check the rollout risk?",
            chinese_translation="你能检查发布风险吗？",
            language_code="en",
        )
    )

    report = summarizer.build_markdown_report(ai_summary="# 1. 会议核心摘要与结论\n\n- AI summary")

    assert "- AI summary" in report
    assert "# 4. 完整中德/中英对照逐字记录" in report


def test_transcript_entry_latency_label() -> None:
    entry = TranscriptEntry(
        speaker="Remote Participant",
        original_text="Wir starten.",
        chinese_translation="我们开始。",
        captured_at=1.0,
        asr_started_at=1.1,
        asr_completed_at=1.6,
        translation_started_at=1.7,
        translation_completed_at=2.9,
    )

    assert "ASR 0.5s" in entry.latency_label
    assert "LLM 1.2s" in entry.to_markdown()


def test_transcript_entry_latency_label_marks_cache_hit() -> None:
    entry = TranscriptEntry(
        speaker="Remote Participant",
        original_text="Wir starten.",
        chinese_translation="我们开始。",
        captured_at=1.0,
        translation_completed_at=1.1,
        translation_source="cache",
    )

    assert "cache hit" in entry.latency_label
    assert "total 0.1s" in entry.latency_label


def test_transcript_entry_latency_label_marks_local_translation() -> None:
    entry = TranscriptEntry(
        speaker="Remote Participant",
        original_text="Genau.",
        chinese_translation="对。",
        captured_at=1.0,
        translation_completed_at=1.05,
        translation_source="local",
    )

    assert "local" in entry.latency_label


def test_transcript_entry_performance_label_includes_queue_and_first_token() -> None:
    entry = TranscriptEntry(
        speaker="Remote Participant",
        original_text="Wir starten.",
        chinese_translation="我们开始。",
        start_time=3.0,
        end_time=5.0,
        captured_at=10.0,
        asr_started_at=10.1,
        asr_completed_at=10.6,
        translation_queued_at=10.7,
        translation_dequeued_at=11.0,
        translation_started_at=11.1,
        translation_first_token_at=11.3,
        translation_completed_at=12.3,
    )

    assert "audio 2.0s" in entry.performance_label
    assert "queue 0.3s" in entry.performance_label
    assert "first 0.2s" in entry.performance_label
