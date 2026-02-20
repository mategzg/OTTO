#!/usr/bin/env python3
"""Universal ingest router: plan/apply raw corpus assimilation into Brain routes/cards."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.corpus_triage import run_triage
from scripts.repo_root import get_canonical_root, is_pathlike_component
from scripts.write_router import build_routing_decisions, load_policy

PLAN_DIR = Path("state/ingest_plans")
PLAN_JSON = Path("docs/_inbox/corpus_assimilation_plan_latest.json")
PLAN_MD = Path("docs/_inbox/corpus_assimilation_plan_latest.md")
PLAN_LOG = Path("logs/corpus_assimilation_plan_latest.json")
REPORT_JSON = Path("docs/_inbox/corpus_assimilation_report_latest.json")
REPORT_MD = Path("docs/_inbox/corpus_assimilation_report_latest.md")
REPORT_LOG = Path("logs/corpus_assimilation_latest.json")

DEFAULT_MAX_FILES = 500
DEFAULT_MAX_BYTES = 100 * 1024 * 1024
DEFAULT_MAX_NODE_CHARS = 20_000
DEFAULT_MAX_CARD_CHARS = 3_000
DEFAULT_MAX_REFS = 40

MEMORY_INBOX = Path("docs/_inbox/memory_inbox.ndjson")

RESERVED_FILENAMES = {"AGENTS.md", "AGENTS.override.md", "CLAUDE.md", "CLAUDE.local.md"}
ALLOWED_RESERVED_TARGETS = {
    "AGENTS.md",
    "AGENTS.override.md",
    "CLAUDE.md",
    "CLAUDE.local.md",
    ".claude/CLAUDE.md",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _save_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _slug(value: str) -> str:
    out: List[str] = []
    prev_dash = False
    for ch in value.lower():
        ok = ("a" <= ch <= "z") or ("0" <= ch <= "9")
        if ok:
            out.append(ch)
            prev_dash = False
            continue
        if not prev_dash:
            out.append("_")
            prev_dash = True
    text = "".join(out).strip("_")
    return text or "external_ingest"


def _plan_id(sources: Sequence[Dict[str, Any]]) -> str:
    raw = "\n".join(f"{item['source_id']}:{item['source_hash']}" for item in sources)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]
    return f"PLAN-{_stamp()}-{digest}" if raw else f"PLAN-{_stamp()}-empty"


def _is_safe_target_rel(rel_path: str) -> bool:
    parts = Path(rel_path).parts
    if any(is_pathlike_component(part) for part in parts):
        return False
    filename = Path(rel_path).name
    if filename in RESERVED_FILENAMES and rel_path.strip().strip("/") not in ALLOWED_RESERVED_TARGETS:
        return False
    return True


def _render_domain_index(domain: str) -> str:
    return "\n".join(
        [
            f"# Domain: {domain}",
            "",
            "## Purpose",
            "",
            f"Hub ruteable para conocimiento asimilado del dominio `{domain}`.",
            "",
            "## Use when",
            "",
            "- Existe un source pendiente recomendado para este dominio.",
            "- Necesitas navegar cards y nodos derivados sin leer el crudo.",
            "",
            "## Avoid when",
            "",
            "- No hay fuentes asimiladas para este dominio.",
            "- Necesitas acceso literal al crudo (usar vault/inbox_raw/_processed).",
            "",
            "## Routing",
            "",
            "- Entrar por este hub, luego abrir `sources/*_index.md` y cards asociadas.",
            "- Para operacion general OpenClaw: `brain/domains/openclaw_ops/00_INDEX.md`.",
            "",
            "## Maintenance",
            "",
            "- Actualizar por plan/apply del ingest router.",
            "",
            "## Links",
            "",
            "- `brain/domains/ingest/00_INDEX.md`",
            "- `brain/cards/`",
        ]
    ) + "\n"


def _render_domain_router(domain: str) -> str:
    return "\n".join(
        [
            f"# Router: {domain}",
            "",
            "## Purpose",
            "",
            "Ruta de bajo costo para consultas del dominio asimilado.",
            "",
            "## Use when",
            "",
            "- Preguntas por contenido incorporado desde `vault/inbox_raw`.",
            "",
            "## Avoid when",
            "",
            "- Preguntas de operacion repo/hygiene (usar openclaw_ops).",
            "",
            "## Routing",
            "",
            "- Buscar primero en `sources/*_index.md`.",
            "- Resolver detalle en cards con `source_ref`.",
            "- Solo si falta detalle, abrir snapshot en `_processed`.",
            "",
            "## Maintenance",
            "",
            "- Mantener rutas compatibles con plan/apply actuales.",
            "",
            "## Links",
            "",
            "- `brain/domains/openclaw_ops/01_ROUTER.md`",
            "- `vault/inbox_raw/_processed/`",
        ]
    ) + "\n"


def _split_batches(files: Sequence[Dict[str, Any]], *, max_refs: int, max_card_chars: int) -> List[List[Dict[str, Any]]]:
    batches: List[List[Dict[str, Any]]] = []
    current: List[Dict[str, Any]] = []
    current_size = 0
    for item in files:
        line = f"- `{item['root_rel_path']}` sha={item['sha256'][:12]} size={item['size']}\n"
        line_size = len(line)
        if current and (len(current) >= max_refs or current_size + line_size > max_card_chars):
            batches.append(current)
            current = []
            current_size = 0
        current.append(item)
        current_size += line_size
    if current:
        batches.append(current)
    return batches


def _render_source_node(source: Dict[str, Any], domain: str, card_paths: Sequence[str], processed_hint: str, category: str) -> str:
    lines: List[str] = [
        f"# Source Router: {source['source_name']}",
        "",
        "## Purpose",
        "",
        "Nodo router para navegar cards derivadas de un source pending sin leer el corpus completo.",
        "",
        "## Use when",
        "",
        "- Necesitas respuesta basada en esta fuente concreta.",
        "- Necesitas ubicar rapidamente cards y source refs.",
        "",
        "## Avoid when",
        "",
        "- Necesitas operacion general de repo (usar openclaw_ops).",
        "",
        "## Routing",
        "",
        f"- Source id: `{source['source_id']}`",
        f"- Domain target: `{domain}`",
        f"- Category: `{category}`",
        f"- Processed hint: `{processed_hint}`",
        "- Cards derivadas:",
    ]
    for card in card_paths:
        lines.append(f"  - `{card}`")
    lines.extend(
        [
            "",
            "## Maintenance",
            "",
            "- Regenerar con nuevo plan si cambia el source hash.",
            "",
            "## Links",
            "",
            f"- `{source['source_path']}`",
        ]
    )
    return "\n".join(lines) + "\n"


def _render_card(source: Dict[str, Any], domain: str, batch: Sequence[Dict[str, Any]], *, card_index: int, total_cards: int, category: str) -> str:
    card_id = f"card-{domain}-{source['source_id']}-{card_index:02d}"
    source_refs = "; ".join(item["root_rel_path"] for item in batch)
    lines: List[str] = [
        f"# Card: {source['source_name']} [{card_index}/{total_cards}]",
        "",
        f"id: {card_id}",
        "type: concept",
        f"tags: ingest,{domain},{source['source_id']}",
        f"source_ref: {source_refs}",
        "status: active",
        "confidence: 0.8",
        f"last_confirmed_at: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
        "",
        "## Summary",
        "",
        f"Segmento {card_index}/{total_cards} del source `{source['source_name']}` asimilado en `{domain}`.",
        f"Categoria de escritura: `{category}`.",
        "",
        "## How to apply",
        "",
        "- Responder desde esta card primero.",
        "- Escalar a snapshot `_processed` solo si el detalle no alcanza.",
        "",
        "## References",
        "",
    ]
    for item in batch:
        lines.append(f"- `{item['root_rel_path']}` sha={item['sha256'][:12]} size={item['size']}")
    return "\n".join(lines) + "\n"


def _render_template_digest(source: Dict[str, Any], *, source_id: str) -> str:
    top_refs = sorted(source.get("files", []), key=lambda item: item["root_rel_path"])[:40]
    lines = [
        f"# Template Digest: {source['source_name']}",
        "",
        "## Purpose",
        "",
        "Derivado corto de plantilla/prompt sin copiar dump crudo.",
        "",
        "## Use when",
        "",
        "- Necesitas patrones de redaccion/protocolo reutilizables.",
        "",
        "## Avoid when",
        "",
        "- Necesitas contenido literal completo del source.",
        "",
        "## Routing",
        "",
        f"- Source id: `{source_id}`",
        "- Expandir manualmente en nodos/card solo cuando haga falta.",
        "",
        "## Extracted Patterns",
        "",
    ]
    for keyword in source.get("keywords", [])[:20]:
        lines.append(f"- `{keyword}`")
    lines.extend(["", "## Source Refs", ""])
    for item in top_refs:
        lines.append(f"- `{item['root_rel_path']}` sha={item['sha256'][:12]}")
    return "\n".join(lines) + "\n"


def _reserved_suffix(filename: str) -> str:
    upper = filename.upper()
    if upper.startswith("AGENTS"):
        return "agents_example"
    if upper.startswith("CLAUDE"):
        return "claude_example"
    return "reserved_example"


def _render_reserved_guardrail_card(source: Dict[str, Any], reserved_filename: str) -> str:
    refs = [item["root_rel_path"] for item in sorted(source.get("files", []), key=lambda x: x["root_rel_path"])]
    lines: List[str] = [
        f"# Card: Reserved Filename Guardrail ({reserved_filename})",
        "",
        f"id: card-guardrail-{source['source_id']}-{_reserved_suffix(reserved_filename)}",
        "type: principle",
        "tags: ingest,guardrail,reserved_filename",
        "status: active",
        "confidence: 1.0",
        f"source_ref: {source['source_path']}",
        "",
        "## Summary",
        "",
        f"Se detecto `{reserved_filename}` dentro de un corpus. El router forzo categoria `inbox_only`.",
        "",
        "## How to apply",
        "",
        "- No promover AGENTS*/CLAUDE* fuera de allowlist.",
        "- Mantener el crudo en `_processed` como fuente auditada.",
        "",
        "## References",
        "",
    ]
    for ref in refs[:40]:
        lines.append(f"- `{ref}`")
    return "\n".join(lines) + "\n"


def _existing(path: Path) -> bool:
    try:
        return path.is_file()
    except OSError:
        return False


def _memory_inbox_entry(source: Dict[str, Any], record_type: str) -> Dict[str, Any]:
    tags = [
        "ingest",
        "memory_human",
        _slug(source.get("recommended_domain", "external_ingest")),
    ]

    return {
        "id": f"memin-{source['source_id']}",
        "type": record_type,
        "key": f"{record_type}:{_slug(source['source_name'])}",
        "captured_at": _utc_now(),
        "tags": tags,
        "notes": f"Assimilated source `{source['source_name']}` into MemoryOS inbox.",
        "source_ref": source["source_path"],
        "status": "pending",
        "confidence": "medium",
        "best_known": False,
        "supersedes": [],
    }


def build_assimilation_plan(
    root: Path,
    *,
    inbox_rel: str = "vault/inbox_raw",
    max_files: int = DEFAULT_MAX_FILES,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_node_chars: int = DEFAULT_MAX_NODE_CHARS,
    max_card_chars: int = DEFAULT_MAX_CARD_CHARS,
    max_refs: int = DEFAULT_MAX_REFS,
    include_source_ids: Optional[Sequence[str]] = None,
    max_sources: int = 0,
) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    triage = run_triage(canonical_root, inbox_rel=inbox_rel)["report"]

    sources_all = sorted(triage["sources"], key=lambda item: item["inbox_rel_path"])
    source_filter = {item for item in (include_source_ids or []) if item}
    sources = [item for item in sources_all if not source_filter or item["source_id"] in source_filter]
    if max_sources > 0:
        sources = sources[: max(1, max_sources)]

    pending_files = sum(item["file_count"] for item in sources)
    pending_bytes = sum(item["total_bytes"] for item in sources)
    pending_sources = len(sources)

    stop_reasons: List[str] = []
    if triage["suspicious_entries"]:
        stop_reasons.append("suspicious_entries_in_inbox")
    if pending_files > max_files:
        stop_reasons.append(f"pending_files_exceeds_limit:{pending_files}>{max_files}")
    if pending_bytes > max_bytes:
        stop_reasons.append(f"pending_bytes_exceeds_limit:{pending_bytes}>{max_bytes}")

    policy = load_policy(canonical_root, create_if_missing=True)
    routing_decisions = build_routing_decisions(sources, policy)
    routing_map = {item["source_id"]: item for item in routing_decisions}

    plan_id = _plan_id(sources)
    operations: List[Dict[str, Any]] = []
    source_plans: List[Dict[str, Any]] = []

    for source in sources:
        decision = routing_map[source["source_id"]]
        category = decision["category"]
        domain = decision["domain"]

        if category in {"ops_system", "brain_knowledge"}:
            domain_root = Path("brain") / "domains" / domain
            cards_root = Path("brain") / "cards" / domain

            domain_index_rel = (domain_root / "00_INDEX.md").as_posix()
            domain_router_rel = (domain_root / "01_ROUTER.md").as_posix()

            if domain != "openclaw_ops" and not _existing(canonical_root / domain_index_rel):
                operations.append(
                    {
                        "op_type": "write",
                        "op_category": category,
                        "source_id": source["source_id"],
                        "target_rel": domain_index_rel,
                        "content": _render_domain_index(domain),
                    }
                )
            if domain != "openclaw_ops" and not _existing(canonical_root / domain_router_rel):
                operations.append(
                    {
                        "op_type": "write",
                        "op_category": category,
                        "source_id": source["source_id"],
                        "target_rel": domain_router_rel,
                        "content": _render_domain_router(domain),
                    }
                )

            files = sorted(source["files"], key=lambda item: item["root_rel_path"])
            batches = _split_batches(files, max_refs=max_refs, max_card_chars=max_card_chars)
            card_paths: List[str] = []

            for idx, batch in enumerate(batches, start=1):
                card_rel = (cards_root / f"card_{source['source_id']}_{idx:02d}.md").as_posix()
                card_paths.append(card_rel)
                operations.append(
                    {
                        "op_type": "write",
                        "op_category": category,
                        "source_id": source["source_id"],
                        "target_rel": card_rel,
                        "content": _render_card(source, domain, batch, card_index=idx, total_cards=len(batches), category=category),
                    }
                )

            source_node_rel = (domain_root / "sources" / f"{source['source_id']}_index.md").as_posix()
            processed_hint = f"vault/inbox_raw/_processed/*_{source['source_id']}/source/"
            node_content = _render_source_node(source, domain, card_paths, processed_hint, category)
            if len(node_content) > max_node_chars:
                stop_reasons.append(f"node_size_exceeds_limit:{source['source_id']}")

            operations.append(
                {
                    "op_type": "write",
                    "op_category": category,
                    "source_id": source["source_id"],
                    "target_rel": source_node_rel,
                    "content": node_content,
                }
            )

            source_plans.append(
                {
                    "source_id": source["source_id"],
                    "source_name": source["source_name"],
                    "source_hash": source["source_hash"],
                    "domain": domain,
                    "category": category,
                    "inbox_rel_path": source["inbox_rel_path"],
                    "card_count": len(card_paths),
                    "node_rel_path": source_node_rel,
                }
            )

        elif category == "templates":
            target_rel = (Path("brain") / "templates" / f"template_{source['source_id']}.md").as_posix()
            operations.append(
                {
                    "op_type": "write",
                    "op_category": category,
                    "source_id": source["source_id"],
                    "target_rel": target_rel,
                    "content": _render_template_digest(source, source_id=source["source_id"]),
                }
            )
            source_plans.append(
                {
                    "source_id": source["source_id"],
                    "source_name": source["source_name"],
                    "source_hash": source["source_hash"],
                    "domain": domain,
                    "category": category,
                    "inbox_rel_path": source["inbox_rel_path"],
                    "card_count": 0,
                    "node_rel_path": target_rel,
                }
            )

        elif category == "memory_human":
            memory_record_type = "timeline"
            for dest in decision["destinations"]:
                if dest.get("kind") == "memory_inbox":
                    memory_record_type = str(dest.get("record_type", "timeline"))
                    break

            operations.append(
                {
                    "op_type": "memory_inbox_append",
                    "op_category": category,
                    "source_id": source["source_id"],
                    "target_rel": MEMORY_INBOX.as_posix(),
                    "entry": _memory_inbox_entry(source, memory_record_type),
                }
            )

            source_plans.append(
                {
                    "source_id": source["source_id"],
                    "source_name": source["source_name"],
                    "source_hash": source["source_hash"],
                    "domain": domain,
                    "category": category,
                    "inbox_rel_path": source["inbox_rel_path"],
                    "card_count": 0,
                    "node_rel_path": MEMORY_INBOX.as_posix(),
                }
            )

        elif category == "inbox_only":
            reserved_files = list(decision.get("reserved_files", []))
            safe_cards: List[str] = []
            for reserved_name in reserved_files:
                card_rel = (
                    Path("brain")
                    / "cards"
                    / "external_ingest"
                    / f"card_{source['source_id']}_{_reserved_suffix(reserved_name)}.md"
                ).as_posix()
                safe_cards.append(card_rel)
                operations.append(
                    {
                        "op_type": "write",
                        "op_category": category,
                        "source_id": source["source_id"],
                        "target_rel": card_rel,
                        "content": _render_reserved_guardrail_card(source, reserved_name),
                    }
                )

            source_plans.append(
                {
                    "source_id": source["source_id"],
                    "source_name": source["source_name"],
                    "source_hash": source["source_hash"],
                    "domain": domain,
                    "category": category,
                    "inbox_rel_path": source["inbox_rel_path"],
                    "card_count": len(safe_cards),
                    "node_rel_path": safe_cards[0] if safe_cards else "",
                }
            )

        else:
            source_plans.append(
                {
                    "source_id": source["source_id"],
                    "source_name": source["source_name"],
                    "source_hash": source["source_hash"],
                    "domain": domain,
                    "category": category,
                    "inbox_rel_path": source["inbox_rel_path"],
                    "card_count": 0,
                    "node_rel_path": "",
                }
            )

    op_priority = {"write": 0, "memory_inbox_append": 1}
    operations.sort(
        key=lambda item: (
            item.get("target_rel", ""),
            op_priority.get(item.get("op_type", ""), 9),
            item["source_id"],
        )
    )
    for op in operations:
        basis = f"{op['op_type']}|{op.get('target_rel','')}|{op['source_id']}"
        op["op_id"] = hashlib.sha1(basis.encode("utf-8")).hexdigest()[:12]
        if op["op_type"] == "write":
            op["content_sha256"] = hashlib.sha256(op["content"].encode("utf-8")).hexdigest()
        elif op["op_type"] == "memory_inbox_append":
            op["entry_sha256"] = hashlib.sha256(
                json.dumps(op["entry"], sort_keys=True, ensure_ascii=False).encode("utf-8")
            ).hexdigest()

    blocked = bool(stop_reasons)
    status = "blocked" if blocked else "ok"

    routing_summary: Dict[str, int] = {}
    for item in routing_decisions:
        cat = item["category"]
        routing_summary[cat] = routing_summary.get(cat, 0) + 1

    triage_summary_selected = {
        "pending_sources": pending_sources,
        "pending_files": pending_files,
        "pending_total_bytes": pending_bytes,
        "high_signal_sources": sum(1 for item in sources if item.get("high_signal")),
        "suspicious_entries": len(triage.get("suspicious_entries", [])),
    }

    plan = {
        "canonical_root": str(canonical_root.resolve()),
        "created_at": _utc_now(),
        "plan_id": plan_id,
        "status": status,
        "stop_reasons": sorted(set(stop_reasons)),
        "thresholds": {
            "max_bytes": max_bytes,
            "max_card_chars": max_card_chars,
            "max_files": max_files,
            "max_node_chars": max_node_chars,
            "max_refs": max_refs,
        },
        "triage_summary": triage_summary_selected,
        "triage_summary_total": triage["summary"],
        "routing_decisions": routing_decisions,
        "routing_summary": dict(sorted(routing_summary.items())),
        "sources": source_plans,
        "operations": operations,
        "version": 2,
    }
    return plan


def _write_plan_reports(root: Path, plan: Dict[str, Any]) -> Dict[str, str]:
    canonical_root = get_canonical_root(root)
    plan_path = canonical_root / PLAN_DIR / f"{plan['plan_id']}.json"
    _save_json(plan_path, plan)
    _save_json(canonical_root / PLAN_JSON, plan)
    _save_json(canonical_root / PLAN_LOG, plan)

    lines: List[str] = [
        "# Corpus Assimilation Plan",
        "",
        f"- Plan ID: `{plan['plan_id']}`",
        f"- Status: `{plan['status']}`",
        f"- Stop reasons: `{', '.join(plan['stop_reasons'])}`",
        f"- Pending sources(selected): {plan['triage_summary']['pending_sources']}",
        f"- Pending sources(total): {plan['triage_summary_total']['pending_sources']}",
        f"- Operations: {len(plan['operations'])}",
        f"- Routing summary: `{json.dumps(plan['routing_summary'], sort_keys=True)}`",
        f"- Plan path: `{(PLAN_DIR / (plan['plan_id'] + '.json')).as_posix()}`",
        f"- JSON report: `{PLAN_JSON.as_posix()}`",
        f"- Log report: `{PLAN_LOG.as_posix()}`",
        "",
        "## Sources",
        "",
    ]
    if not plan["sources"]:
        lines.append("- No sources pending.")
    else:
        for source in plan["sources"]:
            lines.append(
                f"- `{source['source_name']}` id={source['source_id']} category={source['category']} domain={source['domain']} cards={source['card_count']}"
            )

    lines.extend(["", "## Routing Decisions", ""])
    for decision in plan.get("routing_decisions", []):
        lines.append(
            f"- id={decision['source_id']} category={decision['category']} domain={decision['domain']} rule={decision['rule_id']}"
        )

    lines.extend(["", "## Operations", ""])
    for op in plan["operations"]:
        lines.append(
            f"- `{op.get('target_rel','')}` | op_id={op['op_id']} | source={op['source_id']} | type={op['op_type']} | category={op['op_category']}"
        )

    md_path = canonical_root / PLAN_MD
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "plan_file": (PLAN_DIR / f"{plan['plan_id']}.json").as_posix(),
        "json": PLAN_JSON.as_posix(),
        "log": PLAN_LOG.as_posix(),
        "markdown": PLAN_MD.as_posix(),
    }


def run_plan(
    root: Path,
    *,
    inbox_rel: str = "vault/inbox_raw",
    max_files: int = DEFAULT_MAX_FILES,
    max_bytes: int = DEFAULT_MAX_BYTES,
    include_source_ids: Optional[Sequence[str]] = None,
    max_sources: int = 0,
) -> Dict[str, Any]:
    plan = build_assimilation_plan(
        root,
        inbox_rel=inbox_rel,
        max_files=max_files,
        max_bytes=max_bytes,
        include_source_ids=include_source_ids,
        max_sources=max_sources,
    )
    paths = _write_plan_reports(root, plan)
    return {"plan": plan, "paths": paths}


def _conflict_target(path: Path, source_id: str) -> Path:
    suffix = f"__from_{source_id}"
    if path.suffix:
        candidate = Path(f"{path.with_suffix('')}{suffix}{path.suffix}")
    else:
        candidate = Path(f"{path}{suffix}")

    idx = 1
    final = candidate
    while final.exists():
        if path.suffix:
            final = Path(f"{path.with_suffix('')}{suffix}_{idx}{path.suffix}")
        else:
            final = Path(f"{path}{suffix}_{idx}")
        idx += 1
    return final


def _write_operation(root: Path, op: Dict[str, Any]) -> Dict[str, Any]:
    target_rel = op["target_rel"]
    if not _is_safe_target_rel(target_rel):
        raise RuntimeError(f"Blocked unsafe target path: {target_rel}")

    dst = root / target_rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    content = op["content"]
    source_id = op["source_id"]

    if dst.exists():
        if dst.is_file() and dst.read_text(encoding="utf-8") == content:
            return {"status": "unchanged", "path": target_rel, "category": op["op_category"]}
        conflict = _conflict_target(dst, source_id)
        conflict.write_text(content, encoding="utf-8")
        return {
            "status": "conflict_side_by_side",
            "path": conflict.resolve().relative_to(root.resolve()).as_posix(),
            "original": target_rel,
            "category": op["op_category"],
        }

    dst.write_text(content, encoding="utf-8")
    return {"status": "created", "path": target_rel, "category": op["op_category"]}


def _append_memory_inbox_operation(root: Path, op: Dict[str, Any]) -> Dict[str, Any]:
    target_rel = op["target_rel"]
    if not _is_safe_target_rel(target_rel):
        raise RuntimeError(f"Blocked unsafe target path: {target_rel}")

    dst = root / target_rel
    dst.parent.mkdir(parents=True, exist_ok=True)

    entry = dict(op["entry"])
    source_id = op["source_id"]

    desired_id = str(entry.get("id", "")).strip() or f"mem-{source_id}"
    entry["id"] = desired_id

    status = "created"

    with dst.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True, ensure_ascii=False) + "\n")

    return {"status": status, "path": target_rel, "category": op["op_category"]}


def _iter_files(path: Path) -> Iterable[Path]:
    if path.is_file():
        yield path
        return
    for dirpath, _dirnames, filenames in os.walk(path, topdown=True, followlinks=False):
        current = Path(dirpath)
        for filename in sorted(filenames):
            fp = current / filename
            if fp.is_symlink():
                continue
            yield fp


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_processed_manifest(canonical_root: Path, *, target_root: Path, source_path: Path, plan_id: str) -> Dict[str, str]:
    entries: List[Dict[str, Any]] = []
    payload = target_root / "source"
    for fp in sorted(_iter_files(payload), key=lambda p: p.as_posix()):
        rel = fp.resolve().relative_to(payload.resolve()).as_posix()
        try:
            stat = fp.stat()
            digest = _sha256_file(fp)
        except FileNotFoundError:
            # Concurrent or transient disappearance should not fail the whole apply run.
            continue
        entries.append(
            {
                "mtime": stat.st_mtime,
                "origin_path": str(source_path.resolve()),
                "rel_path": rel,
                "sha256": digest,
                "size": stat.st_size,
            }
        )

    manifest = {
        "created_at": _utc_now(),
        "entry_count": len(entries),
        "entries": entries,
        "origin_path": str(source_path.resolve()),
        "plan_id": plan_id,
        "target_path": str(target_root.resolve()),
        "version": 1,
    }
    manifest_path = target_root / "MANIFEST.json"
    _save_json(manifest_path, manifest)

    readme = target_root / "README.md"
    readme.write_text(
        "\n".join(
            [
                "# Processed Source Snapshot",
                "",
                f"- Origin path: `{source_path.resolve()}`",
                f"- Plan ID: `{plan_id}`",
                f"- Target path: `{target_root.resolve()}`",
                "- Reason: source moved from pending inbox to processed snapshot after successful apply.",
                "- Re-derive: rerun `scripts/brain_ingest_router.py --plan` then `--apply <plan_id>`.",
                "- Manifest: `MANIFEST.json`.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "manifest": manifest_path.resolve().relative_to(canonical_root.resolve()).as_posix(),
        "readme": readme.resolve().relative_to(canonical_root.resolve()).as_posix(),
    }


def _move_sources_to_processed(canonical_root: Path, plan: Dict[str, Any], *, inbox_rel: str) -> List[Dict[str, Any]]:
    moved: List[Dict[str, Any]] = []
    inbox_root = canonical_root / inbox_rel
    stamp = _stamp()

    # Plan sources can be fine-grained files (e.g., normalized/slices/*.ndjson).
    # Collapse to top-level source roots so processed move happens once per source package.
    move_roots: Dict[str, str] = {}
    for source in plan["sources"]:
        src_rel = str(source.get("inbox_rel_path", "")).strip()
        if not src_rel:
            continue
        parts = Path(src_rel).parts
        if len(parts) >= 2 and parts[0] == "sources":
            root_rel = f"sources/{parts[1]}"
        else:
            root_rel = src_rel
        move_roots.setdefault(root_rel, str(source.get("source_id", "unknown")))

    for src_rel, source_id in sorted(move_roots.items()):
        src = inbox_root / src_rel
        if not src.exists():
            # Idempotency guard: if another run moved it already, skip instead of failing whole batch.
            continue

        target_root = inbox_root / "_processed" / f"{stamp}_{source_id}"
        suffix = 1
        while target_root.exists():
            target_root = inbox_root / "_processed" / f"{stamp}_{source_id}_{suffix}"
            suffix += 1
        payload_root = target_root / "source"
        payload_root.parent.mkdir(parents=True, exist_ok=True)

        source_name = Path(src_rel).name
        shutil.move(str(src), str(payload_root / source_name))
        docs = _write_processed_manifest(canonical_root, target_root=target_root, source_path=src, plan_id=plan["plan_id"])
        moved.append(
            {
                "source_id": source_id,
                "source_rel": src_rel,
                "processed_root": target_root.resolve().relative_to(canonical_root.resolve()).as_posix(),
                "manifest": docs["manifest"],
                "readme": docs["readme"],
            }
        )

    return sorted(moved, key=lambda item: item["source_id"])


def _write_apply_reports(root: Path, report: Dict[str, Any]) -> Dict[str, str]:
    canonical_root = get_canonical_root(root)
    _save_json(canonical_root / REPORT_JSON, report)
    _save_json(canonical_root / REPORT_LOG, report)

    lines: List[str] = [
        "# Corpus Assimilation Apply Report",
        "",
        f"- Plan ID: `{report['plan_id']}`",
        f"- Status: `{report['status']}`",
        f"- Created files: {report['summary']['created']}",
        f"- Unchanged files: {report['summary']['unchanged']}",
        f"- Conflict side-by-side files: {report['summary']['conflict_side_by_side']}",
        f"- Processed moves: {report['summary']['processed_moves']}",
        f"- Category writes: `{json.dumps(report['summary']['by_category'], sort_keys=True)}`",
        f"- Needs review: {report.get('needs_review', False)}",
        f"- JSON report: `{REPORT_JSON.as_posix()}`",
        f"- Log report: `{REPORT_LOG.as_posix()}`",
        "",
        "## Writes",
        "",
    ]
    if not report["writes"]:
        lines.append("- None.")
    else:
        for item in report["writes"]:
            lines.append(f"- `{item['path']}` | status={item['status']} | category={item['category']}")

    lines.extend(["", "## Processed Moves", ""])
    if not report["processed_moves"]:
        lines.append("- None.")
    else:
        for item in report["processed_moves"]:
            lines.append(f"- `{item['source_rel']}` -> `{item['processed_root']}` | manifest=`{item['manifest']}`")

    if report.get("errors"):
        lines.extend(["", "## Errors", ""])
        for err in report["errors"]:
            lines.append(f"- {err}")

    md_path = canonical_root / REPORT_MD
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"json": REPORT_JSON.as_posix(), "log": REPORT_LOG.as_posix(), "markdown": REPORT_MD.as_posix()}


def run_apply(root: Path, *, plan_id: str, inbox_rel: str = "vault/inbox_raw") -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    plan_path = canonical_root / PLAN_DIR / f"{plan_id}.json"
    if not plan_path.is_file():
        raise RuntimeError(f"Plan not found: {plan_path}")

    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if plan.get("status") == "blocked":
        report = {
            "canonical_root": str(canonical_root.resolve()),
            "created_at": _utc_now(),
            "errors": [f"Plan is blocked: {', '.join(plan.get('stop_reasons', []))}"],
            "needs_review": False,
            "plan_id": plan_id,
            "processed_moves": [],
            "status": "blocked",
            "summary": {
                "by_category": {},
                "conflict_side_by_side": 0,
                "created": 0,
                "processed_moves": 0,
                "unchanged": 0,
            },
            "writes": [],
            "version": 2,
        }
        paths = _write_apply_reports(canonical_root, report)
        return {"report": report, "paths": paths}

    writes: List[Dict[str, Any]] = []
    errors: List[str] = []

    for op in plan.get("operations", []):
        try:
            if op["op_type"] == "write":
                writes.append(_write_operation(canonical_root, op))
            elif op["op_type"] == "memory_inbox_append":
                writes.append(_append_memory_inbox_operation(canonical_root, op))
            else:
                raise RuntimeError(f"Unsupported op_type: {op['op_type']}")
        except Exception as exc:  # pragma: no cover
            errors.append(str(exc))
            break

    conflict_count = sum(1 for item in writes if item["status"] == "conflict_side_by_side")
    needs_review = conflict_count > 50

    status = "partial" if errors or needs_review else "success"
    processed_moves: List[Dict[str, Any]] = []
    if status == "success":
        try:
            processed_moves = _move_sources_to_processed(canonical_root, plan, inbox_rel=inbox_rel)
        except Exception as exc:  # pragma: no cover
            errors.append(str(exc))
            status = "partial"

    by_category: Dict[str, int] = {}
    for item in writes:
        category = item.get("category", "unknown")
        by_category[category] = by_category.get(category, 0) + 1

    summary = {
        "created": sum(1 for item in writes if item["status"] == "created"),
        "unchanged": sum(1 for item in writes if item["status"] == "unchanged"),
        "conflict_side_by_side": conflict_count,
        "processed_moves": len(processed_moves),
        "by_category": dict(sorted(by_category.items())),
    }

    if needs_review and not errors:
        errors.append("needs_review: conflict_side_by_side exceeded 50 in one apply run")

    report = {
        "canonical_root": str(canonical_root.resolve()),
        "created_at": _utc_now(),
        "errors": errors,
        "needs_review": needs_review,
        "plan_id": plan_id,
        "processed_moves": processed_moves,
        "status": status,
        "summary": summary,
        "writes": writes,
        "version": 2,
    }
    paths = _write_apply_reports(canonical_root, report)
    return {"report": report, "paths": paths}


def brain_status(root: Path, *, inbox_rel: str = "vault/inbox_raw") -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    triage = run_triage(canonical_root, inbox_rel=inbox_rel)["report"]
    plans_dir = canonical_root / PLAN_DIR
    latest_plan = ""
    if plans_dir.is_dir():
        plans = sorted((p.name for p in plans_dir.glob("*.json")), reverse=True)
        if plans:
            latest_plan = f"{PLAN_DIR.as_posix()}/{plans[0]}"
    return {
        "canonical_root": str(canonical_root.resolve()),
        "pending_sources": triage["summary"]["pending_sources"],
        "pending_files": triage["summary"]["pending_files"],
        "latest_plan": latest_plan,
        "latest_plan_report": PLAN_JSON.as_posix() if (canonical_root / PLAN_JSON).is_file() else "",
        "latest_apply_report": REPORT_JSON.as_posix() if (canonical_root / REPORT_JSON).is_file() else "",
        "latest_triage_report": "docs/_inbox/corpus_triage_latest.json" if (canonical_root / "docs/_inbox/corpus_triage_latest.json").is_file() else "",
        "latest_write_router_report": "docs/_inbox/write_router_latest.json" if (canonical_root / "docs/_inbox/write_router_latest.json").is_file() else "",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Universal ingest router plan/apply")
    parser.add_argument("--root", default=".")
    parser.add_argument("--inbox", default="vault/inbox_raw")
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--apply", default="")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--max-files", type=int, default=DEFAULT_MAX_FILES)
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    parser.add_argument("--max-sources", type=int, default=0)
    parser.add_argument("--source-id", action="append", default=[])
    args = parser.parse_args()

    if args.status:
        out = brain_status(Path(args.root), inbox_rel=args.inbox)
        print(json.dumps(out, indent=2, sort_keys=True, ensure_ascii=False))
        return 0

    if args.plan and args.apply:
        parser.error("Use either --plan or --apply <plan_id>.")
    if not args.plan and not args.apply:
        parser.error("Use --plan or --apply <plan_id>.")

    if args.plan:
        out = run_plan(
            Path(args.root),
            inbox_rel=args.inbox,
            max_files=max(1, args.max_files),
            max_bytes=max(1, args.max_bytes),
            include_source_ids=args.source_id,
            max_sources=max(0, args.max_sources),
        )
        print(
            json.dumps(
                {
                    "canonical_root": out["plan"]["canonical_root"],
                    "paths": out["paths"],
                    "plan_id": out["plan"]["plan_id"],
                    "status": out["plan"]["status"],
                    "stop_reasons": out["plan"]["stop_reasons"],
                    "summary": out["plan"]["triage_summary"],
                    "routing_summary": out["plan"].get("routing_summary", {}),
                },
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
            )
        )
        return 0 if out["plan"]["status"] != "blocked" else 3

    out = run_apply(Path(args.root), plan_id=args.apply, inbox_rel=args.inbox)
    print(
        json.dumps(
            {
                "canonical_root": out["report"]["canonical_root"],
                "paths": out["paths"],
                "plan_id": out["report"]["plan_id"],
                "status": out["report"]["status"],
                "summary": out["report"]["summary"],
                "errors": out["report"]["errors"],
            },
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
    )
    return 0 if out["report"]["status"] == "success" else 3


if __name__ == "__main__":
    raise SystemExit(main())
