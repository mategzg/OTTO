from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

from hq_logging import append_activity, sanitize_detail, utc_now_iso

ROOT = Path(__file__).resolve().parents[1]


def _ensure_dropzone(root: Path) -> tuple[Path, Path]:
    prompts = root / "dropzone" / "prompts"
    results = root / "dropzone" / "results"
    prompts.mkdir(parents=True, exist_ok=True)
    results.mkdir(parents=True, exist_ok=True)
    return prompts, results


def _default_profiles() -> dict[str, Any]:
    return {
        "default_profile": "manual",
        "profiles": {
            "manual": {
                "args": [],
                "cmd": "",
                "timeout_sec": 90,
            }
        },
    }


def _load_profiles(root: Path) -> dict[str, Any]:
    path = root / "workers" / "coder_profiles.json"
    if not path.exists():
        return _default_profiles()

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return _default_profiles()

    if not isinstance(data, dict):
        return _default_profiles()
    if not isinstance(data.get("profiles"), dict):
        return _default_profiles()
    return data


def _split_args(raw: str) -> list[str]:
    if not raw.strip():
        return []
    try:
        return shlex.split(raw)
    except ValueError:
        return []


def _front_matter(task_id: str, created_at: str, kind: str, status: str) -> str:
    return (
        "---\n"
        f"task_id: {task_id}\n"
        f"created_at: {created_at}\n"
        f"kind: {kind}\n"
        f"status: {status}\n"
        "---\n"
    )


def _write_markdown_handoff(path: Path, task_id: str, kind: str, status: str, body: str) -> None:
    created_at = utc_now_iso()
    text = _front_matter(task_id=task_id, created_at=created_at, kind=kind, status=status) + "\n" + body.strip() + "\n"
    path.write_text(text, encoding="utf-8")


def _extract_status_from_markdown(path: Path) -> str:
    content = path.read_text(encoding="utf-8")
    in_header = False
    for line in content.splitlines():
        line = line.strip()
        if line == "---" and not in_header:
            in_header = True
            continue
        if line == "---" and in_header:
            break
        if in_header and line.startswith("status:"):
            value = line.split(":", 1)[1].strip()
            if value in {"ok", "error", "needs_input"}:
                return value
    return "ok"


def _resolve_runtime(root: Path, timeout_sec: int | None) -> dict[str, Any]:
    profiles_data = _load_profiles(root)
    profiles = profiles_data.get("profiles", {})

    env_profile = os.getenv("CODER_PROFILE", "").strip()
    env_cmd = os.getenv("CODER_CMD", "").strip()
    env_args = _split_args(os.getenv("CODER_ARGS", ""))

    default_profile = str(profiles_data.get("default_profile", "manual")).strip() or "manual"
    profile_name = env_profile or default_profile
    profile = profiles.get(profile_name, {}) if isinstance(profiles, dict) else {}

    cmd = env_cmd or str(profile.get("cmd", "")).strip()
    args = env_args or list(profile.get("args", []))

    resolved_timeout: int
    if timeout_sec is not None:
        resolved_timeout = max(0, int(timeout_sec))
    else:
        try:
            resolved_timeout = max(0, int(profile.get("timeout_sec", 90)))
        except (TypeError, ValueError):
            resolved_timeout = 90

    return {
        "args": [str(item) for item in args],
        "cmd": cmd,
        "profile_name": profile_name,
        "timeout_sec": resolved_timeout,
    }


def _manual_fallback(
    *,
    root: Path,
    prompt: str,
    out_path: Path,
    task_id: str,
    timeout_sec: int,
    poll_interval_sec: float,
    reason: str,
) -> dict[str, str]:
    prompts_dir, results_dir = _ensure_dropzone(root)
    prompt_path = prompts_dir / f"{task_id}.md"
    result_path = results_dir / f"{task_id}.md"

    body = (
        "# Coder Prompt\n\n"
        f"reason: {reason}\n\n"
        "## Prompt\n\n"
        f"{prompt}\n"
    )
    _write_markdown_handoff(prompt_path, task_id=task_id, kind="coder", status="needs_input", body=body)

    append_activity(
        root=root,
        event="coder_manual_handoff",
        detail=f"prompt_file={prompt_path.as_posix()} result_file={result_path.as_posix()}",
        task_id=task_id,
        channel="manual",
    )

    deadline = time.monotonic() + max(0, timeout_sec)
    while time.monotonic() <= deadline:
        if result_path.exists():
            result_status = _extract_status_from_markdown(result_path)
            content = result_path.read_text(encoding="utf-8")
            out_path.write_text(content, encoding="utf-8")
            append_activity(
                root=root,
                event="coder_manual_result",
                detail=f"result_status={result_status}",
                task_id=task_id,
                channel="manual",
            )
            return {
                "mode": "manual",
                "result_file": result_path.as_posix(),
                "status": result_status,
                "task_id": task_id,
            }
        if poll_interval_sec <= 0:
            break
        time.sleep(poll_interval_sec)

    timeout_note = (
        "Coder manual handoff pendiente.\n"
        f"task_id={task_id}\n"
        f"prompt_file={prompt_path.as_posix()}\n"
        f"expected_result={result_path.as_posix()}\n"
    )
    out_path.write_text(timeout_note, encoding="utf-8")
    append_activity(
        root=root,
        event="coder_needs_input",
        detail=f"timeout waiting manual result ({timeout_sec}s)",
        task_id=task_id,
        channel="manual",
        level="warning",
    )
    return {
        "mode": "manual",
        "result_file": result_path.as_posix(),
        "status": "needs_input",
        "task_id": task_id,
    }


def run(
    prompt: str,
    out_path: Path,
    root: Path | None = None,
    timeout_sec: int | None = None,
    task_id: str | None = None,
    poll_interval_sec: float = 1.0,
) -> dict[str, str]:
    """
    Execute delegated coding task.

    Returns a dict with keys: status, task_id, mode, result_file.
    status is one of: ok, error, needs_input.
    """
    base_root = (root or ROOT).resolve()
    out_path = out_path.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not task_id:
        task_id = f"coder-{utc_now_iso().replace(':', '').replace('-', '').replace('T', '').replace('Z', '')}-{uuid4().hex[:8]}"

    runtime = _resolve_runtime(base_root, timeout_sec)
    cmd = runtime["cmd"]
    args = runtime["args"]
    profile_name = runtime["profile_name"]
    effective_timeout = int(runtime["timeout_sec"])

    if not cmd:
        return _manual_fallback(
            root=base_root,
            prompt=prompt,
            out_path=out_path,
            task_id=task_id,
            timeout_sec=effective_timeout,
            poll_interval_sec=poll_interval_sec,
            reason=f"profile '{profile_name}' sin command",
        )

    if shutil.which(cmd) is None:
        return _manual_fallback(
            root=base_root,
            prompt=prompt,
            out_path=out_path,
            task_id=task_id,
            timeout_sec=effective_timeout,
            poll_interval_sec=poll_interval_sec,
            reason=f"command '{cmd}' no disponible en PATH",
        )

    _, results_dir = _ensure_dropzone(base_root)
    result_path = results_dir / f"{task_id}.md"
    full_cmd = [cmd, *args]

    try:
        completed = subprocess.run(
            full_cmd,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=effective_timeout,
            check=False,
        )
        status = "ok" if completed.returncode == 0 else "error"
        body = (
            f"profile: {profile_name}\n"
            f"command: {full_cmd}\n"
            f"exit_code: {completed.returncode}\n"
            "\n## stdout\n\n"
            f"{sanitize_detail(completed.stdout)}\n"
            "\n## stderr\n\n"
            f"{sanitize_detail(completed.stderr)}\n"
        )
        _write_markdown_handoff(result_path, task_id=task_id, kind="coder", status=status, body=body)
        out_path.write_text(result_path.read_text(encoding="utf-8"), encoding="utf-8")

        append_activity(
            root=base_root,
            event="coder_subprocess_done",
            detail=f"profile={profile_name} exit_code={completed.returncode}",
            task_id=task_id,
            channel="manual",
            level="info" if status == "ok" else "warning",
        )
        return {
            "mode": "subprocess",
            "result_file": result_path.as_posix(),
            "status": status,
            "task_id": task_id,
        }
    except subprocess.TimeoutExpired:
        body = (
            f"profile: {profile_name}\n"
            f"command: {full_cmd}\n"
            f"timeout_sec: {effective_timeout}\n"
            "\nEl proceso no termino en el tiempo esperado."
        )
        _write_markdown_handoff(result_path, task_id=task_id, kind="coder", status="needs_input", body=body)
        out_path.write_text(result_path.read_text(encoding="utf-8"), encoding="utf-8")
        append_activity(
            root=base_root,
            event="coder_subprocess_timeout",
            detail=f"profile={profile_name} timeout_sec={effective_timeout}",
            task_id=task_id,
            channel="manual",
            level="warning",
        )
        return {
            "mode": "subprocess",
            "result_file": result_path.as_posix(),
            "status": "needs_input",
            "task_id": task_id,
        }
    except OSError as exc:
        body = (
            f"profile: {profile_name}\n"
            f"command: {full_cmd}\n"
            f"error: {exc.__class__.__name__}\n"
            "\nNo se pudo ejecutar el comando delegado."
        )
        _write_markdown_handoff(result_path, task_id=task_id, kind="coder", status="error", body=body)
        out_path.write_text(result_path.read_text(encoding="utf-8"), encoding="utf-8")
        append_activity(
            root=base_root,
            event="coder_subprocess_error",
            detail=f"profile={profile_name} error={exc.__class__.__name__}",
            task_id=task_id,
            channel="manual",
            level="error",
        )
        return {
            "mode": "subprocess",
            "result_file": result_path.as_posix(),
            "status": "error",
            "task_id": task_id,
        }
