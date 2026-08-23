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
    audio = collect_audio_info(config)
    ollama = collect_ollama_info(config)
    acceleration = collect_acceleration_info(config)
    recent_logs = collect_recent_logs(config.log_dir)

    _write_json(bundle_dir / "system.json", system)
    _write_json(bundle_dir / "config.json", cfg)
    _write_json(bundle_dir / "audio_devices.json", audio)
    _write_json(bundle_dir / "ollama.json", ollama)
    _write_json(bundle_dir / "acceleration.json", acceleration)
    _write_text(bundle_dir / "git.txt", command_result_text(git))
    _write_text(bundle_dir / "python_packages.txt", command_result_text(packages))
    _write_json(bundle_dir / "recent_logs.json", recent_logs)

    report = render_report(
        {
            "system": system,
            "config": cfg,
            "git": git,
            "python_packages": packages,
            "audio": audio,
            "ollama": ollama,
            "acceleration": acceleration,
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


def collect_audio_info(config: AppConfig, system_name: str | None = None) -> dict[str, Any]:
    current_system = (system_name or platform.system()).lower()
    info: dict[str, Any] = {
        "system": current_system,
        "sounddevice": {"available": False, "devices": [], "defaults": {}, "error": ""},
        "macos_remote": {"applicable": current_system == "darwin"},
        "windows_loopback": {"applicable": current_system == "windows"},
    }
    try:
        import sounddevice

        devices = normalise_sounddevice_devices(sounddevice.query_devices())
        info["sounddevice"] = {
            "available": True,
            "devices": devices,
            "defaults": {
                "device": _json_safe(getattr(sounddevice.default, "device", None)),
                "samplerate": _json_safe(getattr(sounddevice.default, "samplerate", None)),
            },
            "inputs": [device for device in devices if int(device.get("max_input_channels", 0)) > 0],
            "outputs": [device for device in devices if int(device.get("max_output_channels", 0)) > 0],
            "selected_mic": _sounddevice_device_by_index(devices, config.mic_device_index),
            "error": "",
        }
    except Exception as exc:
        info["sounddevice"]["error"] = f"{exc.__class__.__name__}: {exc}"

    if current_system == "darwin":
        info["macos_remote"] = collect_macos_remote_info(config)
    if current_system == "windows":
        info["windows_loopback"] = collect_windows_loopback_info(config)
    return info


def normalise_sounddevice_devices(devices: Any) -> list[dict[str, Any]]:
    normalised = []
    for index, device in enumerate(devices):
        item = dict(device)
        normalised.append(
            {
                "index": index,
                "name": str(item.get("name") or ""),
                "max_input_channels": _optional_int_value(item.get("max_input_channels")),
                "max_output_channels": _optional_int_value(item.get("max_output_channels")),
                "default_samplerate": _optional_float_value(item.get("default_samplerate")),
                "hostapi": _optional_int_value(item.get("hostapi")),
            }
        )
    return normalised


def collect_macos_remote_info(config: AppConfig) -> dict[str, Any]:
    try:
        from audio_engine import _remote_input_device_candidates, _select_remote_input_device

        candidates = _remote_input_device_candidates(config)
        selected = _select_remote_input_device(config)
    except Exception as exc:
        return {
            "applicable": True,
            "available": False,
            "candidates": [],
            "selected": None,
            "error": f"{exc.__class__.__name__}: {exc}",
        }

    return {
        "applicable": True,
        "available": bool(candidates),
        "keywords": list(config.remote_device_keywords),
        "candidates": [_normalise_candidate_device(device) for device in candidates],
        "selected": _normalise_candidate_device(selected) if selected else None,
        "error": "",
    }


def collect_windows_loopback_info(config: AppConfig) -> dict[str, Any]:
    try:
        import pyaudiowpatch as pyaudio  # type: ignore[import-not-found]

        from audio_engine import (
            _default_wasapi_output_device,
            _loopback_device_candidates,
            _select_wasapi_loopback_device,
        )
    except Exception as exc:
        return {
            "applicable": True,
            "available": False,
            "candidates": [],
            "selected": None,
            "default_output": None,
            "error": f"{exc.__class__.__name__}: {exc}",
        }

    pa = pyaudio.PyAudio()
    try:
        candidates = _loopback_device_candidates(pa)
        default_output = _default_wasapi_output_device(pa, pyaudio)
        try:
            selected = _select_wasapi_loopback_device(pa, pyaudio, config.loopback_device_index)
            selected_error = ""
        except Exception as exc:
            selected = None
            selected_error = f"{exc.__class__.__name__}: {exc}"
    finally:
        pa.terminate()

    return {
        "applicable": True,
        "available": bool(candidates),
        "candidates": [_normalise_wasapi_device(device) for device in candidates],
        "selected": _normalise_wasapi_device(selected) if selected else None,
        "default_output": _normalise_wasapi_device(default_output) if default_output else None,
        "error": selected_error,
    }


def collect_ollama_info(config: AppConfig) -> dict[str, Any]:
    version = safe_run(["ollama", "--version"], timeout=5)
    models = safe_run(["ollama", "list"], timeout=8)
    try:
        from llm_refiner import LLMRefiner

        health_config = config.model_copy(
            update={"ollama_timeout_seconds": min(config.ollama_timeout_seconds, 5.0)}
        )
        health = LLMRefiner(health_config).healthcheck_sync()
    except Exception as exc:
        health = f"unavailable: {exc.__class__.__name__}: {exc}"

    return {
        "host": config.ollama_host,
        "model": config.ollama_model,
        "cli_version": version,
        "cli_models": models,
        "health": health,
        "model_present_in_list": _model_present_in_ollama_list(config.ollama_model, models),
    }


def collect_acceleration_info(config: AppConfig) -> dict[str, Any]:
    result = safe_run(
        ["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"],
        timeout=3,
    )
    apple_silicon = config.is_macos and platform.machine() == "arm64"
    return {
        "nvidia_smi": result,
        "nvidia_detected": result.get("returncode") == 0 and bool(str(result.get("stdout") or "").strip()),
        "apple_silicon": apple_silicon,
        "hint": _acceleration_hint(config, result, apple_silicon),
    }


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
    audio = data["audio"]
    ollama = data["ollama"]
    acceleration = data["acceleration"]
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
        "## Audio",
        f"- sounddevice available: {audio['sounddevice']['available']}",
        f"- input devices: {len(audio['sounddevice'].get('inputs', []))}",
        f"- output devices: {len(audio['sounddevice'].get('outputs', []))}",
        f"- selected mic: {_device_label(audio['sounddevice'].get('selected_mic'))}",
        f"- macOS remote selected: {_device_label(audio['macos_remote'].get('selected'))}",
        f"- Windows loopback selected: {_device_label(audio['windows_loopback'].get('selected'))}",
        "",
        "## Ollama",
        f"- Health: {ollama['health']}",
        f"- Model present in `ollama list`: {ollama['model_present_in_list']}",
        f"- CLI version return code: {ollama['cli_version'].get('returncode')}",
        "",
        "## Acceleration",
        f"- NVIDIA detected: {acceleration['nvidia_detected']}",
        f"- Apple Silicon: {acceleration['apple_silicon']}",
        f"- Hint: {acceleration['hint']}",
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


def _sounddevice_device_by_index(
    devices: list[dict[str, Any]],
    index: int | None,
) -> dict[str, Any] | None:
    if index is None:
        return None
    for device in devices:
        if device.get("index") == index:
            return device
    return None


def _normalise_candidate_device(device: dict[str, Any]) -> dict[str, Any]:
    return {
        "index": _optional_int_value(device.get("index")),
        "name": str(device.get("name") or ""),
        "max_input_channels": _optional_int_value(device.get("max_input_channels")),
        "max_output_channels": _optional_int_value(device.get("max_output_channels")),
        "default_samplerate": _optional_float_value(device.get("default_samplerate")),
    }


def _normalise_wasapi_device(device: dict[str, Any]) -> dict[str, Any]:
    return {
        "index": _optional_int_value(device.get("index")),
        "name": str(device.get("name") or ""),
        "is_loopback": bool(device.get("isLoopbackDevice")),
        "max_input_channels": _optional_int_value(device.get("maxInputChannels")),
        "max_output_channels": _optional_int_value(device.get("maxOutputChannels")),
        "default_samplerate": _optional_float_value(device.get("defaultSampleRate")),
    }


def _model_present_in_ollama_list(model: str, result: CommandResult) -> bool:
    if result.get("returncode") != 0:
        return False
    names = [line.split()[0] for line in str(result.get("stdout") or "").splitlines()[1:]]
    return model in names


def _acceleration_hint(config: AppConfig, nvidia_result: CommandResult, apple_silicon: bool) -> str:
    if nvidia_result.get("returncode") == 0 and str(nvidia_result.get("stdout") or "").strip():
        return "NVIDIA detected. On Windows, try LMC_ASR_DEVICE=cuda and LMC_ASR_COMPUTE_TYPE=float16."
    if apple_silicon:
        return "Apple Silicon detected. Current stable preset keeps faster-whisper on CPU int8."
    if config.is_windows:
        return "No NVIDIA GPU detected by nvidia-smi. CPU int8 is the safest default."
    return "CPU int8 is the safest default for this platform."


def _device_label(device: object) -> str:
    if not isinstance(device, dict) or not device:
        return "none"
    index = device.get("index", "?")
    name = device.get("name") or "unknown"
    return f"[{index}] {name}"


def _optional_int_value(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _optional_float_value(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _json_safe(value: object) -> object:
    if isinstance(value, tuple | list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, Path):
        return str(value)
    try:
        json.dumps(value)
    except TypeError:
        return str(value)
    return value


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
