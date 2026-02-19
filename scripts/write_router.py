#!/usr/bin/env python3
"""Deterministic write router for ingest sources."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.corpus_triage import run_triage
from scripts.repo_root import get_canonical_root

POLICY_PATH = Path("state/write_router_policy.json")
REPORT_JSON = Path("docs/_inbox/write_router_latest.json")
REPORT_MD = Path("docs/_inbox/write_router_latest.md")
REPORT_LOG = Path("logs/write_router_latest.json")

DEFAULT_POLICY: Dict[str, Any] = {
    "version": 1,
    "categories": [
        "ops_system",
        "brain_knowledge",
        "memory_human",
        "templates",
        "inbox_only",
        "ignore",
    ],
    "thresholds": {
        "max_node_chars": 20_000,
        "max_card_chars": 3_000,
        "max_refs": 40,
        "max_files": 500,
        "max_bytes": 100 * 1024 * 1024,
    },
    "no_overwrite": {"side_by_side_suffix": "__from_{source_id}"},
    "reserved_filename_guardrails": {
        "reserved_filenames": ["AGENTS.md", "AGENTS.override.md", "CLAUDE.md", "CLAUDE.local.md"],
        "allowed_locations": ["AGENTS.md", "AGENTS.override.md", "CLAUDE.md", "CLAUDE.local.md", ".claude/CLAUDE.md", ".claude/rules/**"],
        "force_category_on_detect": "inbox_only",
    },
    "destinations": {
        "ops_system": "brain/domains/openclaw_ops",
        "brain_knowledge": "brain/domains/<domain>",
        "memory_human": "docs/_inbox/memory_inbox.ndjson",
        "templates": "brain/templates",
        "inbox_only": "vault/inbox_raw/_processed",
        "ignore": "vault/inbox_raw/_processed",
    },
    "rules": [
        {
            "id": "ignore_archives",
            "category": "ignore",
            "extensions": [".zip", ".tar", ".gz", ".7z", ".rar"],
        },
        {
            "id": "ops_by_keywords",
            "category": "ops_system",
            "keywords": [
                "openclaw",
                "otto",
                "repo",
                "root",
                "hygiene",
                "quarantine",
                "salvage",
                "autonomy",
                "hook",
                "gates",
                "ledger",
                "ops",
            ],
            "recommended_domains": ["openclaw_ops"],
        },
        {
            "id": "memory_by_human_signals",
            "category": "memory_human",
            "keywords": [
                "mateo",
                "prefer",
                "preference",
                "decision",
                "project",
                "timeline",
                "personal",
                "human",
            ],
            "source_name_contains": ["preferences", "decisions", "timeline", "projects", "personal"],
        },
        {
            "id": "templates_by_prompt_signals",
            "category": "templates",
            "keywords": ["prompt", "template", "playbook", "guide", "protocol", "style"],
            "source_name_contains": ["prompt", "template", "playbook"],
        },
        {
            "id": "inbox_only_large_binary",
            "category": "inbox_only",
            "extensions": [".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx"],
        },
        {
            "id": "default_brain_knowledge",
            "category": "brain_knowledge",
        },
    ],
}

TOKEN_RE = re.compile(r"[a-z0-9_]+")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _save_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _slug(value: str) -> str:
    out: List[str] = []
    prev_sep = False
    for ch in value.lower():
        if ("a" <= ch <= "z") or ("0" <= ch <= "9"):
            out.append(ch)
            prev_sep = False
            continue
        if not prev_sep:
            out.append("_")
            prev_sep = True
    text = "".join(out).strip("_")
    return text or "external_ingest"


def _normalize_policy(policy: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(DEFAULT_POLICY)
    merged.update(policy or {})
    merged["categories"] = list(merged.get("categories", DEFAULT_POLICY["categories"]))
    merged["rules"] = list(merged.get("rules", DEFAULT_POLICY["rules"]))
    merged["thresholds"] = dict(DEFAULT_POLICY["thresholds"]) | dict(merged.get("thresholds", {}))
    merged["no_overwrite"] = dict(DEFAULT_POLICY["no_overwrite"]) | dict(merged.get("no_overwrite", {}))
    merged["destinations"] = dict(DEFAULT_POLICY["destinations"]) | dict(merged.get("destinations", {}))
    merged["reserved_filename_guardrails"] = dict(DEFAULT_POLICY["reserved_filename_guardrails"]) | dict(
        merged.get("reserved_filename_guardrails", {})
    )
    return merged


def load_policy(root: Path, *, create_if_missing: bool = True) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    path = canonical_root / POLICY_PATH
    payload: Dict[str, Any] = {}
    if path.is_file():
        try:
            parsed = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            parsed = {}
        if isinstance(parsed, dict):
            payload = parsed

    policy = _normalize_policy(payload)
    if create_if_missing and not path.is_file():
        _save_json(path, policy)
    return policy


def _source_keywords(source: Dict[str, Any]) -> List[str]:
    raw: List[str] = []
    raw.extend(source.get("keywords", []))
    for token in TOKEN_RE.findall(str(source.get("source_name", "")).lower()):
        raw.append(token)
        raw.extend(part for part in token.split("_") if part)
    raw.extend(TOKEN_RE.findall(str(source.get("recommended_domain", "")).lower()))
    return sorted({token for token in raw if token})


def _memory_record_type(source: Dict[str, Any]) -> str:
    corpus = set(_source_keywords(source))
    if corpus.intersection({"prefer", "preference", "preferences", "gusta", "like"}):
        return "preference"
    if corpus.intersection({"decision", "decisions", "decidir", "decided"}):
        return "decision"
    if corpus.intersection({"project", "projects", "proyecto", "roadmap", "milestone"}):
        return "project"
    if corpus.intersection({"principle", "principles", "rule", "rules"}):
        return "principle"
    if corpus.intersection({"profile", "bio", "persona", "mateo", "about_me"}):
        return "profile_fact"
    return "timeline"


def _source_reserved_files(source: Dict[str, Any], policy: Dict[str, Any]) -> List[str]:
    guardrails = policy.get("reserved_filename_guardrails", {})
    reserved = {str(name).lower() for name in guardrails.get("reserved_filenames", [])}
    found = set()
    for item in source.get("files", []):
        name = Path(str(item.get("rel_path", ""))).name.lower()
        if name in reserved:
            found.add(Path(str(item.get("rel_path", ""))).name)
    return sorted(found)


def _rule_matches(rule: Dict[str, Any], source: Dict[str, Any]) -> bool:
    source_name = str(source.get("source_name", "")).lower()
    recommended_domain = str(source.get("recommended_domain", "")).lower()
    keywords = set(_source_keywords(source))
    extensions = set(str(ext).lower() for ext in source.get("extensions", {}).keys())
    matches: List[bool] = []

    contains = [str(item).lower() for item in rule.get("source_name_contains", [])]
    if contains:
        matches.append(any(token in source_name for token in contains))

    rule_keywords = [str(item).lower() for item in rule.get("keywords", [])]
    if rule_keywords:
        matches.append(any(token in keywords for token in rule_keywords))

    rule_exts = [str(item).lower() for item in rule.get("extensions", [])]
    if rule_exts:
        matches.append(any(ext in extensions for ext in rule_exts))

    rule_domains = [str(item).lower() for item in rule.get("recommended_domains", [])]
    if rule_domains:
        matches.append(recommended_domain in rule_domains)

    if not matches:
        return True
    return any(matches)


def classify_source(source: Dict[str, Any], policy: Dict[str, Any]) -> Dict[str, str]:
    categories = set(policy.get("categories", []))
    for rule in policy.get("rules", []):
        category = str(rule.get("category", "")).strip()
        if category not in categories:
            continue
        if _rule_matches(rule, source):
            return {
                "category": category,
                "rule_id": str(rule.get("id", "unknown")),
            }
    return {"category": "brain_knowledge", "rule_id": "fallback_default"}


def _domain_for(source: Dict[str, Any], category: str) -> str:
    if category == "ops_system":
        return "openclaw_ops"
    if category == "templates":
        return "ingest_patterns"
    if category == "memory_human":
        return "memory_human"
    suggested = str(source.get("recommended_domain", "")).strip()
    return _slug(suggested or "external_ingest")


def build_source_routing_decision(source: Dict[str, Any], policy: Dict[str, Any]) -> Dict[str, Any]:
    reserved_files = _source_reserved_files(source, policy)
    if reserved_files:
        force_category = str(
            policy.get("reserved_filename_guardrails", {}).get("force_category_on_detect", "inbox_only")
        ).strip() or "inbox_only"
        return {
            "source_id": source["source_id"],
            "source_name": source["source_name"],
            "category": force_category,
            "domain": "external_ingest",
            "rule_id": "reserved_filename_guardrail",
            "reason": f"reserved filenames detected: {', '.join(reserved_files)}",
            "reserved_files": reserved_files,
            "destinations": [{"kind": "processed_snapshot", "path": "vault/inbox_raw/_processed"}],
        }

    classification = classify_source(source, policy)
    category = classification["category"]
    domain = _domain_for(source, category)

    destinations: List[Dict[str, str]] = []
    if category in {"ops_system", "brain_knowledge"}:
        destinations.append({"kind": "brain_domain", "path": f"brain/domains/{domain}"})
        destinations.append({"kind": "brain_cards", "path": f"brain/cards/{domain}"})
    elif category == "templates":
        destinations.append({"kind": "brain_template", "path": "brain/templates"})
    elif category == "memory_human":
        destinations.append(
            {
                "kind": "memory_inbox",
                "path": "docs/_inbox/memory_inbox.ndjson",
                "record_type": _memory_record_type(source),
            }
        )

    destinations.append({"kind": "processed_snapshot", "path": "vault/inbox_raw/_processed"})

    return {
        "source_id": source["source_id"],
        "source_name": source["source_name"],
        "category": category,
        "domain": domain,
        "rule_id": classification["rule_id"],
        "reason": f"category={category} via rule={classification['rule_id']}",
        "reserved_files": [],
        "destinations": destinations,
    }


def build_routing_decisions(sources: Sequence[Dict[str, Any]], policy: Dict[str, Any]) -> List[Dict[str, Any]]:
    out = [build_source_routing_decision(source, policy) for source in sources]
    out.sort(key=lambda item: item["source_id"])
    return out


def build_router_report(root: Path, *, triage_report: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    triage = triage_report or run_triage(canonical_root)["report"]
    policy = load_policy(canonical_root, create_if_missing=True)
    decisions = build_routing_decisions(triage.get("sources", []), policy)

    by_category: Dict[str, int] = {}
    for item in decisions:
        category = item["category"]
        by_category[category] = by_category.get(category, 0) + 1

    return {
        "canonical_root": str(canonical_root.resolve()),
        "created_at": _utc_now(),
        "policy_path": POLICY_PATH.as_posix(),
        "routing_decisions": decisions,
        "routing_summary": {
            "source_count": len(decisions),
            "by_category": dict(sorted(by_category.items())),
        },
        "thresholds": policy.get("thresholds", {}),
        "version": 1,
    }


def write_router_reports(root: Path, report: Dict[str, Any]) -> Dict[str, str]:
    canonical_root = get_canonical_root(root)
    _save_json(canonical_root / REPORT_JSON, report)
    _save_json(canonical_root / REPORT_LOG, report)

    lines: List[str] = [
        "# Write Router Report",
        "",
        f"- Canonical root: `{report['canonical_root']}`",
        f"- Policy: `{report['policy_path']}`",
        f"- Source count: {report['routing_summary']['source_count']}",
        f"- Categories: `{json.dumps(report['routing_summary']['by_category'], sort_keys=True)}`",
        f"- JSON report: `{REPORT_JSON.as_posix()}`",
        f"- Log report: `{REPORT_LOG.as_posix()}`",
        "",
        "## Decisions",
        "",
    ]
    if not report["routing_decisions"]:
        lines.append("- No decisions.")
    else:
        for item in report["routing_decisions"]:
            dests = ", ".join(dest["path"] for dest in item["destinations"])
            lines.append(
                f"- `{item['source_name']}` id={item['source_id']} category={item['category']} domain={item['domain']} rule={item['rule_id']} -> {dests}"
            )

    md_path = canonical_root / REPORT_MD
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"json": REPORT_JSON.as_posix(), "markdown": REPORT_MD.as_posix(), "log": REPORT_LOG.as_posix()}


def run_write_router(root: Path, *, triage_report: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    report = build_router_report(root, triage_report=triage_report)
    paths = write_router_reports(root, report)
    return {"report": report, "paths": paths}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run deterministic write router")
    parser.add_argument("--root", default=".")
    parser.add_argument("--triage-json", default="")
    args = parser.parse_args()

    triage_report = None
    if args.triage_json:
        triage_report = json.loads(Path(args.triage_json).read_text(encoding="utf-8"))

    out = run_write_router(Path(args.root), triage_report=triage_report)
    print(
        json.dumps(
            {
                "canonical_root": out["report"]["canonical_root"],
                "routing_summary": out["report"]["routing_summary"],
                "paths": out["paths"],
            },
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
