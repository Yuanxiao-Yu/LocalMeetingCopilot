from __future__ import annotations

from io import StringIO

from config import AppConfig
from model_manager import (
    check_ollama_model,
    collect_model_preflight,
    expected_whisper_cache_root,
    find_whisper_model_cache,
    format_model_preflight,
    ollama_model_present,
    parse_ollama_model_names,
    run_model_check,
)


def test_parse_ollama_model_names() -> None:
    names = parse_ollama_model_names(
        "NAME ID SIZE MODIFIED\nqwen2.5:3b-instruct abc 2 GB now\nllama3:latest def 4 GB now\n"
    )

    assert names == ["qwen2.5:3b-instruct", "llama3:latest"]
    assert ollama_model_present("llama3", names)


def test_find_whisper_model_cache_detects_snapshot(tmp_path) -> None:
    cache_root = expected_whisper_cache_root("base", tmp_path)
    snapshot = cache_root / "snapshots" / "abc"
    snapshot.mkdir(parents=True)
    (snapshot / "model.bin").write_bytes(b"model")

    assert find_whisper_model_cache("base", tmp_path) == snapshot


def test_check_ollama_model_reports_missing() -> None:
    def fake_runner(_command, _timeout):
        return {
            "available": True,
            "returncode": 0,
            "stdout": "NAME ID SIZE MODIFIED\nllama3:latest def 4 GB now\n",
            "stderr": "",
        }

    check = check_ollama_model(AppConfig(ollama_model="qwen2.5:3b-instruct"), fake_runner)

    assert check.available is False
    assert check.fix_command == "ollama pull qwen2.5:3b-instruct"


def test_collect_model_preflight_lists_fix_commands(tmp_path) -> None:
    def fake_runner(command, _timeout):
        if command == ["ollama", "--version"]:
            return {"available": True, "returncode": 0, "stdout": "ollama version x", "stderr": ""}
        return {"available": True, "returncode": 0, "stdout": "NAME ID SIZE MODIFIED\n", "stderr": ""}

    report = collect_model_preflight(
        AppConfig(model_cache_dir=tmp_path, asr_model_size="base"),
        command_runner=fake_runner,
    )

    assert report["ok"] is False
    assert any("ollama pull" in command for command in report["fix_commands"])
    assert "Model preflight" in format_model_preflight(report)


def test_run_model_check_returns_nonzero_for_missing_models(tmp_path) -> None:
    def fake_runner(command, _timeout):
        if command == ["ollama", "--version"]:
            return {"available": True, "returncode": 0, "stdout": "ollama version x", "stderr": ""}
        return {"available": True, "returncode": 0, "stdout": "NAME ID SIZE MODIFIED\n", "stderr": ""}

    output = StringIO()
    config = AppConfig(model_cache_dir=tmp_path, asr_model_size="base")

    result = run_model_check(config=config, output=output, command_runner=fake_runner)

    assert result == 1
    assert "Model preflight" in output.getvalue()
