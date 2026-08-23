from __future__ import annotations

import json
import sys

from config import AppConfig
from diagnostics import (
    collect_audio_info,
    collect_config_snapshot,
    collect_ollama_info,
    collect_recent_logs,
    collect_system_info,
    command_result_text,
    create_diagnostics_bundle,
    normalise_sounddevice_devices,
    safe_run,
)


def test_safe_run_success() -> None:
    result = safe_run([sys.executable, "-c", "print('doctor-ok')"])

    assert result["available"] is True
    assert result["returncode"] == 0
    assert result["stdout"].strip() == "doctor-ok"


def test_command_result_text_formats_nested_results() -> None:
    text = command_result_text(
        {
            "commands": {
                "status": {
                    "command": ["git", "status"],
                    "available": True,
                    "returncode": 0,
                    "stdout": "clean\n",
                    "stderr": "",
                }
            }
        }
    )

    assert "## status" in text
    assert "$ git status" in text
    assert "clean" in text


def test_config_snapshot_adds_derived_fields(tmp_path) -> None:
    config = AppConfig(
        log_dir=tmp_path / "logs",
        model_cache_dir=tmp_path / "models",
        profile_terms_dir=tmp_path / "profiles",
        custom_terms_file=tmp_path / "profiles" / "custom_terms.txt",
    )

    snapshot = collect_config_snapshot(config)

    assert snapshot["language_profile_label"]
    assert snapshot["model_preset_label"]
    assert snapshot["profile_terms_files"]


def test_recent_logs_only_records_metadata(tmp_path) -> None:
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "meeting.md").write_text("private transcript text", encoding="utf-8")

    recent = collect_recent_logs(log_dir)

    assert recent[0]["path"] == "meeting.md"
    assert "private transcript text" not in json.dumps(recent)


def test_normalise_sounddevice_devices_keeps_stable_fields() -> None:
    devices = [
        {
            "name": "Built-in Microphone",
            "max_input_channels": 1,
            "max_output_channels": 0,
            "default_samplerate": 48000.0,
            "hostapi": 0,
            "extra": "ignored",
        }
    ]

    normalised = normalise_sounddevice_devices(devices)

    assert normalised == [
        {
            "index": 0,
            "name": "Built-in Microphone",
            "max_input_channels": 1,
            "max_output_channels": 0,
            "default_samplerate": 48000.0,
            "hostapi": 0,
        }
    ]


def test_collect_audio_info_records_sounddevice_error(monkeypatch) -> None:
    import sounddevice

    def fake_query_devices():
        raise RuntimeError("no devices")

    monkeypatch.setattr(sounddevice, "query_devices", fake_query_devices)

    audio = collect_audio_info(AppConfig(), system_name="linux")

    assert audio["sounddevice"]["available"] is False
    assert "RuntimeError" in audio["sounddevice"]["error"]


def test_collect_ollama_info_marks_model_from_list(monkeypatch) -> None:
    import diagnostics

    def fake_safe_run(command, cwd=None, timeout=10):
        if command == ["ollama", "list"]:
            return {
                "command": command,
                "available": True,
                "returncode": 0,
                "stdout": "NAME ID SIZE MODIFIED\nqwen2.5:3b-instruct abc 1 GB now\n",
                "stderr": "",
            }
        return {
            "command": command,
            "available": True,
            "returncode": 0,
            "stdout": "ollama version 0.0.0\n",
            "stderr": "",
        }

    class FakeRefiner:
        def __init__(self, config):
            self.config = config

        def healthcheck_sync(self):
            return "正常"

    monkeypatch.setattr(diagnostics, "safe_run", fake_safe_run)
    monkeypatch.setattr("llm_refiner.LLMRefiner", FakeRefiner)

    info = collect_ollama_info(AppConfig())

    assert info["health"] == "正常"
    assert info["model_present_in_list"] is True


def test_create_diagnostics_bundle_writes_core_files(monkeypatch, tmp_path) -> None:
    import diagnostics

    command_result = {
        "command": ["mock"],
        "available": True,
        "returncode": 0,
        "stdout": "",
        "stderr": "",
    }
    monkeypatch.setattr(
        diagnostics,
        "collect_audio_info",
        lambda _config: {
            "sounddevice": {"available": True, "inputs": [], "outputs": [], "selected_mic": None},
            "macos_remote": {"selected": None},
            "windows_loopback": {"selected": None},
        },
    )
    monkeypatch.setattr(
        diagnostics,
        "collect_ollama_info",
        lambda _config: {
            "health": "正常",
            "model_present_in_list": True,
            "cli_version": command_result,
        },
    )
    monkeypatch.setattr(
        diagnostics,
        "collect_acceleration_info",
        lambda _config: {"nvidia_detected": False, "apple_silicon": False, "hint": "CPU"},
    )
    monkeypatch.setattr(diagnostics, "safe_run", lambda *args, **kwargs: command_result)

    config = AppConfig(
        project_root=tmp_path,
        log_dir=tmp_path / "logs",
        model_cache_dir=tmp_path / "models",
        profile_terms_dir=tmp_path / "profiles",
        custom_terms_file=tmp_path / "profiles" / "custom_terms.txt",
    )

    bundle = create_diagnostics_bundle(config, output_dir=tmp_path / "doctor")

    assert (bundle / "report.md").exists()
    assert (bundle / "system.json").exists()
    assert (bundle / "audio_devices.json").exists()
    assert (bundle / "ollama.json").exists()
    assert (bundle / "config.json").exists()
    assert (bundle / "git.txt").exists()
    assert (bundle / "python_packages.txt").exists()
    assert collect_system_info(config)["app_name"] == "LocalMeetingCopilot"
