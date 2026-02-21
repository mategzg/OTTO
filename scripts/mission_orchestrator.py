#!/usr/bin/env python3
"""Mission orchestration helper for per-mission planning and learning packaging."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.repo_root import get_canonical_root, is_pathlike_component

POLICY_PATH = Path("state/mission_orchestration_policy.json")
STATE_PATH = Path("state/mission_orchestration_state.json")
MISSIONS_ROOT = Path("state/missions")

REPORT_JSON = Path("docs/_inbox/mission_orchestrator_report_latest.json")
REPORT_MD = Path("docs/_inbox/mission_orchestrator_report_latest.md")
REPORT_LOG = Path("logs/mission_orchestrator_latest.json")

PROMPTS_LATEST_JSON = Path("docs/_inbox/mission_prompts_latest.json")
PROMPTS_LATEST_MD = Path("docs/_inbox/mission_prompts_latest.md")

DEFAULT_POLICY: Dict[str, Any] = {
    "version": 1,
    "enabled": True,
    "size_default": "M",
    "sizes": {
        "S": {
            "roles": ["A"],
            "required_gates": ["pytest -q"],
            "update_cadence": "on milestone",
            "evidence_level": "minimal",
        },
        "M": {
            "roles": ["A", "B"],
            "required_gates": ["pytest -q", "python3 scripts/repo_reality_doctor.py --scan --json"],
            "update_cadence": "daily",
            "evidence_level": "standard",
        },
        "L": {
            "roles": ["A", "B", "C"],
            "required_gates": [
                "pytest -q",
                "python3 scripts/repo_reality_doctor.py --scan --json",
                "python3 scripts/workspace_hygiene_doctor.py --scan",
                "python3 scripts/instruction_surface_doctor.py --scan --root .",
            ],
            "update_cadence": "per major step",
            "evidence_level": "high",
        },
        "XL": {
            "roles": ["A", "B", "C", "D"],
            "required_gates": [
                "python3 -m py_compile scripts/*.py",
                "pytest -q",
                "python3 scripts/repo_reality_doctor.py --scan --json",
                "python3 scripts/workspace_hygiene_doctor.py --scan",
                "python3 scripts/instruction_surface_doctor.py --scan --root .",
                "python3 scripts/brain_index_build.py",
            ],
            "update_cadence": "per phase",
            "evidence_level": "full",
        },
    },
    "role_catalog": {
        "A": {
            "name": "Architecture and orchestration",
            "ownership": "scope, plan quality, interfaces, risk control",
        },
        "B": {
            "name": "Implementation",
            "ownership": "feature code and integration",
        },
        "C": {
            "name": "QA and validation",
            "ownership": "tests, regressions, gates and edge cases",
        },
        "D": {
            "name": "Docs and release hardening",
            "ownership": "canon docs, runbook updates, final evidence",
        },
    },
    "research_phase0": {
        "enabled": True,
        "coverage_threshold": 0.45,
        "learning_max_chars": 12000,
        "dedupe_by_hash": True,
    },
    "paths": {
        "missions_root": "state/missions",
        "learning_drop_root": "vault/inbox_raw/_pending_drop/mission_learning",
        "prompts_latest_json": "docs/_inbox/mission_prompts_latest.json",
        "prompts_latest_md": "docs/_inbox/mission_prompts_latest.md",
    },
    "reserved_guardrails": {
        "forbid_filenames": ["AGENTS.md", "AGENTS.override.md", "CLAUDE.md", "CLAUDE.local.md"],
    },
}

DEFAULT_STATE: Dict[str, Any] = {
    "version": 1,
    "last_run_utc": "",
    "last_status": "never",
    "mission_counter_by_scope": {},
    "missions": {},
    "last_generated_prompts_mission_id": "",
}

SIZE_VALUES = ("S", "M", "L", "XL")
SEARCH_FILES = [
    Path("PROJECT_BRIEF.md"),
    Path("REPO_MAP.md"),
    Path("openclaw/CONTEXT_MAP.md"),
]
SEARCH_GLOBS = [
    "repo_map/*.md",
    "brain/domains/openclaw_ops/*.md",
]


@dataclass(frozen=True)
class MissionRef:
    mission_id: str
    mission_dir: Path
    mission_json: Path
    plan_md: Path
    prompts_dir: Path
    events_ndjson: Path


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


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


def _append_ndjson(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, ensure_ascii=False) + "\n")


def _slug(value: str) -> str:
    out: List[str] = []
    prev_sep = False
    for ch in value.lower():
        ok = ("a" <= ch <= "z") or ("0" <= ch <= "9")
        if ok:
            out.append(ch)
            prev_sep = False
            continue
        if not prev_sep:
            out.append("_")
            prev_sep = True
    text = "".join(out).strip("_")
    return text or "mission"


def _safe_mission_id(value: str) -> str:
    mission_id = value.strip().lower()
    if not mission_id:
        raise RuntimeError("mission_id is required")
    if any(is_pathlike_component(part) for part in Path(mission_id).parts):
        raise RuntimeError("mission_id contains unsafe/pathlike components")
    for ch in mission_id:
        if not (ch.isalnum() or ch in {"_", "-"}):
            raise RuntimeError("mission_id contains unsupported characters")
    return mission_id


def _normalize_size(raw: str) -> str:
    value = raw.strip().upper()
    if value == "AUTO":
        return "AUTO"
    if value not in SIZE_VALUES:
        raise RuntimeError(f"Unsupported size '{raw}'. Use auto|S|M|L|XL.")
    return value


def _ensure_policy(root: Path) -> Dict[str, Any]:
    path = root / POLICY_PATH
    payload = _load_json(path)
    policy = dict(DEFAULT_POLICY)
    policy.update(payload)
    policy["sizes"] = dict(DEFAULT_POLICY["sizes"]) | dict(policy.get("sizes", {}))
    policy["role_catalog"] = dict(DEFAULT_POLICY["role_catalog"]) | dict(policy.get("role_catalog", {}))
    policy["research_phase0"] = dict(DEFAULT_POLICY["research_phase0"]) | dict(policy.get("research_phase0", {}))
    policy["paths"] = dict(DEFAULT_POLICY["paths"]) | dict(policy.get("paths", {}))
    policy["reserved_guardrails"] = dict(DEFAULT_POLICY["reserved_guardrails"]) | dict(
        policy.get("reserved_guardrails", {})
    )
    if not path.is_file():
        _save_json(path, policy)
    return policy


def _ensure_state(root: Path) -> Dict[str, Any]:
    path = root / STATE_PATH
    payload = _load_json(path)
    state = dict(DEFAULT_STATE)
    state.update(payload)
    if not isinstance(state.get("mission_counter_by_scope"), dict):
        state["mission_counter_by_scope"] = {}
    if not isinstance(state.get("missions"), dict):
        state["missions"] = {}
    if not path.is_file():
        _save_json(path, state)
    return state


def _mission_ref(root: Path, policy: Dict[str, Any], mission_id: str) -> MissionRef:
    missions_root = root / str(policy.get("paths", {}).get("missions_root", MISSIONS_ROOT.as_posix()))
    mission_dir = missions_root / mission_id
    return MissionRef(
        mission_id=mission_id,
        mission_dir=mission_dir,
        mission_json=mission_dir / "mission.json",
        plan_md=mission_dir / "PLAN.md",
        prompts_dir=mission_dir / "prompts",
        events_ndjson=mission_dir / "events.ndjson",
    )


def _collect_context_files(root: Path) -> List[Path]:
    out: List[Path] = []
    for rel in SEARCH_FILES:
        path = root / rel
        if path.is_file():
            out.append(path)
    for pattern in SEARCH_GLOBS:
        for path in sorted(root.glob(pattern), key=lambda item: item.as_posix()):
            if path.is_file():
                out.append(path)
    return out


def _tokenize_title(title: str) -> List[str]:
    parts = [_slug(part) for part in title.split()]
    tokens = [token for chunk in parts for token in chunk.split("_") if len(token) >= 3]
    return sorted(set(tokens))


def _knowledge_coverage(root: Path, title: str) -> Dict[str, Any]:
    tokens = _tokenize_title(title)
    if not tokens:
        return {"coverage_score": 1.0, "tokens": [], "matched_tokens": [], "matched_files": []}

    matched_tokens: set[str] = set()
    matched_files: set[str] = set()
    for path in _collect_context_files(root):
        text = path.read_text(encoding="utf-8", errors="replace").lower()
        file_hit = False
        for token in tokens:
            if token in text:
                matched_tokens.add(token)
                file_hit = True
        if file_hit:
            matched_files.add(path.resolve().relative_to(root.resolve()).as_posix())

    score = len(matched_tokens) / max(1, len(tokens))
    return {
        "coverage_score": round(score, 4),
        "tokens": tokens,
        "matched_tokens": sorted(matched_tokens),
        "matched_files": sorted(matched_files),
    }


def _infer_size_auto(title: str, coverage_score: float) -> str:
    token_count = len(_tokenize_title(title))
    lower = title.lower()
    high_complexity = any(
        key in lower
        for key in (
            "multi",
            "complex",
            "orchestration",
            "production",
            "concurrency",
            "migration",
            "integration",
            "cross",
            "xl",
        )
    )
    if high_complexity and (token_count >= 8 or coverage_score < 0.3):
        return "XL"
    if token_count <= 5 and coverage_score >= 0.7:
        return "S"
    if token_count <= 10 and coverage_score >= 0.4:
        return "M"
    if token_count <= 16:
        return "L"
    return "XL"


def _choose_size(size_hint: str, title: str, coverage_score: float, policy: Dict[str, Any]) -> str:
    requested = _normalize_size(size_hint)
    if requested != "AUTO":
        return requested
    inferred = _infer_size_auto(title, coverage_score)
    if inferred in SIZE_VALUES:
        return inferred
    fallback = str(policy.get("size_default", "M")).upper()
    return fallback if fallback in SIZE_VALUES else "M"


def _scope_key(channel: str, peer_id: str, thread_id: str, title: str) -> str:
    base = "|".join([channel.strip().lower(), peer_id.strip().lower(), thread_id.strip().lower(), _slug(title)[:40]])
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:10]


def _next_mission_id(state: Dict[str, Any], *, scope_key: str) -> tuple[str, int]:
    counters = state.setdefault("mission_counter_by_scope", {})
    current = int(counters.get(scope_key, 0))
    next_value = current + 1
    counters[scope_key] = next_value
    mission_id = f"msn_{scope_key}_{next_value:02d}"
    return mission_id, next_value


def _render_plan(meta: Dict[str, Any], profile: Dict[str, Any]) -> str:
    roles = ", ".join(str(item) for item in profile.get("roles", []))
    gates = profile.get("required_gates", [])
    gate_lines = "\n".join(f"- `{item}`" for item in gates) if gates else "- GAP/NO VERIFICADO"
    return "\n".join(
        [
            "# Mission Plan",
            "",
            f"- Mission ID: `{meta['mission_id']}`",
            f"- Title: {meta['title']}",
            f"- Mission size: `{meta['size']}`",
            f"- Channel: `{meta['channel']}`",
            f"- Peer ID: `{meta['peer_id']}`",
            f"- Thread ID: `{meta.get('thread_id', '')}`",
            f"- Status: `{meta['status']}`",
            f"- Created at: `{meta['created_at']}`",
            "",
            "## Objective",
            "",
            f"- {meta['title']}",
            "",
            "## Non-Objectives",
            "",
            "- No side quests fuera del objetivo acordado.",
            "- No refactors transversales sin evidencia.",
            "",
            "## Assumptions",
            "",
            f"- Coverage score inicial: `{meta.get('coverage_score', 0.0)}`.",
            f"- Research phase0 needed: `{meta.get('research_phase0_needed', False)}`.",
            "",
            "## Risks",
            "",
            "- Dependencias externas no verificables offline.",
            "- Integraciones cruzadas que puedan romper zero-mix o instruction surface.",
            "",
            "## Approach",
            "",
            "- Diseñar por modulos con ownership claro por rol.",
            "- Ejecutar gates por calibre antes de close.",
            "- Capturar aprendizaje estructurado a pending_drop para ingest posterior.",
            "",
            "## Work Breakdown Structure",
            "",
            f"- Roles asignados: {roles or 'GAP/NO VERIFICADO'}",
            "- A: arquitectura, contratos y ruteo.",
            "- B: implementacion por ownership de modulos.",
            "- C: validacion (tests + doctores + gates).",
            "- D: docs canonicas y cierre operativo.",
            "",
            "## Tests",
            "",
            "- Unit tests de flujos criticos de la mision.",
            "- Verificacion de no regresion en componentes vecinos.",
            "",
            "## Gates",
            "",
            gate_lines,
            "",
            "## Rollback",
            "",
            "- Revertir solo archivos de la mision si un gate critico falla.",
            "- Mantener evidencia de fallos en reportes deterministicos.",
            "",
            "## Definition of Done",
            "",
            "- Objetivo completado con evidencia y gates verdes.",
            "- Docs actualizadas (si aplica) sin drift de autoridad.",
            "- Learning package emitido cuando hay aprendizaje reusable.",
            "",
            "## Evidence Paths",
            "",
            "- `docs/_inbox/mission_orchestrator_report_latest.json`",
            "- `docs/_inbox/mission_prompts_latest.json`",
            f"- `state/missions/{meta['mission_id']}/`",
        ]
    ) + "\n"


def _prompt_text(role: str, role_meta: Dict[str, Any], mission_meta: Dict[str, Any], plan_excerpt: str) -> str:
    run_style = "POTENT" if str(mission_meta.get("size", "M")) in {"L", "XL"} else "ATOMIC"
    safe_role = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in str(role))
    handoff_file = f"docs/_inbox/subagent_handoffs/{mission_meta['mission_id']}__{safe_role}.json"
    done_checks = [
        "[ ] Objetivo de la misión completado con evidencia verificable.",
        "[ ] No cambios fuera de SCOPE_PATHS (+ ALLOWED_EXCEPTIONS).",
        "[ ] Gates de la misión ejecutados y en PASS (o GAP explicado).",
        "[ ] Respuesta final en UN YAML (run + copilot_packet mínimo).",
    ]
    if run_style == "POTENT":
        done_checks.append("[ ] Checkpoints reportados en YAML con status por CP.")

    gates = [str(item) for item in mission_meta.get("required_gates", []) if str(item).strip()]
    if not gates:
        gates = ["pytest -q"]

    return "\n".join(
        [
            f"# Mission Prompt - Role {role}",
            "",
            f"ROLE: {role_meta.get('name', f'Role {role}')} executor. Evidence required. No fabrication.",
            "ROUTE: CODEX_DEFAULT (CLAUDE_CODE solo si `.claude/*` o runtime/plugins/rules/imports Claude)",
            f"RUN_STYLE: {run_style}",
            "MODE: APPLY",
            f"STOP_AFTER: {'FINAL_REPORT' if run_style == 'POTENT' else 'MILESTONE_DONE'}",
            "",
            "OBJECTIVE:",
            f"Completar ownership del rol {role} para la misión `{mission_meta['mission_id']}` sin romper surfaces.",
            "",
            "ROOT:",
            ".",
            "",
            "SCOPE_PATHS:",
            f"- state/missions/{mission_meta['mission_id']}/",
            "- docs/_inbox/mission_prompts_latest.json",
            "- docs/_inbox/mission_prompts_latest.md",
            "- docs/_inbox/subagent_handoffs/",
            "",
            "ALLOWED_EXCEPTIONS:",
            f"- {handoff_file}",
            "",
            "CONSTRAINTS (HARD):",
            "- NO-FABRICATION: desconocido -> GAP/NO_VERIFICADO.",
            "- SCOPE-BOUND: solo dentro de SCOPE_PATHS (+ ALLOWED_EXCEPTIONS).",
            "- DELTA-MINIMAL: no refactors amplios, no barridos cosméticos.",
            "- SURFACE-PROTECT: no cambiar APIs/contratos/schemas sin request explícito.",
            "- SECRET-SAFE: si aparece secreto -> STOP + escalar.",
            "- ANCHORS > line numbers.",
            "- STOP-ON-FAIL: cualquier gate FAIL detiene ejecución y reporta evidencia.",
            "- PROMPT AUTHORITY: no auto-encadenar prompts; next_prompt_ready es draft para orquestador.",
            "",
            "DONE_CRITERIA:",
            *done_checks,
            "",
            "GATES:",
            *[f"- `{gate}`" for gate in gates],
            "",
            "FAILURE_POLICY:",
            "Si cualquier gate falla: STOP inmediato, incluye output exacto, diagnóstico y fix propuesto.",
            "",
            "HANDOFF_FILE (MUST):",
            f"- `{handoff_file}`",
            "- Debe escribirse SIEMPRE al finalizar (success|failed|partial) con summary, files_changed, gates, gaps y commit_hash.",
            "",
            "OUTPUT_SCHEMA (MUST):",
            "- Devolver UN YAML machine-parseable con `run` + `copilot_packet`.",
            "- `run.allowed_exceptions` MUST existir (aunque sea `[]`).",
            "- `run.handoff_file` y `run.handoff_written=true` MUST estar presentes.",
            "- Si RUN_STYLE=POTENT: incluir `run.checkpoints[]` con gates por checkpoint.",
            "- `copilot_packet` mínimo: current_state, open_issues, approvals_needed, questions_to_user, suggested_next_steps.",
            "",
            "## Base Context (mandatory)",
            "",
            "- `PROMPT_MANUAL.md`",
            "- `PROJECT_BRIEF.md`",
            "- `REPO_MAP.md`",
            "- `repo_map/00_INDEX.md`",
            "- `repo_map/95_MISSION_ORCHESTRATION.md`",
            "- `repo_map/96_MISSION_ACTIVATION.md`",
            "- `brain/domains/openclaw_ops/14_MISSION_ORCHESTRATION.md`",
            "- `brain/domains/openclaw_ops/15_MISSION_ACTIVATION.md`",
            "- `openclaw/CONTEXT_MAP.md`",
            "",
            "## Mission Metadata",
            "",
            f"- Mission ID: `{mission_meta['mission_id']}`",
            f"- Mission title: {mission_meta['title']}",
            f"- Mission size: `{mission_meta['size']}`",
            f"- Role ownership: {role_meta.get('ownership', 'GAP/NO VERIFICADO')}",
            "",
            "## Plan Excerpt",
            "",
            "```md",
            plan_excerpt.rstrip(),
            "```",
        ]
    ) + "\n"


def _write_report(root: Path, report: Dict[str, Any]) -> Dict[str, str]:
    _save_json(root / REPORT_JSON, report)
    _save_json(root / REPORT_LOG, report)
    lines = [
        "# Mission Orchestrator Report",
        "",
        f"- Action: `{report.get('action', '')}`",
        f"- Status: `{report.get('status', '')}`",
        f"- Mission ID: `{report.get('mission_id', '')}`",
        f"- Created at: `{report.get('created_at', '')}`",
    ]
    summary = report.get("summary", {})
    if isinstance(summary, dict):
        lines.append(f"- Summary keys: `{', '.join(sorted(summary.keys()))}`")
    (root / REPORT_MD).parent.mkdir(parents=True, exist_ok=True)
    (root / REPORT_MD).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"json": REPORT_JSON.as_posix(), "markdown": REPORT_MD.as_posix(), "log": REPORT_LOG.as_posix()}


def _manifest_entries(source_dir: Path) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    for path in sorted(source_dir.rglob("*"), key=lambda item: item.as_posix()):
        if not path.is_file():
            continue
        rel = path.resolve().relative_to(source_dir.resolve()).as_posix()
        data = path.read_bytes()
        entries.append(
            {
                "rel_path": rel,
                "size": len(data),
                "mtime": path.stat().st_mtime,
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
    return entries


def _load_mission(ref: MissionRef) -> Dict[str, Any]:
    if not ref.mission_json.is_file():
        raise RuntimeError(f"Mission not found: {ref.mission_id}")
    payload = _load_json(ref.mission_json)
    if not payload:
        raise RuntimeError(f"Mission metadata invalid: {ref.mission_json}")
    return payload


def _save_mission(ref: MissionRef, mission_meta: Dict[str, Any]) -> None:
    mission_meta["updated_at"] = _utc_now()
    _save_json(ref.mission_json, mission_meta)


def _mission_paths_for_report(ref: MissionRef, root: Path) -> Dict[str, str]:
    return {
        "mission_dir": ref.mission_dir.resolve().relative_to(root.resolve()).as_posix(),
        "mission_json": ref.mission_json.resolve().relative_to(root.resolve()).as_posix(),
        "plan_md": ref.plan_md.resolve().relative_to(root.resolve()).as_posix(),
    }


def run_init(
    root: str | Path,
    *,
    title: str,
    channel: str,
    peer_id: str,
    thread_id: str = "",
    size: str = "auto",
    mission_id: str = "",
) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    policy = _ensure_policy(canonical_root)
    state = _ensure_state(canonical_root)

    safe_title = title.strip()
    if not safe_title:
        raise RuntimeError("title is required")
    safe_channel = channel.strip().lower()
    if safe_channel not in {"telegram", "discord", "whatsapp"}:
        raise RuntimeError("channel must be one of: telegram|discord|whatsapp")
    safe_peer = peer_id.strip()
    if not safe_peer:
        raise RuntimeError("peer_id is required")
    safe_thread = thread_id.strip()

    coverage = _knowledge_coverage(canonical_root, safe_title)
    chosen_size = _choose_size(size, safe_title, float(coverage["coverage_score"]), policy)
    profile = dict(policy.get("sizes", {}).get(chosen_size, {}))

    scope_key = _scope_key(safe_channel, safe_peer, safe_thread, safe_title)
    if mission_id.strip():
        safe_mission_id = _safe_mission_id(mission_id)
        counter_value = int(state.get("mission_counter_by_scope", {}).get(scope_key, 0))
    else:
        safe_mission_id, counter_value = _next_mission_id(state, scope_key=scope_key)
    ref = _mission_ref(canonical_root, policy, safe_mission_id)
    if ref.mission_dir.exists():
        raise RuntimeError(f"mission already exists: {safe_mission_id}")

    ref.prompts_dir.mkdir(parents=True, exist_ok=True)
    ref.events_ndjson.parent.mkdir(parents=True, exist_ok=True)

    threshold = float(policy.get("research_phase0", {}).get("coverage_threshold", 0.45))
    research_needed = bool(policy.get("research_phase0", {}).get("enabled", True)) and float(coverage["coverage_score"]) < threshold

    mission_meta: Dict[str, Any] = {
        "version": 1,
        "mission_id": safe_mission_id,
        "title": safe_title,
        "channel": safe_channel,
        "peer_id": safe_peer,
        "thread_id": safe_thread,
        "size": chosen_size,
        "scope_key": scope_key,
        "scope_counter": counter_value,
        "status": "active",
        "roles": profile.get("roles", []),
        "required_gates": profile.get("required_gates", []),
        "coverage_score": float(coverage["coverage_score"]),
        "coverage_tokens": coverage.get("tokens", []),
        "coverage_matched_tokens": coverage.get("matched_tokens", []),
        "coverage_matched_files": coverage.get("matched_files", []),
        "research_phase0_needed": research_needed,
        "learning_hashes": [],
        "learning_packages": [],
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
    }
    _save_mission(ref, mission_meta)
    ref.plan_md.write_text(_render_plan(mission_meta, profile), encoding="utf-8")

    _append_ndjson(
        ref.events_ndjson,
        {
            "ts": _utc_now(),
            "event": "init",
            "mission_id": safe_mission_id,
            "size": chosen_size,
            "research_phase0_needed": research_needed,
        },
    )

    missions = state.setdefault("missions", {})
    missions[safe_mission_id] = {
        "status": "active",
        "title": safe_title,
        "size": chosen_size,
        "updated_at": mission_meta["updated_at"],
        "path": ref.mission_dir.resolve().relative_to(canonical_root.resolve()).as_posix(),
    }
    state["last_run_utc"] = _utc_now()
    state["last_status"] = "success"
    _save_json(canonical_root / STATE_PATH, state)

    report = {
        "version": 1,
        "created_at": _utc_now(),
        "action": "init",
        "status": "success",
        "mission_id": safe_mission_id,
        "summary": {
            "size": chosen_size,
            "roles": profile.get("roles", []),
            "coverage_score": coverage["coverage_score"],
            "research_phase0_needed": research_needed,
        },
        "mission_paths": _mission_paths_for_report(ref, canonical_root),
    }
    paths = _write_report(canonical_root, report)
    return {"report": report, "paths": paths}


def run_emit_prompts(root: str | Path, *, mission_id: str) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    policy = _ensure_policy(canonical_root)
    state = _ensure_state(canonical_root)
    safe_mission_id = _safe_mission_id(mission_id)
    ref = _mission_ref(canonical_root, policy, safe_mission_id)
    mission = _load_mission(ref)

    role_catalog = dict(policy.get("role_catalog", {}))
    roles = [str(item) for item in mission.get("roles", []) if str(item).strip()]
    if not roles:
        roles = list(policy.get("sizes", {}).get(str(mission.get("size", "M")), {}).get("roles", []))

    plan_excerpt = ref.plan_md.read_text(encoding="utf-8", errors="replace")
    excerpt_lines = plan_excerpt.splitlines()[:120]
    excerpt = "\n".join(excerpt_lines)

    prompts_payload: List[Dict[str, Any]] = []
    md_lines: List[str] = [
        "# Mission Prompts Latest",
        "",
        f"- Mission ID: `{safe_mission_id}`",
        f"- Mission title: {mission.get('title', '')}",
        f"- Mission size: `{mission.get('size', '')}`",
        "",
    ]

    for role in roles:
        role_meta = role_catalog.get(role, {"name": f"Role {role}", "ownership": "GAP/NO VERIFICADO"})
        prompt = _prompt_text(role, role_meta, mission, excerpt)
        prompts_payload.append(
            {
                "mission_id": safe_mission_id,
                "role": role,
                "role_name": role_meta.get("name", ""),
                "delegate_default": "codex",
                "delegate_override_rule": "claude_code_if_plugins_rules_imports",
                "prompt": prompt,
            }
        )
        md_lines.extend([f"## Role {role}", "", prompt, ""])

    stamp = _stamp()
    ref.prompts_dir.mkdir(parents=True, exist_ok=True)
    mission_prompts_json = ref.prompts_dir / f"{stamp}_prompts.json"
    mission_prompts_md = ref.prompts_dir / f"{stamp}_prompts.md"

    mission_payload = {
        "version": 1,
        "created_at": _utc_now(),
        "mission_id": safe_mission_id,
        "roles": roles,
        "prompts": prompts_payload,
    }
    _save_json(mission_prompts_json, mission_payload)
    mission_prompts_md.write_text("\n".join(md_lines).strip() + "\n", encoding="utf-8")

    _save_json(canonical_root / PROMPTS_LATEST_JSON, mission_payload)
    (canonical_root / PROMPTS_LATEST_MD).write_text("\n".join(md_lines).strip() + "\n", encoding="utf-8")

    mission["last_prompts_generated_at"] = _utc_now()
    mission["last_prompts_paths"] = [
        mission_prompts_json.resolve().relative_to(canonical_root.resolve()).as_posix(),
        mission_prompts_md.resolve().relative_to(canonical_root.resolve()).as_posix(),
    ]
    _save_mission(ref, mission)
    _append_ndjson(
        ref.events_ndjson,
        {"ts": _utc_now(), "event": "emit_prompts", "mission_id": safe_mission_id, "roles": roles},
    )

    state["last_generated_prompts_mission_id"] = safe_mission_id
    state["last_run_utc"] = _utc_now()
    state["last_status"] = "success"
    _save_json(canonical_root / STATE_PATH, state)

    report = {
        "version": 1,
        "created_at": _utc_now(),
        "action": "emit-prompts",
        "status": "success",
        "mission_id": safe_mission_id,
        "summary": {"roles_count": len(roles), "roles": roles},
        "mission_prompt_paths": {
            "mission_json": mission_prompts_json.resolve().relative_to(canonical_root.resolve()).as_posix(),
            "mission_md": mission_prompts_md.resolve().relative_to(canonical_root.resolve()).as_posix(),
            "latest_json": PROMPTS_LATEST_JSON.as_posix(),
            "latest_md": PROMPTS_LATEST_MD.as_posix(),
        },
        "mission_paths": _mission_paths_for_report(ref, canonical_root),
    }
    paths = _write_report(canonical_root, report)
    return {"report": report, "paths": paths}


def _safe_read_source(path: Path, *, per_file_limit: int) -> Dict[str, Any]:
    raw = path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    try:
        text = raw.decode("utf-8")
        display = text[:per_file_limit]
        clipped = len(text) > len(display)
        return {
            "kind": "text",
            "path": path.as_posix(),
            "sha256": sha,
            "size": len(raw),
            "excerpt": display,
            "clipped": clipped,
        }
    except UnicodeDecodeError:
        return {
            "kind": "binary",
            "path": path.as_posix(),
            "sha256": sha,
            "size": len(raw),
            "excerpt": "",
            "clipped": False,
        }


def _render_learning_content(mission: Dict[str, Any], entries: Sequence[Dict[str, Any]], stdin_text: str) -> str:
    lines: List[str] = [
        f"# Mission Learning - {mission.get('mission_id', '')}",
        "",
        f"- Mission title: {mission.get('title', '')}",
        f"- Mission size: {mission.get('size', '')}",
        "- Captured in mission lifecycle (see EVENT_META for timestamp).",
        "",
        "## Key Learnings",
        "",
    ]
    if stdin_text.strip():
        lines.extend(["### Input (stdin)", "", stdin_text.strip(), ""])
    for item in entries:
        lines.append(f"### Source: `{item['path']}`")
        lines.append("")
        lines.append(f"- kind: `{item['kind']}`")
        lines.append(f"- size: `{item['size']}`")
        lines.append(f"- sha256: `{item['sha256'][:16]}...`")
        if item["kind"] == "text":
            lines.append("- excerpt:")
            lines.append("```text")
            lines.append(item["excerpt"].strip())
            lines.append("```")
            if item["clipped"]:
                lines.append("- note: excerpt clipped by policy limit.")
        else:
            lines.append("- note: binary source summarized only; no raw dump.")
        lines.append("")

    lines.extend(
        [
            "## How to Apply",
            "",
            "- Convert these learnings into reusable patterns/cards.",
            "- Keep source_ref to mission package and mission plan.",
            "- Avoid raw dumps in brain; promote summarized knowledge only.",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def run_learn(
    root: str | Path,
    *,
    mission_id: str,
    add_files: Sequence[str] | None = None,
    stdin_text: str = "",
) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    policy = _ensure_policy(canonical_root)
    state = _ensure_state(canonical_root)
    safe_mission_id = _safe_mission_id(mission_id)
    ref = _mission_ref(canonical_root, policy, safe_mission_id)
    mission = _load_mission(ref)

    phase0 = dict(policy.get("research_phase0", {}))
    per_file_limit = max(256, int(phase0.get("learning_max_chars", 12000) // 3))
    total_limit = max(1024, int(phase0.get("learning_max_chars", 12000)))

    safe_entries: List[Dict[str, Any]] = []
    for raw in add_files or []:
        raw = raw.strip()
        if not raw:
            continue
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = (canonical_root / candidate).resolve()
        else:
            candidate = candidate.resolve()
        if not candidate.is_file():
            raise RuntimeError(f"--add-file not found: {raw}")
        if canonical_root.resolve() not in candidate.parents and candidate.resolve() != canonical_root.resolve():
            raise RuntimeError(f"--add-file outside canonical root is not allowed: {candidate}")
        safe_entries.append(_safe_read_source(candidate, per_file_limit=per_file_limit))

    if not safe_entries and not stdin_text.strip():
        raise RuntimeError("learn requires --add-file and/or --stdin payload")

    content = _render_learning_content(mission, safe_entries, stdin_text)
    if len(content) > total_limit:
        content = content[:total_limit].rstrip() + "\n\n[TRUNCATED_BY_POLICY]\n"
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

    hashes = mission.get("learning_hashes", [])
    if not isinstance(hashes, list):
        hashes = []
    if bool(phase0.get("dedupe_by_hash", True)) and content_hash in hashes:
        report = {
            "version": 1,
            "created_at": _utc_now(),
            "action": "learn",
            "status": "skipped_duplicate",
            "mission_id": safe_mission_id,
            "summary": {"reason": "duplicate_content_hash", "content_hash": content_hash[:16]},
            "mission_paths": _mission_paths_for_report(ref, canonical_root),
        }
        paths = _write_report(canonical_root, report)
        return {"report": report, "paths": paths}

    drop_root = canonical_root / str(policy.get("paths", {}).get("learning_drop_root", "vault/inbox_raw/_pending_drop/mission_learning"))
    package_dir = drop_root / f"{safe_mission_id}_{_stamp()}"
    source_dir = package_dir / "source"
    source_dir.mkdir(parents=True, exist_ok=True)

    content_path = source_dir / "CONTENT.md"
    content_path.write_text(content, encoding="utf-8")
    event_meta = {
        "version": 1,
        "created_at": _utc_now(),
        "source_kind": "mission_learning",
        "mission_id": safe_mission_id,
        "mission_title": mission.get("title", ""),
        "recommended_domain": "openclaw_ops",
        "source_ref": ref.plan_md.resolve().relative_to(canonical_root.resolve()).as_posix(),
        "content_hash": content_hash,
    }
    _save_json(source_dir / "EVENT_META.json", event_meta)

    manifest = {
        "version": 1,
        "created_at": _utc_now(),
        "source_kind": "mission_learning",
        "origin": {"mission_id": safe_mission_id},
        "entries": _manifest_entries(source_dir),
    }
    manifest["file_count"] = len(manifest["entries"])
    _save_json(package_dir / "MANIFEST.json", manifest)

    readme = "\n".join(
        [
            "# Mission Learning Package",
            "",
            f"- mission_id: `{safe_mission_id}`",
            "- source_kind: `mission_learning`",
            "- files: `source/CONTENT.md`, `source/EVENT_META.json`, `MANIFEST.json`",
            "- generated for ingest via heartbeat pipeline.",
        ]
    )
    (package_dir / "README.md").write_text(readme + "\n", encoding="utf-8")

    hashes.append(content_hash)
    mission["learning_hashes"] = hashes[-500:]
    packages = mission.get("learning_packages", [])
    if not isinstance(packages, list):
        packages = []
    packages.append(package_dir.resolve().relative_to(canonical_root.resolve()).as_posix())
    mission["learning_packages"] = packages[-500:]
    mission["last_learning_at"] = _utc_now()
    _save_mission(ref, mission)
    _append_ndjson(
        ref.events_ndjson,
        {
            "ts": _utc_now(),
            "event": "learn",
            "mission_id": safe_mission_id,
            "content_hash": content_hash,
            "package": package_dir.resolve().relative_to(canonical_root.resolve()).as_posix(),
        },
    )

    state["last_run_utc"] = _utc_now()
    state["last_status"] = "success"
    _save_json(canonical_root / STATE_PATH, state)

    report = {
        "version": 1,
        "created_at": _utc_now(),
        "action": "learn",
        "status": "success",
        "mission_id": safe_mission_id,
        "summary": {
            "content_hash": content_hash[:16],
            "entries_count": len(safe_entries),
            "stdin_used": bool(stdin_text.strip()),
            "package_path": package_dir.resolve().relative_to(canonical_root.resolve()).as_posix(),
        },
        "learning_paths": {
            "package": package_dir.resolve().relative_to(canonical_root.resolve()).as_posix(),
            "manifest": (package_dir / "MANIFEST.json").resolve().relative_to(canonical_root.resolve()).as_posix(),
            "event_meta": (source_dir / "EVENT_META.json").resolve().relative_to(canonical_root.resolve()).as_posix(),
            "content": content_path.resolve().relative_to(canonical_root.resolve()).as_posix(),
        },
        "mission_paths": _mission_paths_for_report(ref, canonical_root),
    }
    paths = _write_report(canonical_root, report)
    return {"report": report, "paths": paths}


def run_close(root: str | Path, *, mission_id: str, summary: str = "") -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    policy = _ensure_policy(canonical_root)
    state = _ensure_state(canonical_root)
    safe_mission_id = _safe_mission_id(mission_id)
    ref = _mission_ref(canonical_root, policy, safe_mission_id)
    mission = _load_mission(ref)

    mission["status"] = "completed"
    mission["closed_at"] = _utc_now()
    if summary.strip():
        mission["close_summary"] = summary.strip()
    _save_mission(ref, mission)
    _append_ndjson(
        ref.events_ndjson,
        {"ts": _utc_now(), "event": "close", "mission_id": safe_mission_id, "summary": summary.strip()},
    )

    state_missions = state.setdefault("missions", {})
    item = state_missions.get(safe_mission_id, {})
    if not isinstance(item, dict):
        item = {}
    item["status"] = "completed"
    item["updated_at"] = _utc_now()
    state_missions[safe_mission_id] = item
    state["last_run_utc"] = _utc_now()
    state["last_status"] = "success"
    _save_json(canonical_root / STATE_PATH, state)

    close_summary_path = ref.mission_dir / "CLOSE_SUMMARY.md"
    close_summary_lines = [
        "# Mission Close Summary",
        "",
        f"- Mission ID: `{safe_mission_id}`",
        f"- Closed at: `{mission['closed_at']}`",
        "",
        "## Outcome",
        "",
        summary.strip() or "- Completed without explicit close summary.",
    ]
    close_summary_path.write_text("\n".join(close_summary_lines) + "\n", encoding="utf-8")

    report = {
        "version": 1,
        "created_at": _utc_now(),
        "action": "close",
        "status": "success",
        "mission_id": safe_mission_id,
        "summary": {"completed": True, "close_summary_provided": bool(summary.strip())},
        "mission_paths": _mission_paths_for_report(ref, canonical_root),
        "close_summary_path": close_summary_path.resolve().relative_to(canonical_root.resolve()).as_posix(),
    }
    paths = _write_report(canonical_root, report)
    return {"report": report, "paths": paths}


def run_status(root: str | Path, *, mission_id: str = "") -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    policy = _ensure_policy(canonical_root)
    state = _ensure_state(canonical_root)
    missions = state.get("missions", {})
    if not isinstance(missions, dict):
        missions = {}

    details: Dict[str, Any] = {}
    if mission_id.strip():
        safe_mission_id = _safe_mission_id(mission_id)
        ref = _mission_ref(canonical_root, policy, safe_mission_id)
        mission = _load_mission(ref)
        details = mission
        selected = [safe_mission_id]
    else:
        selected = sorted(missions.keys())
        for mid in selected:
            ref = _mission_ref(canonical_root, policy, mid)
            if ref.mission_json.is_file():
                meta = _load_json(ref.mission_json)
                details[mid] = {
                    "status": meta.get("status", ""),
                    "size": meta.get("size", ""),
                    "title": meta.get("title", ""),
                    "updated_at": meta.get("updated_at", ""),
                }

    report = {
        "version": 1,
        "created_at": _utc_now(),
        "action": "status",
        "status": "success",
        "mission_id": mission_id.strip(),
        "summary": {
            "missions_total": len(missions),
            "missions_selected": len(selected),
            "active_count": sum(1 for item in details.values() if isinstance(item, dict) and item.get("status") == "active")
            if isinstance(details, dict)
            else 0,
        },
        "details": details,
    }
    paths = _write_report(canonical_root, report)
    return {"report": report, "paths": paths}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Mission orchestration helper")
    parser.add_argument("--root", default=".")
    parser.add_argument("--init", action="store_true")
    parser.add_argument("--emit-prompts", action="store_true")
    parser.add_argument("--learn", action="store_true")
    parser.add_argument("--close", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--mission", default="")
    parser.add_argument("--mission-id", default="")
    parser.add_argument("--title", default="")
    parser.add_argument("--channel", default="")
    parser.add_argument("--peer_id", default="")
    parser.add_argument("--thread_id", default="")
    parser.add_argument("--size", default="auto")
    parser.add_argument("--add-file", action="append", default=[])
    parser.add_argument("--stdin", action="store_true")
    parser.add_argument("--summary", default="")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    actions = [args.init, args.emit_prompts, args.learn, args.close, args.status]
    if sum(1 for item in actions if item) != 1:
        raise SystemExit("Use exactly one action: --init | --emit-prompts | --learn | --close | --status")

    if args.init:
        out = run_init(
            args.root,
            title=args.title,
            channel=args.channel,
            peer_id=args.peer_id,
            thread_id=args.thread_id,
            size=args.size,
            mission_id=args.mission_id,
        )
    elif args.emit_prompts:
        mission = args.mission or args.mission_id
        out = run_emit_prompts(args.root, mission_id=mission)
    elif args.learn:
        mission = args.mission or args.mission_id
        stdin_text = sys.stdin.read() if args.stdin else ""
        out = run_learn(args.root, mission_id=mission, add_files=args.add_file, stdin_text=stdin_text)
    elif args.close:
        mission = args.mission or args.mission_id
        out = run_close(args.root, mission_id=mission, summary=args.summary)
    else:
        mission = args.mission or args.mission_id
        out = run_status(args.root, mission_id=mission)

    print(json.dumps({"report": out["report"], "paths": out["paths"]}, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
