from __future__ import annotations

import json
import zipfile
from pathlib import Path

from config import AppConfig
from support_bundle import create_support_bundle, run_support_bundle


def test_create_support_bundle_writes_manifest_outputs_and_zip(monkeypatch, tmp_path) -> None:
    def fake_doctor(_config: AppConfig, output_dir: str | Path | None = None) -> Path:
        doctor_dir = Path(output_dir)
        doctor_dir.mkdir(parents=True)
        (doctor_dir / "report.md").write_text("# fake doctor\n", encoding="utf-8")
        return doctor_dir

    def ok_step(_config: AppConfig, output) -> int:
        print("ok stdout", file=output)
        return 0

    monkeypatch.setattr("support_bundle.create_diagnostics_bundle", fake_doctor)

    config = AppConfig(log_dir=tmp_path / "logs")
    bundle = create_support_bundle(
        config,
        output_dir=tmp_path / "support",
        steps={"environment_check": ok_step, "model_check": ok_step},
    )

    manifest = json.loads((bundle / "support_manifest.json").read_text(encoding="utf-8"))
    zip_path = Path(manifest["zip_path"])

    assert manifest["ok"] is True
    assert [step["name"] for step in manifest["steps"]] == ["environment_check", "model_check"]
    assert (bundle / "commands" / "environment_check.stdout.txt").read_text(
        encoding="utf-8"
    ).strip() == "ok stdout"
    assert (bundle / "doctor" / "report.md").exists()
    assert zip_path.exists()
    with zipfile.ZipFile(zip_path) as archive:
        assert "support_manifest.json" in archive.namelist()
        assert "doctor/report.md" in archive.namelist()


def test_create_support_bundle_records_failing_step(monkeypatch, tmp_path) -> None:
    def fake_doctor(_config: AppConfig, output_dir: str | Path | None = None) -> Path:
        doctor_dir = Path(output_dir)
        doctor_dir.mkdir(parents=True)
        return doctor_dir

    def failing_step(_config: AppConfig, output) -> int:
        print("missing model", file=output)
        return 1

    monkeypatch.setattr("support_bundle.create_diagnostics_bundle", fake_doctor)

    bundle = create_support_bundle(
        AppConfig(log_dir=tmp_path / "logs"),
        output_dir=tmp_path / "support",
        steps={"model_check": failing_step},
    )

    manifest = json.loads((bundle / "support_manifest.json").read_text(encoding="utf-8"))

    assert manifest["ok"] is False
    assert manifest["steps"][0]["returncode"] == 1
    assert manifest["steps"][0]["ok"] is False


def test_run_support_bundle_returns_nonzero_when_manifest_needs_attention(monkeypatch, tmp_path) -> None:
    def fake_doctor(_config: AppConfig, output_dir: str | Path | None = None) -> Path:
        doctor_dir = Path(output_dir)
        doctor_dir.mkdir(parents=True)
        return doctor_dir

    monkeypatch.setattr("support_bundle.create_diagnostics_bundle", fake_doctor)

    code = run_support_bundle(
        config=AppConfig(log_dir=tmp_path / "logs"),
        output_dir=tmp_path / "support",
        steps={"model_check": lambda _config, _output: 1},
    )

    assert code == 1
