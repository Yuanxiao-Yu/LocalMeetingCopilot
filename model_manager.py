from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, TextIO

from config import AppConfig, load_config

CommandResult = dict[str, Any]
CommandRunner = Callable[[list[str], float], CommandResult]


@dataclass(slots=True)
class ModelCheck:
    key: str
    label: str
    required: str
    available: bool
    status: str
    detail: str = ""
    fix_command: str = ""
    path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_model_check(
    config: AppConfig | None = None,
    profile: str | None = None,
    preset: str | None = None,
    style: str | None = None,
    output: TextIO | None = None,
    command_runner: CommandRunner | None = None,
) -> int:
    cfg = config or load_config(profile=profile, preset=preset, translation_style=style)
    report = collect_model_preflight(cfg, command_runner=command_runner)
    print(format_model_preflight(report), file=output or sys.stdout)
    return 0 if report["ok"] else 1


def collect_model_preflight(
    config: AppConfig,
    command_runner: CommandRunner | None = None,
) -> dict[str, Any]:
    runner = command_runner or run_command
    checks = [
        check_python_package("faster_whisper", "faster-whisper", "python -m pip install -r requirements.txt"),
        check_whisper_model_cache(config),
        check_python_package("ollama", "ollama Python package", "python -m pip install -r requirements.txt"),
        check_ollama_cli(runner),
        check_ollama_model(config, runner),
    ]
    fix_commands = _unique_nonempty(check.fix_command for check in checks if not check.available)
    return {
        "ok": all(check.available for check in checks),
        "checks": [check.to_dict() for check in checks],
        "fix_commands": fix_commands,
    }


def format_model_preflight(report: dict[str, Any]) -> str:
    lines = ["Model preflight", ""]
    for check in report.get("checks", []):
        marker = "OK" if check.get("available") else "MISSING"
        label = check.get("label", "unknown")
        required = check.get("required", "")
        status = check.get("status", "")
        lines.append(f"- {marker} {label}: {required}")
        if status:
            lines.append(f"  {status}")
        if check.get("path"):
            lines.append(f"  path: {check['path']}")
        if not check.get("available") and check.get("fix_command"):
            lines.append(f"  fix: {check['fix_command']}")

    fix_commands = report.get("fix_commands", [])
    if fix_commands:
        lines.extend(["", "Suggested fix commands:"])
        for command in fix_commands:
            lines.append(f"  {command}")
    lines.append("")
    lines.append(f"Overall: {'OK' if report.get('ok') else 'needs attention'}")
    return "\n".join(lines)


def check_python_package(module_name: str, label: str, fix_command: str) -> ModelCheck:
    available = importlib.util.find_spec(module_name) is not None
    return ModelCheck(
        key=f"python:{module_name}",
        label=label,
        required=module_name,
        available=available,
        status="Python import is available" if available else "Python import is missing",
        fix_command="" if available else fix_command,
    )


def check_whisper_model_cache(config: AppConfig) -> ModelCheck:
    cache = find_whisper_model_cache(config.asr_model_size, config.model_cache_dir)
    available = cache is not None
    return ModelCheck(
        key="faster-whisper-model",
        label="faster-whisper ASR model cache",
        required=config.asr_model_size,
        available=available,
        status="model cache found" if available else "model will download on first ASR use",
        fix_command="" if available else whisper_prefetch_command(config),
        path=str(cache) if cache else str(expected_whisper_cache_root(config.asr_model_size, config.model_cache_dir)),
    )


def check_ollama_cli(command_runner: CommandRunner) -> ModelCheck:
    result = command_runner(["ollama", "--version"], 5)
    available = result.get("available") is True and result.get("returncode") == 0
    detail = str(result.get("stdout") or result.get("stderr") or "").strip()
    return ModelCheck(
        key="ollama-cli",
        label="Ollama CLI",
        required="ollama",
        available=available,
        status=detail or ("ollama CLI available" if available else "ollama CLI unavailable"),
        fix_command="" if available else "Install and open Ollama, then make sure `ollama` is on PATH",
    )


def check_ollama_model(config: AppConfig, command_runner: CommandRunner) -> ModelCheck:
    result = command_runner(["ollama", "list"], 8)
    names = parse_ollama_model_names(str(result.get("stdout") or ""))
    available = result.get("available") is True and result.get("returncode") == 0
    present = available and ollama_model_present(config.ollama_model, names)
    if present:
        status = f"model found in ollama list ({len(names)} installed)"
    elif available:
        status = f"model missing; installed models: {', '.join(names) or 'none'}"
    else:
        status = str(result.get("stderr") or "ollama list failed").strip()

    return ModelCheck(
        key="ollama-model",
        label="Ollama translation model",
        required=config.ollama_model,
        available=present,
        status=status,
        fix_command="" if present else f"ollama pull {config.ollama_model}",
    )


def find_whisper_model_cache(model_size: str, model_cache_dir: Path) -> Path | None:
    model_path = Path(model_size)
    if model_path.exists():
        return model_path
    cache_root = expected_whisper_cache_root(model_size, model_cache_dir)
    if not cache_root.exists():
        return None
    for snapshot in (cache_root / "snapshots").glob("*"):
        if (snapshot / "model.bin").exists():
            return snapshot
    if (cache_root / "model.bin").exists():
        return cache_root
    return None


def expected_whisper_cache_root(model_size: str, model_cache_dir: Path) -> Path:
    repo = faster_whisper_repo_name(model_size)
    return model_cache_dir / ("models--" + repo.replace("/", "--"))


def faster_whisper_repo_name(model_size: str) -> str:
    if "/" in model_size:
        return model_size
    return f"Systran/faster-whisper-{model_size}"


def whisper_prefetch_command(config: AppConfig) -> str:
    code = (
        "from faster_whisper import WhisperModel; "
        f"WhisperModel({config.asr_model_size!r}, "
        f"device={config.asr_device!r}, "
        f"compute_type={config.asr_compute_type!r}, "
        f"download_root={str(config.model_cache_dir)!r})"
    )
    return f"{Path(sys.executable).name} -c {json.dumps(code)}"


def parse_ollama_model_names(output: str) -> list[str]:
    names = []
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped or stripped.lower().startswith("name "):
            continue
        names.append(stripped.split()[0])
    return names


def ollama_model_present(required: str, installed: list[str]) -> bool:
    if required in installed:
        return True
    if ":" not in required:
        return f"{required}:latest" in installed
    return False


def run_command(command: list[str], timeout: float) -> CommandResult:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        return {
            "command": command,
            "available": False,
            "returncode": None,
            "stdout": "",
            "stderr": str(exc),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": command,
            "available": True,
            "returncode": None,
            "stdout": exc.stdout or "",
            "stderr": f"Timed out after {timeout}s",
        }
    return {
        "command": command,
        "available": True,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def _unique_nonempty(values: Iterable[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
