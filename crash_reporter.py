from __future__ import annotations

import platform
import sys
import threading
import traceback
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from types import TracebackType
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent
_DEFAULT_CRASH_DIR = _PROJECT_ROOT / "logs" / "crash"
_installed = False
_crash_dir = _DEFAULT_CRASH_DIR


def run_with_crash_logging(entrypoint: Callable[[], int]) -> int:
    install_crash_logging()
    try:
        return entrypoint()
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException as exc:
        path = write_crash_report(type(exc), exc, exc.__traceback__)
        print(f"Crash report written: {path}", file=sys.stderr)
        return 1


def install_crash_logging(log_dir: str | Path | None = None) -> None:
    global _crash_dir, _installed
    if log_dir is not None:
        _crash_dir = Path(log_dir)
    if _installed:
        return

    previous_excepthook = sys.excepthook

    def handle_exception(
        exc_type: type[BaseException],
        exc: BaseException,
        tb: TracebackType | None,
    ) -> None:
        if issubclass(exc_type, (KeyboardInterrupt, SystemExit)):
            previous_excepthook(exc_type, exc, tb)
            return
        path = write_crash_report(exc_type, exc, tb)
        print(f"Crash report written: {path}", file=sys.stderr)
        previous_excepthook(exc_type, exc, tb)

    sys.excepthook = handle_exception

    if hasattr(threading, "excepthook"):
        previous_threading_excepthook = threading.excepthook

        def handle_thread_exception(args: threading.ExceptHookArgs) -> None:
            if issubclass(args.exc_type, (KeyboardInterrupt, SystemExit)):
                previous_threading_excepthook(args)
                return
            context = {"thread": getattr(args.thread, "name", "unknown")}
            path = write_crash_report(args.exc_type, args.exc_value, args.exc_traceback, context)
            print(f"Crash report written: {path}", file=sys.stderr)
            previous_threading_excepthook(args)

        threading.excepthook = handle_thread_exception

    _installed = True


def write_crash_report(
    exc_type: type[BaseException],
    exc: BaseException,
    tb: TracebackType | None,
    context: dict[str, Any] | None = None,
    log_dir: str | Path | None = None,
) -> Path:
    target_dir = Path(log_dir) if log_dir is not None else _crash_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S_%f")
    path = target_dir / f"crash_{stamp}.txt"
    path.write_text(
        render_crash_report(exc_type, exc, tb, context=context),
        encoding="utf-8",
    )
    return path


def render_crash_report(
    exc_type: type[BaseException],
    exc: BaseException,
    tb: TracebackType | None,
    context: dict[str, Any] | None = None,
) -> str:
    lines = [
        "LocalMeetingCopilot Crash Report",
        "",
        f"Generated: {datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"Platform: {platform.platform()}",
        f"Machine: {platform.machine()}",
        f"Python: {sys.version}",
        f"Executable: {sys.executable}",
        f"Arguments: {sys.argv}",
    ]
    if context:
        lines.extend(["", "Context:"])
        for key, value in sorted(context.items()):
            lines.append(f"- {key}: {value}")

    lines.extend(
        [
            "",
            f"Exception: {exc_type.__name__}: {exc}",
            "",
            "Traceback:",
            "".join(traceback.format_exception(exc_type, exc, tb)).rstrip(),
            "",
        ]
    )
    return "\n".join(lines)
