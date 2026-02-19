#!/usr/bin/env python3
"""Production readiness doctor (offline-first, non-destructive)."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.outbox_delivery import run_scan as run_outbox_scan
from scripts.repo_root import get_canonical_root

STATE_PATH = Path("state/prod_doctor_state.json")
REPORT_JSON = Path("docs/_inbox/prod_doctor_latest.json")
REPORT_MD = Path("docs/_inbox/prod_doctor_latest.md")
REPORT_LOG = Path("logs/prod_doctor_latest.json")

DEFAULT_STATE: Dict[str, Any] = {
    "version": 1,
    "run_interval_hours": 6,
    "last_run_utc": "",
    "last_status": "",
    "last_gaps": [],
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _save_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _load_state(root: Path) -> Dict[str, Any]:
    state = dict(DEFAULT_STATE)
    state.update(_load_json(root / STATE_PATH))
    if not (root / STATE_PATH).is_file():
        _save_json(root / STATE_PATH, state)
    return state


def _save_state(root: Path, state: Dict[str, Any]) -> None:
    _save_json(root / STATE_PATH, state)


def _parse_iso(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _run_command(cmd: List[str]) -> Dict[str, Any]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except OSError as exc:
        return {"ok": False, "cmd": cmd, "returncode": 127, "stdout": "", "stderr": str(exc)}
    return {
        "ok": proc.returncode == 0,
        "cmd": cmd,
        "returncode": proc.returncode,
        "stdout": proc.stdout[:800],
        "stderr": proc.stderr[:800],
    }


def _check(root: Path, *, name: str, ok: bool, evidence: List[str], note: str, gap: str = "") -> Dict[str, Any]:
    return {
        "name": name,
        "ok": bool(ok),
        "status": "ok" if ok else "gap",
        "evidence_paths": sorted(set(evidence)),
        "note": note,
        "gap": gap,
    }


def run_prod_doctor(root: str | Path, *, force: bool = False) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    now = _utc_now()
    state = _load_state(canonical_root)
    run_interval_hours = max(1, int(state.get("run_interval_hours", 6)))

    last_run = _parse_iso(str(state.get("last_run_utc", "")))
    if not force and last_run and (now - last_run) < timedelta(hours=run_interval_hours):
        report = {
            "canonical_root": str(canonical_root.resolve()),
            "created_at": now.isoformat(),
            "status": "skipped_interval",
            "go_no_go": "go_with_limits",
            "summary": {"run_interval_hours": run_interval_hours, "last_run_utc": state.get("last_run_utc", "")},
            "checks": [],
            "gaps_no_verificado": [],
            "version": 1,
        }
        _save_json(canonical_root / REPORT_JSON, report)
        _save_json(canonical_root / REPORT_LOG, report)
        (canonical_root / REPORT_MD).write_text("# Prod Doctor\n\n- Status: `skipped_interval`\n", encoding="utf-8")
        return {"report": report, "paths": {"json": REPORT_JSON.as_posix(), "markdown": REPORT_MD.as_posix(), "log": REPORT_LOG.as_posix()}}

    checks: List[Dict[str, Any]] = []
    gaps: List[str] = []

    checks.append(
        _check(
            canonical_root,
            name="canonical_root_marker",
            ok=(canonical_root / ".openclaw/CANONICAL_ROOT.json").is_file(),
            evidence=[".openclaw/CANONICAL_ROOT.json"],
            note="Canonical root pin marker must exist.",
            gap="Falta .openclaw/CANONICAL_ROOT.json",
        )
    )

    hb_path = canonical_root / "HEARTBEAT.md"
    hb_ok = hb_path.is_file() and "python3 scripts/heartbeat_worker.py --once --root ." in hb_path.read_text(encoding="utf-8")
    checks.append(
        _check(
            canonical_root,
            name="heartbeat_contract",
            ok=hb_ok,
            evidence=["HEARTBEAT.md", "scripts/heartbeat_worker.py"],
            note="Heartbeat contract should call heartbeat_worker once.",
            gap="HEARTBEAT.md no contiene contrato operativo esperado.",
        )
    )

    heartbeat_policy = _load_json(canonical_root / "state/heartbeat_policy.json")
    interval_ok = int(heartbeat_policy.get("interval_minutes", 0)) == 30
    checks.append(
        _check(
            canonical_root,
            name="heartbeat_policy_interval",
            ok=interval_ok,
            evidence=["state/heartbeat_policy.json"],
            note="interval_minutes should remain 30 for passive cadence.",
            gap="state/heartbeat_policy.json interval_minutes != 30",
        )
    )

    openclaw_path = shutil.which("openclaw")
    if openclaw_path:
        checks.append(
            _check(
                canonical_root,
                name="openclaw_cli_present",
                ok=True,
                evidence=[],
                note=f"openclaw CLI detected at {openclaw_path}",
            )
        )
        help_cmd = _run_command(["openclaw", "--help"])
        checks.append(
            _check(
                canonical_root,
                name="openclaw_cli_help",
                ok=help_cmd["ok"],
                evidence=[],
                note="openclaw --help executed.",
                gap=f"openclaw --help rc={help_cmd['returncode']}",
            )
        )
        hooks_help = _run_command(["openclaw", "hooks", "--help"])
        checks.append(
            _check(
                canonical_root,
                name="openclaw_hooks_help",
                ok=hooks_help["ok"],
                evidence=["hooks/otto-runtime-bridge/HOOK.md"],
                note="hooks command availability probe.",
                gap=f"openclaw hooks --help rc={hooks_help['returncode']}",
            )
        )
        hooks_list = _run_command(["openclaw", "hooks", "list"])
        discovered = "otto-runtime-bridge" in (hooks_list.get("stdout", "") + hooks_list.get("stderr", ""))
        checks.append(
            _check(
                canonical_root,
                name="hook_bridge_discovery",
                ok=hooks_list["ok"] and discovered,
                evidence=["hooks/otto-runtime-bridge/HOOK.md", "hooks/otto-runtime-bridge/handler.js"],
                note="Attempt to verify hook discovery through openclaw hooks list.",
                gap="GAP/NO VERIFICADO: hook bridge no confirmado por openclaw hooks list.",
            )
        )
    else:
        checks.append(
            _check(
                canonical_root,
                name="openclaw_cli_present",
                ok=False,
                evidence=[],
                note="CLI probe for production integration.",
                gap="GAP/NO VERIFICADO: openclaw CLI no disponible en PATH.",
            )
        )

    outbox_scan = run_outbox_scan(canonical_root)
    checks.append(
        _check(
            canonical_root,
            name="outbox_scan",
            ok=True,
            evidence=[outbox_scan["paths"]["json"], outbox_scan["paths"]["markdown"]],
            note="outbox scan completed (dry non-delivery).",
        )
    )

    for item in checks:
        if not item["ok"] and item.get("gap"):
            gaps.append(str(item["gap"]))

    has_blocking = any(item["name"] in {"canonical_root_marker", "heartbeat_contract"} and not item["ok"] for item in checks)
    status = "ok" if not has_blocking else "partial"
    go_no_go = "go_with_limits" if gaps else "go"
    if has_blocking:
        go_no_go = "blocked"

    report = {
        "canonical_root": str(canonical_root.resolve()),
        "created_at": now.isoformat(),
        "status": status,
        "go_no_go": go_no_go,
        "summary": {
            "checks_total": len(checks),
            "checks_ok": sum(1 for item in checks if item["ok"]),
            "checks_gap": sum(1 for item in checks if not item["ok"]),
            "run_interval_hours": run_interval_hours,
        },
        "checks": checks,
        "gaps_no_verificado": sorted(set(gaps)),
        "paths": {"json": REPORT_JSON.as_posix(), "markdown": REPORT_MD.as_posix(), "log": REPORT_LOG.as_posix()},
        "version": 1,
    }

    state["last_run_utc"] = now.isoformat()
    state["last_status"] = status
    state["last_gaps"] = sorted(set(gaps))
    _save_state(canonical_root, state)

    _save_json(canonical_root / REPORT_JSON, report)
    _save_json(canonical_root / REPORT_LOG, report)
    lines = [
        "# Prod Doctor",
        "",
        f"- Status: `{status}`",
        f"- Go/No-Go: `{go_no_go}`",
        f"- Checks OK: {report['summary']['checks_ok']}/{report['summary']['checks_total']}",
        "",
        "## Checks",
        "",
    ]
    for item in checks:
        marker = "✅" if item["ok"] else "🟨"
        lines.append(f"- {marker} `{item['name']}`: {item['note']}")
        for path in item.get("evidence_paths", []):
            lines.append(f"  - evidence: `{path}`")
        if item.get("gap"):
            lines.append(f"  - gap: {item['gap']}")
    (canonical_root / REPORT_MD).write_text("\n".join(lines) + "\n", encoding="utf-8")

    return {"report": report, "paths": report["paths"]}


def main() -> int:
    parser = argparse.ArgumentParser(description="Production compatibility doctor")
    parser.add_argument("--root", default=".")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    out = run_prod_doctor(args.root, force=args.force)
    print(json.dumps(out["report"], indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if out["report"]["status"] in {"ok", "partial", "skipped_interval"} else 3


if __name__ == "__main__":
    raise SystemExit(main())
