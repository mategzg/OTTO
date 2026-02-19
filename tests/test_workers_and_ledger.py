from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import workers.coder_cli as coder_cli
import workers.jack_stub as jack_stub


def _load_append_ledger_module() -> object:
    module_path = Path(__file__).resolve().parents[1] / "scripts" / "append_ledger.py"
    spec = importlib.util.spec_from_file_location("append_ledger_module", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _seed_profiles(root: Path, content: dict) -> None:
    workers_dir = root / "workers"
    workers_dir.mkdir(parents=True, exist_ok=True)
    (workers_dir / "coder_profiles.json").write_text(
        json.dumps(content, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def test_profile_missing_falls_back_to_dropzone(tmp_path: Path, monkeypatch) -> None:
    _seed_profiles(
        tmp_path,
        {
            "default_profile": "manual",
            "profiles": {"manual": {"args": [], "cmd": "", "timeout_sec": 0}},
        },
    )
    monkeypatch.delenv("CODER_PROFILE", raising=False)
    monkeypatch.delenv("CODER_CMD", raising=False)
    monkeypatch.delenv("CODER_ARGS", raising=False)

    out_path = tmp_path / "out" / "coder.txt"
    result = coder_cli.run(
        prompt="Implementa refactor sin secretos",
        out_path=out_path,
        root=tmp_path,
        task_id="task-profile-missing",
        timeout_sec=0,
        poll_interval_sec=0,
    )

    prompt_file = tmp_path / "dropzone" / "prompts" / "task-profile-missing.md"
    assert result["status"] == "needs_input"
    assert prompt_file.exists()
    assert "status: needs_input" in prompt_file.read_text(encoding="utf-8")


def test_dropzone_timeout_returns_needs_input(tmp_path: Path, monkeypatch) -> None:
    _seed_profiles(
        tmp_path,
        {
            "default_profile": "missing",
            "profiles": {"missing": {"args": [], "cmd": "definitely-not-installed", "timeout_sec": 0}},
        },
    )
    monkeypatch.delenv("CODER_PROFILE", raising=False)
    monkeypatch.delenv("CODER_CMD", raising=False)

    out_path = tmp_path / "out" / "coder-timeout.txt"
    result = coder_cli.run(
        prompt="Analiza este batch",
        out_path=out_path,
        root=tmp_path,
        task_id="task-timeout",
        timeout_sec=0,
        poll_interval_sec=0,
    )

    assert result["status"] == "needs_input"
    assert "task_id=task-timeout" in out_path.read_text(encoding="utf-8")


def test_subprocess_success_captures_output(tmp_path: Path, monkeypatch) -> None:
    _seed_profiles(
        tmp_path,
        {
            "default_profile": "codex",
            "profiles": {"codex": {"args": ["--fast"], "cmd": "codex", "timeout_sec": 5}},
        },
    )
    monkeypatch.setenv("CODER_PROFILE", "codex")
    monkeypatch.delenv("CODER_CMD", raising=False)
    monkeypatch.delenv("CODER_ARGS", raising=False)
    monkeypatch.setattr(coder_cli.shutil, "which", lambda _: "/usr/bin/codex")

    def fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
        return subprocess.CompletedProcess(
            args=kwargs.get("args", args[0] if args else []),
            returncode=0,
            stdout="ok stdout",
            stderr="ok stderr",
        )

    monkeypatch.setattr(coder_cli.subprocess, "run", fake_run)

    out_path = tmp_path / "out" / "coder-success.md"
    result = coder_cli.run(
        prompt="Genera reporte",
        out_path=out_path,
        root=tmp_path,
        task_id="task-subprocess",
    )

    assert result["status"] == "ok"
    content = out_path.read_text(encoding="utf-8")
    assert "status: ok" in content
    assert "ok stdout" in content
    assert "ok stderr" in content


def test_no_secrets_in_logs(tmp_path: Path, monkeypatch) -> None:
    _seed_profiles(
        tmp_path,
        {
            "default_profile": "manual",
            "profiles": {"manual": {"args": [], "cmd": "", "timeout_sec": 0}},
        },
    )
    monkeypatch.delenv("CODER_PROFILE", raising=False)
    monkeypatch.delenv("CODER_CMD", raising=False)

    coder_cli.run(
        prompt="mi token sk-abcdef12345678 y api_key=topsecret no deben quedar en log",
        out_path=tmp_path / "out" / "secrets.md",
        root=tmp_path,
        task_id="task-secrets",
        timeout_sec=0,
        poll_interval_sec=0,
    )

    log_text = (tmp_path / "logs" / "activity.ndjson").read_text(encoding="utf-8")
    assert "sk-abcdef12345678" not in log_text.lower()
    assert "api_key" not in log_text.lower()


def test_jack_rejects_non_sg_queries(tmp_path: Path) -> None:
    (tmp_path / "docs" / "empresa").mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs" / "empresa" / "JACK_URL.txt").write_text(
        "https://chatgpt.com/g/gpt-jack", encoding="utf-8"
    )

    result = jack_stub.request(
        prompt="Busca vuelos baratos a Cusco",
        root=tmp_path,
        task_id="jack-non-sg",
    )

    assert result["status"] == "rejected"
    assert result["reason"] == "non_sg_query"


def test_jack_writes_request_file_deterministically(tmp_path: Path) -> None:
    (tmp_path / "docs" / "empresa").mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs" / "empresa" / "JACK_URL.txt").write_text(
        "https://chatgpt.com/g/gpt-jack", encoding="utf-8"
    )

    result = jack_stub.request(
        prompt="Necesito criterio SG de cotizacion para proveedor de acabados",
        root=tmp_path,
        task_id="jack-sg-001",
    )

    expected = tmp_path / "docs" / "_inbox" / "jack_requests" / "jack-sg-001.md"
    assert result["status"] == "needs_browser"
    assert result["request_file"] == expected.as_posix()
    content = expected.read_text(encoding="utf-8")
    assert "task_id: jack-sg-001" in content
    assert "status: needs_browser" in content


def test_append_ledger_deduplicates_and_sorts_desc(tmp_path: Path) -> None:
    append_ledger = _load_append_ledger_module()

    row_a = {
        "fecha": "2026-02-10",
        "empresa": "A Corp",
        "contacto": "a@corp.com",
        "canal": "telegram",
        "ciudad": "Lima",
        "proyecto": "Proyecto A",
        "archivo_doc": "docs/empresa/leads/a.md",
    }
    row_b = {
        "fecha": "2026-02-11",
        "empresa": "B Corp",
        "contacto": "b@corp.com",
        "canal": "whatsapp",
        "ciudad": "Arequipa",
        "proyecto": "Proyecto B",
        "archivo_doc": "docs/empresa/leads/b.md",
    }

    assert append_ledger.append_row(tmp_path, "leads", row_a) is True
    assert append_ledger.append_row(tmp_path, "leads", row_b) is True
    assert append_ledger.append_row(tmp_path, "leads", row_b) is False

    ledger_text = (tmp_path / "docs" / "empresa" / "ledger.md").read_text(encoding="utf-8")
    assert ledger_text.count("B Corp") == 1
    assert ledger_text.index("2026-02-11") < ledger_text.index("2026-02-10")
