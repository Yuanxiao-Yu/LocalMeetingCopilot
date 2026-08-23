from __future__ import annotations

import argparse

from diagnostics import run_doctor
from main import run_app, run_environment_check


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="LocalMeetingCopilot")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--mock", action="store_true", help="Run the local scripted meeting demo")
    mode.add_argument("--mic", action="store_true", help="Run local microphone capture with VAD")
    mode.add_argument("--live", action="store_true", help="Run Windows mic + WASAPI loopback capture")
    mode.add_argument("--mac-live", action="store_true", help="Run macOS mic + virtual remote input")
    mode.add_argument("--wav", help="Transcribe and translate a WAV/audio file")
    parser.add_argument(
        "--profile",
        choices=("de", "en", "de-en"),
        help="Meeting language channel: pure German, pure English, or mixed German/English",
    )
    parser.add_argument(
        "--preset",
        choices=("fast", "balanced", "accurate"),
        help="ASR speed/accuracy preset",
    )
    parser.add_argument(
        "--style",
        choices=("literal", "meeting", "natural"),
        help="Chinese translation style",
    )
    parser.add_argument("--privacy", action="store_true", help="Do not write reports to disk")
    parser.add_argument("--debug-audio", action="store_true", help="Save completed speech chunks as WAV")
    parser.add_argument("--no-mic-track", action="store_true", help="Disable local microphone track")
    parser.add_argument("--no-remote-track", action="store_true", help="Disable remote/loopback track")
    parser.add_argument("--check", action="store_true", help="Run environment checks and exit")
    parser.add_argument("--doctor", action="store_true", help="Write a shareable diagnostics bundle")
    parser.add_argument("--no-autostart", dest="autostart", action="store_false")
    parser.set_defaults(autostart=True)
    args = parser.parse_args(argv)
    if args.mac_live:
        args.mode = "mac_live"
    elif args.live:
        args.mode = "live"
    elif args.mic:
        args.mode = "mic"
    else:
        args.mode = "mock"
    return args


def main() -> int:
    args = parse_args()
    if args.doctor:
        return run_doctor(profile=args.profile, preset=args.preset, style=args.style)
    if args.check:
        return run_environment_check(profile=args.profile, preset=args.preset, style=args.style)
    return run_app(args)


if __name__ == "__main__":
    raise SystemExit(main())
