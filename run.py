from __future__ import annotations

import argparse

from crash_reporter import run_with_crash_logging


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
    parser.add_argument("--model-check", action="store_true", help="Check local ASR/Ollama models and exit")
    parser.add_argument("--audio-test", action="store_true", help="Run audio/VAD calibration and exit")
    parser.add_argument("--audio-test-seconds", type=float, default=12.0, help="Audio test duration")
    parser.add_argument("--support-bundle", action="store_true", help="Write a zipped support bundle")
    parser.add_argument(
        "--support-include-audio-test",
        action="store_true",
        help="Include a short live audio/VAD test in the support bundle",
    )
    parser.add_argument("--glossary-search", help="Search glossary matches for a sentence and exit")
    parser.add_argument("--glossary-add", help="Add or update one structured glossary source term")
    parser.add_argument("--glossary-zh", default="", help="Chinese target for --glossary-add")
    parser.add_argument(
        "--glossary-variants",
        default="",
        help="Comma, semicolon, or pipe separated variants for --glossary-add",
    )
    parser.add_argument("--glossary-category", default="general", help="Category for --glossary-add")
    parser.add_argument(
        "--glossary-priority",
        choices=("low", "medium", "high"),
        default="medium",
        help="Priority for --glossary-add",
    )
    parser.add_argument(
        "--glossary-profiles",
        default="",
        help="Comma, semicolon, or pipe separated profiles for --glossary-add",
    )
    parser.add_argument("--glossary-import", help="Import structured glossary terms from a CSV file")
    parser.add_argument("--glossary-file", help="Override target YAML file for glossary add/import")
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
    if args.glossary_search:
        from glossary_manager import run_glossary_search

        return run_glossary_search(
            args.glossary_search,
            config=_runtime_config_from_args(args),
        )
    if args.glossary_add:
        from glossary_manager import run_glossary_add

        return run_glossary_add(
            source=args.glossary_add,
            zh=args.glossary_zh,
            variants=args.glossary_variants,
            category=args.glossary_category,
            priority=args.glossary_priority,
            profiles=args.glossary_profiles,
            config=_runtime_config_from_args(args),
            glossary_file=args.glossary_file,
        )
    if args.glossary_import:
        from glossary_manager import run_glossary_import

        return run_glossary_import(
            args.glossary_import,
            config=_runtime_config_from_args(args),
            glossary_file=args.glossary_file,
        )
    if args.support_bundle:
        from support_bundle import run_support_bundle

        return run_support_bundle(
            config=_runtime_config_from_args(args),
            include_audio_test=args.support_include_audio_test,
            audio_test_seconds=args.audio_test_seconds,
        )
    if args.audio_test:
        from audio_test import run_audio_test

        return run_audio_test(config=_runtime_config_from_args(args), duration_seconds=args.audio_test_seconds)
    if args.model_check:
        from model_manager import run_model_check

        return run_model_check(config=_runtime_config_from_args(args))
    if args.doctor:
        from diagnostics import run_doctor

        return run_doctor(profile=args.profile, preset=args.preset, style=args.style)
    if args.check:
        from main import run_environment_check

        return run_environment_check(profile=args.profile, preset=args.preset, style=args.style)

    from main import run_app

    return run_app(args)


def _runtime_config_from_args(args: argparse.Namespace):
    from config import load_config

    config = load_config(profile=args.profile, preset=args.preset, translation_style=args.style)
    if args.privacy:
        config.privacy_mode = True
        config.save_reports_enabled = False
    if args.debug_audio:
        config.debug_audio_enabled = True
        config.ensure_directories()
    if args.no_mic_track:
        config.capture_mic_enabled = False
    if args.no_remote_track:
        config.capture_remote_enabled = False
    return config


if __name__ == "__main__":
    raise SystemExit(run_with_crash_logging(main))
