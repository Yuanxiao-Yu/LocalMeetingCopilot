from __future__ import annotations

import json
import platform
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from config import AppConfig, load_config

CommandResult = dict[str, Any]


def run_doctor(
    config: AppConfig | None = None,
    profile: str | None = None,
    preset: str | None = None,
    style: str | None = None,
    output_dir: str | Path | None = None,
) -> int:
    cfg = config or load_config(profile=profile, preset=preset, translation_style=style)
    bundle_dir = create_diagnostics_bundle(cfg, output_dir=output_dir)
    print(f"Diagnostic bundle: {bundle_dir}")
    print(f"Report: {bundle_dir / 'report.md'}")
    return 0


def create_diagnostics_bundle(config: AppConfig, output_dir: str | Path | None = None) -> Path:
    collected_at = datetime.now().astimezone()
    bundle_dir = _bundle_dir(config, collected_at, output_dir)
    bundle_dir.mkdir(parents=True, exist_ok=True)

    system = collect_system_info(config, collected_at)
    cfg = collect_config_snapshot(config)
    git = collect_git_info(config.project_root)
    packages = safe_run([sys.executable, "-m", "pip", "freeze"], timeout=20)
    recent_logs = collect_recent_logs(config.log_dir)

    _write_json(bundle_dir / "system.json", system)
    _write_json(bundle_dir / "config.json", cfg)
    _write_text(bundle_dir / "git.txt", command_result_text(git))
    _write_text(bundle_dir / "python_packages.txt", command_result_text(packages))
    _write_json(bundle_dir / "recent_logs.json", recent_logs)

    report = render_report(
        {
            "system": system,
            "config": cfg,
            "git": git,
            "python_packages": packages,
            "recent_logs": recent_logs,
        }
    )
    _write_text(bundle_dir / "report.md", report)
    return bundle_dir


def collect_system_info(config: AppConfig, collected_at: datetime | None = None) -> dict[str, Any]:
    generated_at = collected_at or datetime.now().astimezone()
    return {
        "generated_at": generated_at.isoformat(timespec="seconds"),
        "app_name": config.app_name,
        "platform": platform.platform(),
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python_version": sys.version,
        "python_executable": sys.executable,
        "cwd": str(config.project_root),
    }


def collect_config_snapshot(config: AppConfig) -> dict[str, Any]:
    data = config.model_dump(mode="json")
    data["language_profile_label"] = config.language_profile_label
    data["model_preset_label"] = config.model_preset_label
    data["profile_terms_token_count"] = len(config.profile_terms_text.split())
    data["profile_terms_files"] = [str(path) for path in config.profile_terms_files()]
    return data


def collect_git_info(project_root: Path) -> CommandResult:
    commands = {
        "status": ["git", "status", "--short", "--branch"],
        "head": ["git", "log", "-1", "--oneline"],
        "remote": ["git", "remote", "-v"],
        "email": ["git", "config", "--get", "user.email"],
    }
    results = {}
    for name, command in commands.items():
        results[name] = safe_run(command, cwd=project_root, timeout=5)
    return {"commands": results}


def collect_recent_logs(log_dir: Path, limit: int = 20) -> list[dict[str, Any]]:
    if not log_dir.exists():
        return []

    files = [
        path
        for path in log_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in {".json", ".jsonl", ".md", ".txt", ".wav"}
    ]
    files.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    recent = []
    for path in files[:limit]:
        stat = path.stat()
        recent.append(
            {
                "path": str(path.relative_to(log_dir)),
                "suffix": path.suffix,
                "size_bytes": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(
                    timespec="seconds"
                ),
            }
        )
    return recent


def safe_run(
    command: list[str],
    cwd: str | Path | None = None,
    timeout: float = 10,
) -> CommandResult:
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
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
    except Exception as exc:
        return {
            "command": command,
            "available": False,
            "returncode": None,
            "stdout": "",
            "stderr": f"{exc.__class__.__name__}: {exc}",
        }

    return {
        "command": command,
        "available": True,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def command_result_text(result: CommandResult) -> str:
    if "commands" in result:
        parts = []
        for name, command_result in result["commands"].items():
            parts.append(f"## {name}\n{command_result_text(command_result).strip()}")
        return "\n\n".join(parts) + "\n"

    command = " ".join(str(part) for part in result.get("command", []))
    lines = [f"$ {command}", f"available: {result.get('available')}"]
    lines.append(f"returncode: {result.get('returncode')}")
    stdout = str(result.get("stdout") or "").rstrip()
    stderr = str(result.get("stderr") or "").rstrip()
    if stdout:
        lines.append("\nstdout:\n" + stdout)
    if stderr:
        lines.append("\nstderr:\n" + stderr)
    return "\n".join(lines) + "\n"


def render_report(data: dict[str, Any]) -> str:
    system = data["system"]
    config = data["config"]
    git = data["git"]
    packages = data["python_packages"]
    recent_logs = data["recent_logs"]
    git_status = _stdout_from_nested_command(git, "status") or "(empty)"
    git_head = _stdout_from_nested_command(git, "head") or "(unknown)"
    git_email = _stdout_from_nested_command(git, "email") or "(unknown)"

    lines = [
        "# LocalMeetingCopilot Doctor Report",
        "",
        "## System",
        f"- Generated: {system['generated_at']}",
        f"- Platform: {system['platform']}",
        f"- Machine: {system['machine']}",
        f"- Python: {system['python_version'].split()[0]}",
        f"- Executable: `{system['python_executable']}`",
        "",
        "## Project",
        f"- Root: `{system['cwd']}`",
        f"- Git HEAD: `{git_head}`",
        f"- Git email: `{git_email}`",
        "- Git status:",
        "```text",
        git_status.strip(),
        "```",
        "",
        "## Runtime Config",
        f"- Profile: {config['meeting_profile']} ({config['language_profile_label']})",
        f"- Preset: {config['model_preset']} ({config['model_preset_label']})",
        f"- Translation style: {config['translation_style']}",
        f"- ASR: {config['asr_model_size']} / {config['asr_device']} / {config['asr_compute_type']}",
        f"- VAD: {config['vad_mode']} / sensitivity {config['vad_sensitivity']}",
        f"- Ollama: {config['ollama_model']} at {config['ollama_host']}",
        f"- Privacy: save_reports={config['save_reports_enabled']}, privacy_mode={config['privacy_mode']}",
        "",
        "## Python Packages",
        f"- `pip freeze` return code: {packages.get('returncode')}",
        "",
        "## Recent Log Files",
    ]
    if recent_logs:
        for item in recent_logs:
            lines.append(f"- `{item['path']}` ({item['size_bytes']} bytes, {item['modified_at']})")
    else:
        lines.append("- No recent log files found.")
    lines.append("")
    return "\n".join(lines)


def _stdout_from_nested_command(result: CommandResult, key: str) -> str:
    command = result.get("commands", {}).get(key, {})
    return str(command.get("stdout") or "").strip()


def _bundle_dir(
    config: AppConfig,
    collected_at: datetime,
    output_dir: str | Path | None,
) -> Path:
    if output_dir is not None:
        return Path(output_dir)
    stamp = collected_at.strftime("%Y%m%d_%H%M%S")
    return config.log_dir / "diagnostics" / f"diagnostic_{stamp}"


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
