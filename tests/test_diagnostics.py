from __future__ import annotations

import json
import sys

from config import AppConfig
from diagnostics import (
    collect_config_snapshot,
    collect_recent_logs,
    collect_system_info,
    command_result_text,
    create_diagnostics_bundle,
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


def test_create_diagnostics_bundle_writes_core_files(tmp_path) -> None:
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
    assert (bundle / "config.json").exists()
    assert (bundle / "git.txt").exists()
    assert (bundle / "python_packages.txt").exists()
    assert collect_system_info(config)["app_name"] == "LocalMeetingCopilot"
