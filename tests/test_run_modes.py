from run import parse_args


def test_parse_mac_live_mode() -> None:
    args = parse_args(["--mac-live"])

    assert args.mode == "mac_live"


def test_parse_language_profile() -> None:
    args = parse_args(["--mac-live", "--profile", "de"])

    assert args.mode == "mac_live"
    assert args.profile == "de"


def test_parse_preset_style_and_privacy_flags() -> None:
    args = parse_args(
        [
            "--mac-live",
            "--profile",
            "de",
            "--preset",
            "fast",
            "--style",
            "meeting",
            "--privacy",
            "--no-remote-track",
        ]
    )

    assert args.preset == "fast"
    assert args.style == "meeting"
    assert args.privacy
    assert args.no_remote_track


def test_parse_doctor_flag() -> None:
    args = parse_args(["--doctor", "--profile", "de"])

    assert args.doctor
    assert args.profile == "de"


def test_parse_audio_test_flags() -> None:
    args = parse_args(["--audio-test", "--audio-test-seconds", "3", "--no-mic-track"])

    assert args.audio_test
    assert args.audio_test_seconds == 3
    assert args.no_mic_track


def test_parse_model_check_flag() -> None:
    args = parse_args(["--model-check", "--preset", "fast"])

    assert args.model_check
    assert args.preset == "fast"


def test_parse_support_bundle_flags() -> None:
    args = parse_args(
        [
            "--support-bundle",
            "--support-include-audio-test",
            "--audio-test-seconds",
            "4",
        ]
    )

    assert args.support_bundle
    assert args.support_include_audio_test
    assert args.audio_test_seconds == 4
