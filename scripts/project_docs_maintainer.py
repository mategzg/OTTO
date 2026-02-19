#!/usr/bin/env python3
"""Maintain canonical project docs from repository source-of-truth."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.repo_root import get_canonical_root

POLICY_PATH = Path("state/project_docs_policy.json")
STATE_PATH = Path("state/project_docs_state.json")
REPORT_JSON = Path("docs/_inbox/project_docs_report_latest.json")
REPORT_MD = Path("docs/_inbox/project_docs_report_latest.md")
LOG_JSON = Path("logs/project_docs_latest.json")

PROJECT_BRIEF = Path("PROJECT_BRIEF.md")
REPO_MAP = Path("REPO_MAP.md")
REPO_MAP_DIR = Path("repo_map")

REPO_MAP_FILES = [
    Path("repo_map/00_INDEX.md"),
    Path("repo_map/10_RUNTIME_INGRESS.md"),
    Path("repo_map/20_INGEST_PIPELINE.md"),
    Path("repo_map/30_MEMORYOS.md"),
    Path("repo_map/40_OUTBOX_APPROVALS.md"),
    Path("repo_map/50_HOOKS_OPENCLAW.md"),
    Path("repo_map/60_POLICIES_STATE.md"),
    Path("repo_map/70_TESTS_GATES.md"),
    Path("repo_map/80_PROD_SAFETY.md"),
    Path("repo_map/90_LEGACY_RECOVERY.md"),
]

MANDATORY_SOURCES = [
    Path("scripts/heartbeat_worker.py"),
    Path("scripts/autonomy_tick.py"),
    Path("scripts/channel_ingress_adapter.py"),
    Path("scripts/session_memory_manager.py"),
    Path("scripts/brain_ingest_router.py"),
    Path("scripts/write_router.py"),
    Path("scripts/dropbox_intake.py"),
    Path("scripts/chatgpt_export_normalize.py"),
    Path("scripts/outbox_delivery.py"),
    Path("scripts/openclaw_cli.py"),
    Path("scripts/approval_manager.py"),
    Path("scripts/sg_promotion.py"),
    Path("scripts/hook_backlog.py"),
    Path("scripts/capability_inventory.py"),
    Path("scripts/legacy_coldstore_audit.py"),
    Path("scripts/legacy_gap_detector.py"),
    Path("scripts/legacy_capability_inventory.py"),
    Path("scripts/legacy_recovery_worker.py"),
    Path("scripts/prod_doctor.py"),
    Path("scripts/safety_switch.py"),
    Path("hooks/otto-runtime-bridge/HOOK.md"),
    Path("hooks/otto-runtime-bridge/handler.js"),
    Path("openclaw/CONTEXT_MAP.md"),
]

DEFAULT_POLICY: Dict[str, Any] = {
    "version": 1,
    "enabled": True,
    "interval_minutes": 720,
    "min_changed_files_to_trigger": 1,
    "signature_allowlist": [
        "AGENTS.md",
        "CLAUDE.md",
        "CEO.md",
        "SOUL.md",
        "INDEX.md",
        "openclaw/*.md",
        "scripts/*.py",
        "state/channel_runtime_policy.json",
        "state/heartbeat_policy.json",
        "state/write_router_policy.json",
        "state/memory_policy.json",
        "state/sg_policy.json",
        "state/instruction_surface_policy.json",
        "state/workspace_hygiene_policy.json",
        "state/project_docs_policy.json",
        "state/legacy_recovery_policy.json",
        "hooks/**",
        "brain/domains/openclaw_ops/**",
        "brain/domains/ingest/**",
        "memory/00_INDEX.md",
    ],
    "signature_exclusions": [
        "vault/**",
        "docs/_inbox/**",
        "logs/**",
        "__pycache__/**",
        ".pytest_cache/**",
        ".venv/**",
        "node_modules/**",
        "dist/**",
        "build/**",
        "hooks/**/node_modules/**",
        "hooks/**/dist/**",
        "hooks/**/.cache/**",
    ],
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_now() -> str:
    return _utc_now().isoformat()


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _save_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_if_changed(path: Path, content: str) -> bool:
    new_text = content.rstrip() + "\n"
    if path.is_file():
        old = path.read_text(encoding="utf-8")
        if old == new_text:
            return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new_text, encoding="utf-8")
    return True


def _parse_iso(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _ensure_policy(root: Path) -> Dict[str, Any]:
    path = root / POLICY_PATH
    current = _load_json(path)
    policy = dict(DEFAULT_POLICY)
    policy.update(current)
    if not path.is_file():
        _save_json(path, policy)
    else:
        # Keep file synchronized if keys were introduced.
        if any(key not in current for key in DEFAULT_POLICY):
            _save_json(path, policy)
    return policy


def _default_state() -> Dict[str, Any]:
    return {
        "version": 1,
        "last_signature": "",
        "last_run_utc": "",
        "last_status": "",
        "last_updated_files": [],
        "last_gap_count": 0,
        "last_changed_files": [],
        "last_file_hashes": {},
    }


def _load_state(root: Path) -> Dict[str, Any]:
    state = _default_state()
    state.update(_load_json(root / STATE_PATH))
    return state


def _collect_signature_files(root: Path, policy: Dict[str, Any]) -> List[Path]:
    allowlist = [str(item).strip() for item in policy.get("signature_allowlist", []) if str(item).strip()]
    exclusions = [str(item).strip() for item in policy.get("signature_exclusions", []) if str(item).strip()]
    selected: set[Path] = set()
    for pattern in allowlist:
        for candidate in root.glob(pattern):
            if candidate.is_file():
                selected.add(candidate.resolve())
    if not selected:
        return []

    out: List[Path] = []
    for item in sorted(selected, key=lambda p: p.as_posix()):
        rel = item.relative_to(root).as_posix()
        excluded = any(Path(rel).match(ex) for ex in exclusions)
        if excluded:
            continue
        out.append(item)
    return out


def _build_signature(root: Path, files: Iterable[Path]) -> Tuple[str, Dict[str, str]]:
    rows: List[Tuple[str, str]] = []
    for path in files:
        rel = path.resolve().relative_to(root.resolve()).as_posix()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        rows.append((rel, digest))
    rows.sort(key=lambda item: item[0])
    per_file = {rel: digest for rel, digest in rows}
    aggregate = hashlib.sha256()
    for rel, digest in rows:
        aggregate.update(rel.encode("utf-8"))
        aggregate.update(b"\n")
        aggregate.update(digest.encode("utf-8"))
        aggregate.update(b"\n")
    return aggregate.hexdigest(), per_file


def _changed_files(old: Dict[str, str], new: Dict[str, str]) -> List[str]:
    keys = sorted(set(old) | set(new))
    changed: List[str] = []
    for key in keys:
        if old.get(key, "") != new.get(key, ""):
            changed.append(key)
    return changed


def _get_json(root: Path, rel_path: str) -> Dict[str, Any]:
    return _load_json(root / rel_path)


def _mandatory_gaps(root: Path) -> List[str]:
    gaps: List[str] = []
    for rel in MANDATORY_SOURCES:
        if not (root / rel).is_file():
            gaps.append(f"{rel.as_posix()} missing")
    return gaps


def _collect_facts(root: Path) -> Dict[str, Any]:
    heartbeat_policy = _get_json(root, "state/heartbeat_policy.json")
    channel_runtime_policy = _get_json(root, "state/channel_runtime_policy.json")
    write_router_policy = _get_json(root, "state/write_router_policy.json")
    memory_policy = _get_json(root, "state/memory_policy.json")
    legacy_recovery_policy = _get_json(root, "state/legacy_recovery_policy.json")
    sg_policy = _get_json(root, "state/sg_policy.json")
    instruction_surface = _get_json(root, "state/instruction_surface_policy.json")
    hygiene_policy = _get_json(root, "state/workspace_hygiene_policy.json")

    canonical_marker = _get_json(root, ".openclaw/CANONICAL_ROOT.json")
    canonical_root = str(canonical_marker.get("root_realpath", "")).strip()

    tiers = channel_runtime_policy.get("tiers", {}) if isinstance(channel_runtime_policy.get("tiers", {}), dict) else {}
    promotion_rules = sg_policy.get("promotion_rules", {}) if isinstance(sg_policy.get("promotion_rules", {}), dict) else {}
    reserved = instruction_surface.get("reserved_filenames", []) if isinstance(instruction_surface.get("reserved_filenames", []), list) else []

    gaps = _mandatory_gaps(root)
    if not canonical_root:
        gaps.append(".openclaw/CANONICAL_ROOT.json missing root_realpath")
    if not heartbeat_policy:
        gaps.append("state/heartbeat_policy.json missing or invalid")
    if not channel_runtime_policy:
        gaps.append("state/channel_runtime_policy.json missing or invalid")
    if not legacy_recovery_policy:
        gaps.append("state/legacy_recovery_policy.json missing or invalid")

    categories_raw = write_router_policy.get("categories", {})
    if isinstance(categories_raw, dict):
        categories = sorted(str(k) for k in categories_raw.keys())
    elif isinstance(categories_raw, list):
        categories = sorted(str(item) for item in categories_raw if str(item).strip())
    else:
        categories = []

    record_types_raw = memory_policy.get("record_types", {})
    if isinstance(record_types_raw, dict):
        record_types = sorted(str(k) for k in record_types_raw.keys())
    elif isinstance(record_types_raw, list):
        record_types = sorted(str(item) for item in record_types_raw if str(item).strip())
    else:
        record_types = []

    return {
        "canonical_root": canonical_root or str(root.resolve()),
        "heartbeat_interval_minutes": int(heartbeat_policy.get("interval_minutes", 30)),
        "channel_tiers": sorted(tiers.keys()),
        "sg_promotion_rules": {
            "low": str(promotion_rules.get("low", "unknown")),
            "medium": str(promotion_rules.get("medium", "unknown")),
            "high": str(promotion_rules.get("high", "unknown")),
        },
        "worker_auth_mode": str(sg_policy.get("worker_auth_mode", "unknown")),
        "reserved_instruction_filenames": [str(item) for item in reserved],
        "hygiene_exclusions_count": len(hygiene_policy.get("ignore_globs", [])) if isinstance(hygiene_policy.get("ignore_globs", []), list) else 0,
        "write_router_categories": categories,
        "memory_record_types": record_types,
        "legacy_recovery_enabled": bool(legacy_recovery_policy.get("enabled", False)),
        "legacy_recovery_interval_minutes": int(legacy_recovery_policy.get("interval_minutes", 720)),
        "legacy_recovery_scan_interval_hours": int(legacy_recovery_policy.get("scan_interval_hours", 12)),
        "legacy_recovery_allow_types": [
            str(item) for item in legacy_recovery_policy.get("allow_types", []) if str(item).strip()
        ],
        "gaps": gaps,
    }


def _render_project_brief(facts: Dict[str, Any]) -> str:
    gaps = facts["gaps"]
    gap_lines = "\n".join(f"- GAP/NO VERIFICADO: {item}" for item in gaps) if gaps else "- Ninguno detectado en esta corrida."
    tiers = ", ".join(facts["channel_tiers"]) if facts["channel_tiers"] else "GAP/NO VERIFICADO"
    write_router = ", ".join(facts["write_router_categories"]) if facts["write_router_categories"] else "GAP/NO VERIFICADO"
    memory_types = ", ".join(facts["memory_record_types"]) if facts["memory_record_types"] else "GAP/NO VERIFICADO"

    return f"""# PROJECT_BRIEF

## Scope y Proposito

Repositorio canonico de OTTO/OpenClaw-MemoryOS en `{facts["canonical_root"]}`.  
Objetivo operativo: ejecutar runtime NL-first multi-canal con zero-mix de sesiones, ingest por bloques, MemoryOS estructurado y evidencia determinista.

## Invariantes Operativas

- Zero-mix por session_id (chat/canal/thread): `scripts/session_memory_manager.py`.
- Anti-overread: routing por indices/nodos/cards; no lectura masiva de crudo.
- No indexar crudo: `scripts/brain_index_build.py`, politicas en `state/workspace_hygiene_policy.json`.
- No delete destructivo; quarantine/salvage para casos de riesgo.
- Instruction surface reservada (`AGENTS*`, `CLAUDE*`) con doctor dedicado: `scripts/instruction_surface_doctor.py`.

## Arquitectura Real (Componentes + Source Files)

- Runtime ingress por canal: `scripts/channel_ingress_adapter.py`, `scripts/nl_intent_classifier.py`, `hooks/otto-runtime-bridge/handler.js`.
- Session memory + compact/distill: `scripts/session_memory_manager.py`.
- Ingest pipeline: `scripts/dropbox_intake.py` -> `scripts/chatgpt_export_normalize.py` -> `scripts/corpus_triage.py` -> `scripts/brain_ingest_router.py`.
- Write Router: `scripts/write_router.py` (categorias detectadas: {write_router}).
- MemoryOS: `scripts/memory_capture.py`, `scripts/memory_compact.py`, `scripts/memory_index_build.py`, `scripts/memory_query.py` (tipos: {memory_types}).
- Outbox/approvals/SG: `scripts/outbox_queue.py`, `scripts/outbox_delivery.py`, `scripts/openclaw_cli.py`, `scripts/approval_manager.py`, `scripts/sg_promotion.py`, `scripts/sg_channel_policy.py`.
- Orquestacion: `scripts/heartbeat_worker.py`, `scripts/autonomy_tick.py`.
- Hardening prod: `scripts/hook_backlog.py`, `scripts/prod_doctor.py`, `scripts/safety_switch.py`.

## Workflows Canonicos (Auto)

1. Mensaje entrante -> ingress adapter -> append session -> intent routing -> posibles acciones (drop/memory/approval).
2. Heartbeat ({facts["heartbeat_interval_minutes"]} min) ejecuta intake/normalize/runtime/outbox/autonomia.
3. Outbox queue autoridad: `docs/_inbox/outbox_queue.ndjson`; entrega por `outbox_delivery` via OpenClaw CLI.
4. Memory inbox (`docs/_inbox/memory_inbox.ndjson`) -> compact/index -> NDJSON canonicos en `memory/`.

## Operacion por Canal y Guardrails

- Tiers definidos en `state/channel_runtime_policy.json`: {tiers}.
- Telegram owner: aprobaciones/notificaciones.
- Discord: domain inference por `channel_name`, thread episodico.
- WhatsApp: dominio SG; no memoria personal.
- SG promotions: low={facts["sg_promotion_rules"]["low"]}, medium={facts["sg_promotion_rules"]["medium"]}, high={facts["sg_promotion_rules"]["high"]}.
- Worker auth mode: `{facts["worker_auth_mode"]}`.

## Contribucion Segura (Do/Don't + Gates)

- Tocar preferentemente: `scripts/`, `state/`, `brain/`, `openclaw/`, `tests/`.
- No tocar como fuente operativa: `vault/_quarantine/**`, `vault/_salvage/**`, `vault/inbox_raw/**`.
- Respetar reserved instruction surface: {", ".join(facts["reserved_instruction_filenames"]) if facts["reserved_instruction_filenames"] else "GAP/NO VERIFICADO"}.
- Gates minimos:
  - `pytest -q`
  - `python3 scripts/heartbeat_worker.py --once --root . --force`
  - `python3 scripts/repo_reality_doctor.py --scan --json`
  - `python3 scripts/workspace_hygiene_doctor.py --scan`
  - `python3 scripts/instruction_surface_doctor.py --scan --root .`
  - `python3 scripts/brain_index_build.py`

## Operational Safety & Recovery

- Hook bridge fail-open: backlog en `state/hook_backlog/events.ndjson` + replay por heartbeat.
- Safety switch global: `state/safety_switch.json` detiene automatizaciones cuando hay degradacion.
- Prod doctor offline-first: `scripts/prod_doctor.py` reporta compatibilidad real y gaps verificables.
- Procedimiento de recovery: `repo_map/80_PROD_SAFETY.md`.
- Legacy recovery (coldstore): `scripts/capability_inventory.py` -> `scripts/legacy_coldstore_audit.py` -> `scripts/legacy_gap_detector.py` -> `scripts/legacy_capability_inventory.py` -> `scripts/legacy_recovery_worker.py`.
- Policy de recovery: `state/legacy_recovery_policy.json` (enabled=`{facts["legacy_recovery_enabled"]}`, interval={facts["legacy_recovery_interval_minutes"]}m, scan_interval={facts["legacy_recovery_scan_interval_hours"]}h, allow_types={",".join(facts["legacy_recovery_allow_types"]) or "GAP/NO VERIFICADO"}).

## GAPS / NO VERIFICADO

{gap_lines}
"""


def _render_repo_map_portal() -> str:
    return """# REPO_MAP

Portal de navegacion minima para OTTO/subagentes.

## Zonas del Repo

- `brain/`: nodos/router/cards de conocimiento.
- `memory/`: memoria canonica estructurada.
- `scripts/`: runtime, ingest, memory, approvals, doctors.
- `state/`: politicas y estado persistente.
- `openclaw/`: mapa de contexto y compatibilidad OpenClaw.
- `hooks/`: bridge/event wiring.
- `docs/_inbox/`: reportes latest deterministas.
- `logs/`: logs latest deterministas.
- `vault/`: crudo/pending/quarantine (no indexar como conocimiento).
- `tests/`: cobertura de flujos criticos y gates.

## Si Necesitas X -> Lee A -> B -> C

- Ejecutar runtime diario: `repo_map/00_INDEX.md` -> `repo_map/10_RUNTIME_INGRESS.md` -> `scripts/heartbeat_worker.py`.
- Entender ingest por bloques: `repo_map/20_INGEST_PIPELINE.md` -> `scripts/dropbox_intake.py` -> `scripts/brain_ingest_router.py`.
- Consultar MemoryOS: `repo_map/30_MEMORYOS.md` -> `scripts/memory_query.py` -> `memory/00_INDEX.md`.
- Resolver approvals/outbox: `repo_map/40_OUTBOX_APPROVALS.md` -> `scripts/approval_manager.py` -> `scripts/outbox_delivery.py`.
- Revisar politicas/estado: `repo_map/60_POLICIES_STATE.md` -> `state/*.json`.
- Validar calidad antes de cerrar: `repo_map/70_TESTS_GATES.md` -> `tests/`.
- Hardening/recovery productivo: `repo_map/80_PROD_SAFETY.md` -> `scripts/hook_backlog.py` -> `scripts/safety_switch.py`.
- Auditar coldstore y recuperar por lotes: `repo_map/90_LEGACY_RECOVERY.md` -> `scripts/legacy_gap_detector.py` -> `scripts/legacy_capability_inventory.py` -> `scripts/legacy_recovery_worker.py`.

## Router

- `repo_map/00_INDEX.md`
- `openclaw/CONTEXT_MAP.md`
"""


def _render_repo_map_nodes() -> Dict[Path, str]:
    return {
        Path("repo_map/00_INDEX.md"): """# REPO MAP INDEX

Router por intencion:

- Runtime ingress y sesiones: `repo_map/10_RUNTIME_INGRESS.md`
- Ingest universal por bloques: `repo_map/20_INGEST_PIPELINE.md`
- MemoryOS (capture/compact/index/query): `repo_map/30_MEMORYOS.md`
- Outbox + approvals + SG: `repo_map/40_OUTBOX_APPROVALS.md`
- Hooks OpenClaw y bridge: `repo_map/50_HOOKS_OPENCLAW.md`
- Politicas y estado: `repo_map/60_POLICIES_STATE.md`
- Tests y gates: `repo_map/70_TESTS_GATES.md`
- Prod safety / recovery: `repo_map/80_PROD_SAFETY.md`
- Legacy recovery (salvage/quarantine): `repo_map/90_LEGACY_RECOVERY.md`
""",
        Path("repo_map/10_RUNTIME_INGRESS.md"): """# 10 Runtime Ingress

Lectura minima:

1. `scripts/channel_ingress_adapter.py`
2. `scripts/session_memory_manager.py`
3. `scripts/nl_intent_classifier.py`

Clave:

- Cada evento se normaliza y persiste en sesion deterministica (zero-mix).
- Session identity incluye canal/peer/thread y evita mezcla entre chats.
- Discord propaga `domain_slug`; WhatsApp aplica politicas SG.
""",
        Path("repo_map/20_INGEST_PIPELINE.md"): """# 20 Ingest Pipeline

Lectura minima:

1. `scripts/dropbox_intake.py`
2. `scripts/chatgpt_export_normalize.py`
3. `scripts/corpus_triage.py`
4. `scripts/brain_ingest_router.py`

Flujo:

- `vault/inbox_raw/_pending_drop` -> intake a `vault/inbox_raw/sources/*`.
- Normalizacion (si aplica) y slicing para cargas grandes.
- Triage genera señal/plan.
- Plan/apply crea derivados (brain/cards/memory inbox) y mueve processed.
""",
        Path("repo_map/30_MEMORYOS.md"): """# 30 MemoryOS

Lectura minima:

1. `scripts/memory_capture.py`
2. `scripts/memory_compact.py`
3. `scripts/memory_index_build.py`
4. `scripts/memory_query.py`

Ubicaciones:

- Inbox append-only: `docs/_inbox/memory_inbox.ndjson`
- Canonico: `memory/03_PREFERENCES.ndjson`, `memory/04_PROJECTS.ndjson`, `memory/05_DECISIONS.ndjson`, `memory/06_TIMELINE.ndjson`
- Indice: `state/memory_index.json`

Regla:

- Best-known/supersedes por tema; no expiracion por edad.
""",
        Path("repo_map/40_OUTBOX_APPROVALS.md"): """# 40 Outbox + Approvals

Lectura minima:

1. `scripts/outbox_queue.py`
2. `scripts/outbox_delivery.py`
3. `scripts/approval_manager.py`
4. `scripts/sg_promotion.py`
5. `scripts/openclaw_cli.py`

Autoridad:

- Cola saliente: `docs/_inbox/outbox_queue.ndjson`
- Snapshot legible: `docs/_inbox/outbox_latest.md`

Reglas:

- Aprobaciones del owner por Telegram (NL sin IDs).
- SG promotions: low auto; medium/high con approval.
- Delivery intenta OpenClaw CLI; si falla, item queda pending con reason.
""",
        Path("repo_map/50_HOOKS_OPENCLAW.md"): """# 50 Hooks OpenClaw

Lectura minima:

1. `hooks/otto-runtime-bridge/HOOK.md`
2. `hooks/otto-runtime-bridge/handler.js`
3. `scripts/channel_ingress_adapter.py`

Notas:

- Hook bridge captura `message:received` y `message:sent`.
- Bridge esta marcado experimental; runtime canonico vive en scripts/policies del workspace.
- Compatibilidad OpenClaw documentada en `openclaw/CONTEXT_MAP.md`.
""",
        Path("repo_map/60_POLICIES_STATE.md"): """# 60 Policies + State

Politicas clave:

- `state/channel_runtime_policy.json`: tiers, budgets, triggers.
- `state/heartbeat_policy.json`: cadencia y limites heartbeat.
- `state/write_router_policy.json`: routing de ingestion/escritura.
- `state/memory_policy.json`: schema de MemoryOS.
- `state/sg_policy.json`: auth worker + promotion rules.
- `state/instruction_surface_policy.json`: reserved filenames/allowlist.
- `state/workspace_hygiene_policy.json`: exclusiones y clasificacion hygiene.
- `state/project_docs_policy.json`: mantenimiento de PROJECT_BRIEF/REPO_MAP.

Estado operativo:

- `state/autonomy_state.json`
- `state/project_docs_state.json`
- `state/sg_worker_pairings.json`
""",
        Path("repo_map/70_TESTS_GATES.md"): """# 70 Tests + Gates

Comandos recomendados:

- `pytest -q`
- `python3 scripts/heartbeat_worker.py --once --root . --force`
- `python3 scripts/repo_reality_doctor.py --scan --json`
- `python3 scripts/workspace_hygiene_doctor.py --scan`
- `python3 scripts/instruction_surface_doctor.py --scan --root .`
- `python3 scripts/brain_index_build.py`

Tests relevantes por dominio:

- runtime/ingress: `tests/test_channel_ingress_and_approvals.py`
- heartbeat: `tests/test_heartbeat_worker.py`
- outbox/delivery: `tests/test_outbox_queue_and_delivery_mock_cli.py`
- memory: `tests/test_memory_pipeline.py`
- doctors/hygiene/surface: `tests/test_repo_reality_doctor.py`, `tests/test_workspace_hygiene.py`, `tests/test_instruction_surface_doctor.py`
""",
        Path("repo_map/80_PROD_SAFETY.md"): """# 80 Prod Safety

Rutas minimas:

1. Hook backlog: `scripts/hook_backlog.py` + `state/hook_backlog_policy.json`.
2. Safety switch: `scripts/safety_switch.py` + `state/safety_switch.json`.
3. Prod doctor: `scripts/prod_doctor.py` + `docs/_inbox/prod_doctor_latest.json`.
4. Orquestacion: `scripts/heartbeat_worker.py` (replay/backoff/autopause).

Checklist de recuperacion:

- Ver estado global: `python3 scripts/safety_switch.py --status`.
- Ver backlog pending/fallos: `python3 scripts/hook_backlog.py --scan --root .`.
- Forzar replay controlado: `python3 scripts/hook_backlog.py --replay --root .`.
- Si procede, reanudar: `python3 scripts/safety_switch.py --resume --reason "manual_recovery"`.
- Ejecutar heartbeat forzado: `python3 scripts/heartbeat_worker.py --once --root . --force`.
- Audit/packaging de coldstore: `repo_map/90_LEGACY_RECOVERY.md`.
""",
        Path("repo_map/90_LEGACY_RECOVERY.md"): """# 90 Legacy Recovery

Lectura minima:

1. `scripts/capability_inventory.py`
2. `scripts/legacy_coldstore_audit.py`
3. `scripts/legacy_gap_detector.py`
4. `scripts/legacy_capability_inventory.py`
5. `scripts/legacy_recovery_worker.py`

Objetivo:

- Auditar `vault/_salvage/**` y `vault/_quarantine/**` sin restaurar destructivamente.
- Detectar capacidades potenciales faltantes vs repositorio actual.
- Preparar recuperacion por lotes solo para documentacion segura (no codigo).

Reglas:

- `state/legacy_recovery_policy.json` manda; `enabled=false` por defecto.
- Legacy Gap v2 suprime ruido de path y artefactos de ejecucion (`docs/_inbox/**`, `logs/**`, `ops/**`, `copilots/**`).
- `scripts/legacy_capability_inventory.py` tipa candidatos (`script/hook/policy_state/brain_node/skill/doc_value`) y marca `GAP/NO VERIFICADO` cuando no hay equivalencia clara.
- Recovery worker v2 solo empaqueta tipos permitidos por policy (`doc_value`,`brain_node` por default) y nunca auto-mergea codigo.
- Packaging en `vault/inbox_raw/_pending_drop/legacy_recovery/` con `MANIFEST.json` + `EVENT_META.json` (`source_kind=legacy_recovery_v2`).
""",
    }


def _build_docs(root: Path, facts: Dict[str, Any]) -> Dict[Path, str]:
    docs: Dict[Path, str] = {
        PROJECT_BRIEF: _render_project_brief(facts),
        REPO_MAP: _render_repo_map_portal(),
    }
    docs.update(_render_repo_map_nodes())
    return docs


def _docs_exist(root: Path) -> bool:
    required = [PROJECT_BRIEF, REPO_MAP] + REPO_MAP_FILES
    return all((root / item).is_file() for item in required)


def _update_state(root: Path, state: Dict[str, Any]) -> None:
    _save_json(root / STATE_PATH, state)


def _report_paths() -> Dict[str, str]:
    return {
        "json": REPORT_JSON.as_posix(),
        "markdown": REPORT_MD.as_posix(),
        "log": LOG_JSON.as_posix(),
    }


def _write_report(root: Path, report: Dict[str, Any]) -> None:
    _save_json(root / REPORT_JSON, report)
    _save_json(root / LOG_JSON, report)
    lines = [
        "# Project Docs Report",
        "",
        f"- Status: `{report.get('status', '')}`",
        f"- Signature old: `{report.get('signature_old', '')}`",
        f"- Signature new: `{report.get('signature_new', '')}`",
        f"- Changed files count: {report.get('changed_files_count', 0)}",
        f"- Gap count: {report.get('gap_count', 0)}",
        f"- Updated files count: {len(report.get('updated_files', []))}",
        f"- Paths: `{', '.join(report.get('updated_files', [])) or '(none)'}`",
    ]
    if report.get("changed_files", []):
        lines.extend(["", "## Changed Files (top 50)", ""])
        for item in report["changed_files"][:50]:
            lines.append(f"- `{item}`")
    if report.get("gaps", []):
        lines.extend(["", "## GAPS / NO VERIFICADO", ""])
        for item in report["gaps"]:
            lines.append(f"- {item}")
    (root / REPORT_MD).parent.mkdir(parents=True, exist_ok=True)
    (root / REPORT_MD).write_text("\n".join(lines) + "\n", encoding="utf-8")


def _should_skip_interval(policy: Dict[str, Any], state: Dict[str, Any], now: datetime, force: bool) -> bool:
    if force:
        return False
    last = _parse_iso(str(state.get("last_run_utc", "")))
    if last is None:
        return False
    interval = max(1, int(policy.get("interval_minutes", 720)))
    return (now - last) < timedelta(minutes=interval)


def _compute_context(root: Path) -> Dict[str, Any]:
    policy = _ensure_policy(root)
    state = _load_state(root)
    files = _collect_signature_files(root, policy)
    signature, file_hashes = _build_signature(root, files)
    changed = _changed_files(state.get("last_file_hashes", {}), file_hashes)
    facts = _collect_facts(root)
    return {
        "policy": policy,
        "state": state,
        "files": files,
        "signature": signature,
        "file_hashes": file_hashes,
        "changed_files": changed,
        "facts": facts,
    }


def run_scan(root: str | Path, *, force: bool = False) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    now = _utc_now()
    ctx = _compute_context(canonical_root)
    policy = ctx["policy"]
    state = ctx["state"]
    signature = ctx["signature"]
    changed = ctx["changed_files"]
    docs_exist = _docs_exist(canonical_root)

    if not bool(policy.get("enabled", True)):
        status = "disabled"
    elif _should_skip_interval(policy, state, now, force):
        status = "skipped_interval"
    elif signature == str(state.get("last_signature", "")) and docs_exist and len(changed) < int(policy.get("min_changed_files_to_trigger", 1)):
        status = "no_change"
    else:
        status = "needs_update"

    report = {
        "canonical_root": str(canonical_root.resolve()),
        "created_at": now.isoformat(),
        "status": status,
        "signature_old": str(state.get("last_signature", "")),
        "signature_new": signature,
        "signature_files_count": len(ctx["files"]),
        "changed_files_count": len(changed),
        "changed_files": changed[:100],
        "docs_exist": docs_exist,
        "updated_files": [],
        "gap_count": len(ctx["facts"]["gaps"]),
        "gaps": ctx["facts"]["gaps"],
        "paths": _report_paths(),
        "version": 1,
    }
    _write_report(canonical_root, report)
    return {"report": report, "paths": _report_paths()}


def run_apply(root: str | Path, *, force: bool = False) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    now = _utc_now()
    ctx = _compute_context(canonical_root)
    policy = ctx["policy"]
    state = ctx["state"]
    old_signature = str(state.get("last_signature", ""))
    signature = ctx["signature"]
    changed = ctx["changed_files"]
    docs_exist = _docs_exist(canonical_root)
    min_changed = int(policy.get("min_changed_files_to_trigger", 1))

    if not bool(policy.get("enabled", True)):
        status = "disabled"
        should_update = False
    elif _should_skip_interval(policy, state, now, force):
        status = "skipped_interval"
        should_update = False
    elif not docs_exist:
        status = "updated"
        should_update = True
    elif signature != old_signature and len(changed) >= min_changed:
        status = "updated"
        should_update = True
    elif force:
        status = "updated"
        should_update = True
    else:
        status = "no_change"
        should_update = False

    updated_files: List[str] = []
    if should_update:
        docs = _build_docs(canonical_root, ctx["facts"])
        for rel, content in docs.items():
            if _write_if_changed(canonical_root / rel, content):
                updated_files.append(rel.as_posix())
    # Refresh signature after writes when update occurred.
    if should_update:
        files_after = _collect_signature_files(canonical_root, policy)
        signature_after, hashes_after = _build_signature(canonical_root, files_after)
        signature = signature_after
        ctx["file_hashes"] = hashes_after

    state["last_signature"] = signature
    state["last_run_utc"] = now.isoformat()
    state["last_status"] = status
    state["last_updated_files"] = updated_files
    state["last_gap_count"] = len(ctx["facts"]["gaps"])
    state["last_changed_files"] = changed[:100]
    state["last_file_hashes"] = ctx["file_hashes"]
    _update_state(canonical_root, state)

    report = {
        "canonical_root": str(canonical_root.resolve()),
        "created_at": now.isoformat(),
        "status": status,
        "signature_old": old_signature,
        "signature_new": signature,
        "signature_files_count": len(ctx["files"]),
        "changed_files_count": len(changed),
        "changed_files": changed[:100],
        "docs_exist": _docs_exist(canonical_root),
        "updated_files": updated_files,
        "gap_count": len(ctx["facts"]["gaps"]),
        "gaps": ctx["facts"]["gaps"],
        "paths": _report_paths(),
        "version": 1,
    }
    _write_report(canonical_root, report)
    return {"report": report, "paths": _report_paths()}


def main() -> int:
    parser = argparse.ArgumentParser(description="Maintain PROJECT_BRIEF and REPO_MAP docs")
    parser.add_argument("--root", default=".")
    parser.add_argument("--scan", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if not args.scan and not args.apply:
        parser.error("Use --scan or --apply")

    if args.apply:
        out = run_apply(args.root, force=args.force)
    else:
        out = run_scan(args.root, force=args.force)

    print(json.dumps(out["report"], indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
