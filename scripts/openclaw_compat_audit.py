#!/usr/bin/env python3
"""OpenClaw <-> workspace compatibility audit with deterministic reports."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.repo_root import get_canonical_root

REPORT_JSON = Path("docs/_inbox/openclaw_compat_audit_latest.json")
REPORT_MD = Path("docs/_inbox/openclaw_compat_audit_latest.md")
REPORT_LOG = Path("logs/openclaw_compat_audit_latest.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def _exists(root: Path, rel: str) -> bool:
    return (root / rel).exists()


def _git_status_short(root: Path) -> List[str]:
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "status", "--short"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return ["GAP/NO_VERIFICADO: git no disponible en entorno"]
    if proc.returncode != 0:
        return [f"GAP/NO_VERIFICADO: git status fallo rc={proc.returncode}"]
    lines = [line.rstrip() for line in proc.stdout.splitlines() if line.strip()]
    return lines[:80]


def _verdict_icon(verdict: str) -> str:
    return {
        "compatible": "✅",
        "risk": "🟨",
        "gap": "❌",
    }.get(verdict, "🟨")


def _area(
    *,
    name: str,
    verdict: str,
    evidence_paths: List[str],
    notes: str,
    gaps: List[str] | None = None,
) -> Dict[str, Any]:
    return {
        "name": name,
        "verdict": verdict,
        "evidence_paths": sorted(set(evidence_paths)),
        "notes": notes,
        "gaps": gaps or [],
    }


def _build_matrix(root: Path) -> List[Dict[str, Any]]:
    heartbeat_policy = _load_json(root / "state/heartbeat_policy.json")
    runtime_policy = _load_json(root / "state/channel_runtime_policy.json")
    instruction_report = _load_json(root / "docs/_inbox/instruction_surface_report_latest.json")
    hygiene_report = _load_json(root / "docs/_inbox/workspace_hygiene_report_latest.json")
    reality_report = _load_json(root / "docs/_inbox/repo_reality_report_latest.json")

    drift_grave = int(instruction_report.get("summary", {}).get("drift_grave_count", 0))
    hygiene_candidates = int(hygiene_report.get("summary", {}).get("candidate_count", 0))
    hygiene_sensitive = int(hygiene_report.get("summary", {}).get("sensitive_count", 0))
    reality_pending = int(reality_report.get("summary", {}).get("pending_count", 0))

    has_hook_files = _exists(root, "hooks/otto-runtime-bridge/HOOK.md") and _exists(
        root, "hooks/otto-runtime-bridge/handler.js"
    )
    hook_text = (root / "hooks/otto-runtime-bridge/HOOK.md").read_text(encoding="utf-8") if has_hook_files else ""
    hook_is_experimental = "experimental" in hook_text.lower()
    heartbeat_ok = _exists(root, "HEARTBEAT.md") and "scripts/heartbeat_worker.py --once --root ." in (
        root / "HEARTBEAT.md"
    ).read_text(encoding="utf-8")
    interval_ok = int(heartbeat_policy.get("interval_minutes", 0)) == 30
    session_schema = runtime_policy.get("session_id_schema", {})
    session_fields = session_schema.get("fields", [])
    zero_mix_fields_ok = all(
        field in session_fields for field in ["channel", "account_id", "peer_id", "channel_id", "thread_id"]
    )

    matrix: List[Dict[str, Any]] = []

    matrix.append(
        _area(
            name="Workspace semantics",
            verdict="compatible"
            if _exists(root, ".openclaw/CANONICAL_ROOT.json") and _exists(root, "openclaw/CONTEXT_MAP.md")
            else "gap",
            evidence_paths=[".openclaw/CANONICAL_ROOT.json", "openclaw/CONTEXT_MAP.md", "scripts/repo_root.py"],
            notes="Raiz canonica pinneada y contexto operativo en repo.",
            gaps=[] if _exists(root, ".openclaw/CANONICAL_ROOT.json") else ["Falta marker canonico de root."],
        )
    )

    matrix.append(
        _area(
            name="Hooks (message received/sent)",
            verdict="risk" if hook_is_experimental else ("compatible" if has_hook_files else "gap"),
            evidence_paths=[
                "hooks/otto-runtime-bridge/HOOK.md",
                "hooks/otto-runtime-bridge/handler.js",
                "scripts/channel_ingress_adapter.py",
            ],
            notes="Bridge de workspace hook existe y enruta a ingress adapter.",
            gaps=(
                ["Hook marcado experimental; recomendable validacion en entorno productivo OpenClaw."]
                if hook_is_experimental
                else ([] if has_hook_files else ["Faltan archivos de hook bridge."])
            ),
        )
    )

    matrix.append(
        _area(
            name="Heartbeat behavior",
            verdict="compatible" if (heartbeat_ok and interval_ok) else "risk",
            evidence_paths=["HEARTBEAT.md", "scripts/heartbeat_worker.py", "state/heartbeat_policy.json"],
            notes="Heartbeat ejecuta pipeline pasivo por bloques sin requerir comandos del usuario.",
            gaps=(
                []
                if (heartbeat_ok and interval_ok)
                else ["Heartbeat no alineado completamente con ejecucion pasiva cada ~30 minutos."]
            ),
        )
    )

    matrix.append(
        _area(
            name="Cron vs Heartbeat",
            verdict="risk",
            evidence_paths=["AGENTS.md", "HEARTBEAT.md", "scripts/heartbeat_worker.py"],
            notes="Repo documenta uso de heartbeat; no hay verificacion automatizada de contrato cron OpenClaw en este run.",
            gaps=["GAP/NO VERIFICADO: contrato oficial cron vs heartbeat no validado en runtime real."],
        )
    )

    matrix.append(
        _area(
            name="Sessions/session scoping (zero-mix)",
            verdict="compatible" if zero_mix_fields_ok else "gap",
            evidence_paths=[
                "scripts/session_memory_manager.py",
                "scripts/channel_ingress_adapter.py",
                "state/channel_runtime_policy.json",
            ],
            notes="Session_id usa canal/account/peer/channel/thread para aislamiento por chat/thread.",
            gaps=[] if zero_mix_fields_ok else ["Campos de zero-mix incompletos en schema de session_id."],
        )
    )

    matrix.append(
        _area(
            name="Subagents / multi-agent compatibility",
            verdict="risk",
            evidence_paths=[
                "AGENTS.md",
                "CLAUDE.md",
                ".claude/rules/00_CANON.md",
                "brain/domains/openclaw_ops/07_DELEGATION_POLICY.md",
            ],
            notes="Delegacion y lectura base estan definidas; falta verificacion e2e con orchestration externa de sub-agents.",
            gaps=["GAP/NO VERIFICADO: flujo multi-agent externo no validado en este entorno."],
        )
    )

    matrix.append(
        _area(
            name="Delegation + instruction surface control",
            verdict="compatible" if drift_grave == 0 else "gap",
            evidence_paths=[
                "state/instruction_surface_policy.json",
                "scripts/instruction_surface_doctor.py",
                "docs/_inbox/instruction_surface_report_latest.json",
            ],
            notes="Allowlist de archivos reservados y doctor de drift activos.",
            gaps=[] if drift_grave == 0 else [f"drift_grave_count={drift_grave} requiere fix antes de operar."],
        )
    )

    matrix.append(
        _area(
            name="Hygiene + repo reality posture",
            verdict="compatible" if (hygiene_candidates == 0 and hygiene_sensitive == 0 and reality_pending == 0) else "risk",
            evidence_paths=[
                "docs/_inbox/workspace_hygiene_report_latest.json",
                "docs/_inbox/repo_reality_report_latest.json",
                "scripts/workspace_hygiene_doctor.py",
                "scripts/repo_reality_doctor.py",
            ],
            notes="Doctors deterministas presentes para limpieza/no-drift.",
            gaps=(
                []
                if (hygiene_candidates == 0 and hygiene_sensitive == 0 and reality_pending == 0)
                else [
                    f"hygiene candidate_count={hygiene_candidates}",
                    f"hygiene sensitive_count={hygiene_sensitive}",
                    f"repo_reality pending_count={reality_pending}",
                ]
            ),
        )
    )

    return matrix


def run_audit(root: str | Path) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    matrix = _build_matrix(canonical_root)

    gaps: List[str] = []
    has_blocking = False
    has_risk = False
    for area in matrix:
        verdict = str(area.get("verdict", "risk"))
        if verdict == "gap":
            has_blocking = True
        elif verdict == "risk":
            has_risk = True
        for gap in area.get("gaps", []):
            gaps.append(str(gap))

    go_no_go = "no_go" if has_blocking else ("go_with_limits" if has_risk else "go")
    status = "ok" if not has_blocking else "partial"

    report = {
        "canonical_root": str(canonical_root.resolve()),
        "created_at": _utc_now(),
        "status": status,
        "go_no_go": go_no_go,
        "matrix": matrix,
        "official_docs_verification": {
            "verified_sources": [],
            "unverified_topics": [
                "GAP/NO VERIFICADO: contrato oficial de cron vs heartbeat en runtime productivo",
                "GAP/NO VERIFICADO: compatibilidad e2e multi-agent/sandbox fuera de pruebas locales",
            ],
        },
        "gaps": sorted(set(gaps)),
        "run_context": {
            "git_status_short": _git_status_short(canonical_root),
            "paths": {
                "json": REPORT_JSON.as_posix(),
                "markdown": REPORT_MD.as_posix(),
                "log": REPORT_LOG.as_posix(),
            },
        },
        "version": 1,
    }
    return report


def _write_markdown(root: Path, report: Dict[str, Any]) -> None:
    lines: List[str] = [
        "# OpenClaw Compatibility Audit",
        "",
        f"- Canonical root: `{report['canonical_root']}`",
        f"- Created at: `{report['created_at']}`",
        f"- Status: `{report['status']}`",
        f"- Go/No-Go: `{report['go_no_go']}`",
        "",
        "## Compatibility Matrix",
        "",
        "| Area | Verdict | Notes |",
        "| --- | --- | --- |",
    ]
    for area in report.get("matrix", []):
        verdict = str(area.get("verdict", "risk"))
        icon = _verdict_icon(verdict)
        notes = str(area.get("notes", "")).replace("|", "/")
        lines.append(f"| {area.get('name', '')} | {icon} `{verdict}` | {notes} |")

    lines.extend(["", "## Evidence by Area", ""])
    for area in report.get("matrix", []):
        lines.append(f"### {area.get('name', '')}")
        lines.append(f"- Verdict: `{area.get('verdict', '')}`")
        for path in area.get("evidence_paths", []):
            lines.append(f"- Evidence: `{path}`")
        gaps = area.get("gaps", [])
        if gaps:
            for gap in gaps:
                lines.append(f"- GAP/NO VERIFICADO: {gap}")
        lines.append("")

    lines.extend(["## GAPS/NO VERIFICADO", ""])
    if report.get("gaps"):
        for gap in report["gaps"]:
            lines.append(f"- {gap}")
    else:
        lines.append("- None")

    lines.extend(["", "## Context Snapshot", ""])
    for line in report.get("run_context", {}).get("git_status_short", []):
        lines.append(f"- `{line}`")

    (root / REPORT_MD).parent.mkdir(parents=True, exist_ok=True)
    (root / REPORT_MD).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate OpenClaw compatibility audit reports")
    parser.add_argument("--root", default=".")
    args = parser.parse_args()

    report = run_audit(args.root)
    canonical_root = get_canonical_root(args.root)
    _save_json(canonical_root / REPORT_JSON, report)
    _save_json(canonical_root / REPORT_LOG, report)
    _write_markdown(canonical_root, report)

    print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if report.get("status") == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
