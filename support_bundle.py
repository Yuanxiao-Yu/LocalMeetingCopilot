from __future__ import annotations

import contextlib
import io
import json
import shutil
import sys
import traceback
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import TextIO

from config import AppConfig, load_config
from diagnostics import create_diagnostics_bundle

SupportStep = Callable[[AppConfig, TextIO], int]


@dataclass(slots=True)
class SupportBundleStep:
    name: str
    returncode: int
    stdout_file: str
    stderr_file: str
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def run_support_bundle(
    config: AppConfig | None = None,
    profile: str | None = None,
    preset: str | None = None,
    style: str | None = None,
    output_dir: str | Path | None = None,
    include_audio_test: bool = False,
    audio_test_seconds: float = 5.0,
    output: TextIO | None = None,
    steps: dict[str, SupportStep] | None = None,
) -> int:
    cfg = config or load_config(profile=profile, preset=preset, translation_style=style)
    bundle_dir = create_support_bundle(
        cfg,
        output_dir=output_dir,
        include_audio_test=include_audio_test,
        audio_test_seconds=audio_test_seconds,
        steps=steps,
    )
    manifest = json.loads((bundle_dir / "support_manifest.json").read_text(encoding="utf-8"))
    out = output or sys.stdout
    print(f"Support bundle: {bundle_dir}", file=out)
    print(f"Zip: {manifest['zip_path']}", file=out)
    print(f"Overall: {'OK' if manifest['ok'] else 'needs attention'}", file=out)
    return 0 if manifest["ok"] else 1


def create_support_bundle(
    config: AppConfig,
    output_dir: str | Path | None = None,
    include_audio_test: bool = False,
    audio_test_seconds: float = 5.0,
    steps: dict[str, SupportStep] | None = None,
) -> Path:
    collected_at = datetime.now().astimezone()
    bundle_dir = _support_bundle_dir(config, collected_at, output_dir)
    bundle_dir.mkdir(parents=True, exist_ok=True)
    command_dir = bundle_dir / "commands"
    command_dir.mkdir(exist_ok=True)

    step_map = steps or _default_steps(include_audio_test, audio_test_seconds)
    results: list[SupportBundleStep] = []
    for name, step in step_map.items():
        results.append(_run_step(name, step, config, command_dir))

    doctor_dir = bundle_dir / "doctor"
    create_diagnostics_bundle(config, output_dir=doctor_dir)

    zip_path = _zip_path_for_bundle(bundle_dir)
    manifest = {
        "generated_at": collected_at.isoformat(timespec="seconds"),
        "app_name": config.app_name,
        "profile": config.meeting_profile,
        "preset": config.model_preset,
        "translation_style": config.translation_style,
        "privacy_note": (
            "Support bundles include environment metadata, device names, command output, "
            "doctor JSON files, and recent log file metadata. They do not include raw audio "
            "unless the user separately enabled debug audio logs."
        ),
        "include_audio_test": include_audio_test,
        "audio_test_seconds": audio_test_seconds if include_audio_test else 0,
        "steps": [asdict(result) | {"ok": result.ok} for result in results],
        "doctor_dir": "doctor",
        "zip_path": str(zip_path),
    }
    manifest["ok"] = all(result.ok for result in results)
    manifest_path = bundle_dir / "support_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _zip_bundle(bundle_dir)
    return bundle_dir


def _default_steps(include_audio_test: bool, audio_test_seconds: float) -> dict[str, SupportStep]:
    from audio_test import run_audio_test
    from main import run_environment_check
    from model_manager import run_model_check

    steps: dict[str, SupportStep] = {
        "environment_check": lambda config, output: run_environment_check(config=config),
        "model_check": lambda config, output: run_model_check(config=config, output=output),
    }
    if include_audio_test:
        steps["audio_test"] = lambda config, output: run_audio_test(
            config=config,
            duration_seconds=audio_test_seconds,
            output=output,
        )
    return steps


def _run_step(
    name: str,
    step: SupportStep,
    config: AppConfig,
    command_dir: Path,
) -> SupportBundleStep:
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    error = ""
    returncode = 1
    try:
        with contextlib.redirect_stdout(stdout_buffer), contextlib.redirect_stderr(stderr_buffer):
            returncode = int(step(config, stdout_buffer))
    except Exception as exc:
        error = f"{exc.__class__.__name__}: {exc}"
        stderr_buffer.write(traceback.format_exc())

    stdout_path = command_dir / f"{name}.stdout.txt"
    stderr_path = command_dir / f"{name}.stderr.txt"
    stdout_path.write_text(stdout_buffer.getvalue(), encoding="utf-8")
    stderr_path.write_text(stderr_buffer.getvalue(), encoding="utf-8")
    return SupportBundleStep(
        name=name,
        returncode=returncode,
        stdout_file=str(stdout_path.relative_to(command_dir.parent)),
        stderr_file=str(stderr_path.relative_to(command_dir.parent)),
        error=error,
    )


def _zip_bundle(bundle_dir: Path) -> Path:
    archive_base = bundle_dir.with_suffix("")
    archive_path = Path(shutil.make_archive(str(archive_base), "zip", bundle_dir))
    return archive_path


def _zip_path_for_bundle(bundle_dir: Path) -> Path:
    return bundle_dir.with_suffix(".zip")


def _support_bundle_dir(
    config: AppConfig,
    collected_at: datetime,
    output_dir: str | Path | None,
) -> Path:
    if output_dir is not None:
        return Path(output_dir)
    stamp = collected_at.strftime("%Y%m%d_%H%M%S")
    return config.log_dir / "support" / f"support_{stamp}"
