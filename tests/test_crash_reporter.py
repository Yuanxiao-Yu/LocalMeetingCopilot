from __future__ import annotations

from crash_reporter import render_crash_report, write_crash_report


def test_render_crash_report_includes_exception_and_context() -> None:
    try:
        raise RuntimeError("boom")
    except RuntimeError as exc:
        report = render_crash_report(
            type(exc),
            exc,
            exc.__traceback__,
            context={"thread": "worker"},
        )

    assert "RuntimeError: boom" in report
    assert "Traceback:" in report
    assert "- thread: worker" in report


def test_write_crash_report_creates_file(tmp_path) -> None:
    try:
        raise ValueError("bad value")
    except ValueError as exc:
        path = write_crash_report(type(exc), exc, exc.__traceback__, log_dir=tmp_path)

    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "ValueError: bad value" in text
