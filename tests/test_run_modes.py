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
