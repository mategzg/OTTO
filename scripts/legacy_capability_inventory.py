#!/usr/bin/env python3
"""Build a typed legacy capability inventory from coldstore with current-vs-legacy comparison."""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.repo_root import get_canonical_root

COLDSTORE_INDEX_PATH = Path("state/legacy_coldstore_index.json")
CURRENT_INVENTORY_PATH = Path("state/capability_inventory.json")

STATE_PATH = Path("state/legacy_capability_inventory.json")
REPORT_JSON = Path("docs/_inbox/legacy_capability_inventory_latest.json")
REPORT_MD = Path("docs/_inbox/legacy_capability_inventory_latest.md")
REPORT_LOG = Path("logs/legacy_capability_inventory_latest.json")

ARTIFACT_GLOBS = (
    "*/docs/_inbox/**",
    "*/logs/**",
    "*/ops/**",
    "*/copilots/**",
    "*/state/**",
)
ARTIFACT_HINTS = ("report", "latest", "ledger", "_inbox", "manifest", "conflicts")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def _normalize_path(path: str) -> str:
    text = path.strip().replace("\\", "/")
    text = re.sub(r"/+", "/", text)
    return text.strip("/")


def _is_artifact(path: str) -> bool:
    normalized = _normalize_path(path).lower()
    padded = f"/{normalized}"
    for pattern in ARTIFACT_GLOBS:
        glob = pattern.lower().replace("**", "*")
        if fnmatch.fnmatch(padded, glob) or fnmatch.fnmatch(normalized, glob):
            return True
    basename = Path(normalized).name
    return any(hint in basename for hint in ARTIFACT_HINTS)


def _canonical_key(path: str, sha256: str, size: int) -> str:
    normalized = _normalize_path(path)
    basename = Path(normalized).name.lower()
    seed = f"{sha256}|{basename}|{int(size)}" if sha256 else f"{normalized}|{basename}|{int(size)}"
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:18]


def _legacy_type(item: Dict[str, Any]) -> str:
    path = _normalize_path(str(item.get("path", ""))).lower()
    kind = str(item.get("kind_heuristic", "")).lower()
    if "/skills/" in path:
        return "skill"
    if "/hooks/" in path:
        return "hook"
    if "/scripts/" in path and path.endswith(".py"):
        return "script"
    if "/state/" in path and path.endswith(".json"):
        return "policy_state"
    if "/brain/" in path and (path.endswith(".md") or path.endswith(".ndjson")):
        return "brain_node"
    if kind in {"doc", "data"} and not _is_artifact(path):
        return "doc_value"
    return "other"


def _current_type(item: Dict[str, Any]) -> str:
    path = _normalize_path(str(item.get("path", ""))).lower()
    kind = str(item.get("kind", "")).lower()
    if "/skills/" in path:
        return "skill"
    if "/hooks/" in path:
        return "hook"
    if "/scripts/" in path and path.endswith(".py"):
        return "script"
    if "/state/" in path and path.endswith(".json"):
        return "policy_state"
    if "/brain/" in path and path.endswith(".md"):
        return "brain_node"
    if kind == "doc":
        return "doc_value"
    return "other"


def _priority(item: Dict[str, Any]) -> int:
    base = int(item.get("value_score", 0)) * 100
    size_bonus = min(int(item.get("size", 0)) // 2048, 50)
    type_bonus = {
        "hook": 140,
        "skill": 140,
        "script": 130,
        "policy_state": 120,
        "brain_node": 110,
        "doc_value": 50,
        "other": 0,
    }.get(str(item.get("legacy_type", "other")), 0)
    artifact_penalty = 400 if bool(item.get("is_artifact_execution", False)) else 0
    return base + size_bonus + type_bonus - artifact_penalty


def _dedupe_legacy(items: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
    chosen: Dict[str, Dict[str, Any]] = {}
    duplicates = 0
    for item in items:
        key = str(item.get("canonical_coldstore_key", ""))
        if not key:
            continue
        if key not in chosen:
            chosen[key] = item
            continue
        duplicates += 1
        if int(item.get("priority_score", 0)) > int(chosen[key].get("priority_score", 0)):
            chosen[key] = item
    unique = sorted(chosen.values(), key=lambda x: (-int(x.get("priority_score", 0)), x.get("path", "")))
    return unique, duplicates


def build_legacy_capability_inventory(root: str | Path) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    coldstore = _load_json(canonical_root / COLDSTORE_INDEX_PATH)
    current = _load_json(canonical_root / CURRENT_INVENTORY_PATH)

    cold_items_raw = coldstore.get("items", []) if isinstance(coldstore.get("items"), list) else []
    current_items = current.get("items", []) if isinstance(current.get("items"), list) else []

    legacy_items: List[Dict[str, Any]] = []
    for item in cold_items_raw:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path", "")).strip()
        if not path:
            continue
        normalized = _normalize_path(path)
        legacy_type = _legacy_type(item)
        artifact = _is_artifact(normalized)
        entry = {
            "candidate_id": str(item.get("candidate_id", "")).strip(),
            "path": path,
            "normalized_path": normalized,
            "bucket": str(item.get("bucket", "")),
            "legacy_type": legacy_type,
            "kind_heuristic": str(item.get("kind_heuristic", "")),
            "size": int(item.get("size", 0)),
            "sha256": str(item.get("sha256", "")).strip(),
            "content_hash": str(item.get("sha256", "")).strip(),
            "value_score": int(item.get("value_score", 0)),
            "value_keywords": [str(x) for x in item.get("value_keywords", []) if str(x).strip()],
            "feature_signature": str(item.get("feature_signature", "")),
            "is_artifact_execution": artifact,
        }
        entry["canonical_coldstore_key"] = _canonical_key(entry["path"], entry["sha256"], entry["size"])
        entry["priority_score"] = _priority(entry)
        legacy_items.append(entry)

    unique_items, suppressed_duplicates = _dedupe_legacy(legacy_items)
    filtered_items = [item for item in unique_items if not item["is_artifact_execution"] and item["legacy_type"] != "other"]

    current_sha = {str(item.get("sha256", "")).strip() for item in current_items if str(item.get("sha256", "")).strip()}
    current_basename_by_type: Dict[str, set[str]] = {}
    for item in current_items:
        ctype = _current_type(item)
        current_basename_by_type.setdefault(ctype, set()).add(Path(str(item.get("path", ""))).name.lower())

    potential_missing: Dict[str, List[Dict[str, Any]]] = {}
    gaps: List[Dict[str, Any]] = []
    for item in filtered_items:
        ltype = str(item.get("legacy_type", "other"))
        basename = Path(str(item.get("path", ""))).name.lower()
        content_hash = str(item.get("sha256", ""))
        present = False
        reasoning = ""
        if content_hash and content_hash in current_sha:
            present = True
            reasoning = "content_hash_match"
        elif basename in current_basename_by_type.get(ltype, set()):
            present = True
            reasoning = "basename_type_match"
        else:
            reasoning = "no_equivalent_detected"

        if not present:
            potential_missing.setdefault(ltype, []).append(item)
            gaps.append(
                {
                    "candidate_id": item.get("candidate_id", ""),
                    "path": item.get("path", ""),
                    "legacy_type": ltype,
                    "reason": "GAP/NO VERIFICADO: no equivalencia clara en capability_inventory current",
                }
            )
        item["comparison_reason"] = reasoning
        item["present_in_current"] = present

    for key in potential_missing:
        potential_missing[key].sort(key=lambda x: (-int(x.get("priority_score", 0)), x.get("path", "")))
    gaps = gaps[:300]

    counts_by_type: Dict[str, int] = {}
    for item in filtered_items:
        key = str(item.get("legacy_type", "other"))
        counts_by_type[key] = counts_by_type.get(key, 0) + 1

    top_by_type = {key: values[:30] for key, values in sorted(potential_missing.items())}
    summary = {
        "legacy_items_scanned_count": len(legacy_items),
        "legacy_unique_count": len(unique_items),
        "legacy_filtered_count": len(filtered_items),
        "suppressed_duplicates_count": suppressed_duplicates,
        "counts_by_type": dict(sorted(counts_by_type.items())),
        "potential_missing_by_type_counts": {key: len(values) for key, values in sorted(potential_missing.items())},
        "gaps_count": len(gaps),
    }

    report = {
        "canonical_root": str(canonical_root.resolve()),
        "created_at": _utc_now(),
        "sources": {
            "legacy_coldstore_index": COLDSTORE_INDEX_PATH.as_posix(),
            "current_capability_inventory": CURRENT_INVENTORY_PATH.as_posix(),
        },
        "summary": summary,
        "items": filtered_items,
        "top_candidates_by_type": top_by_type,
        "potential_missing_by_type": top_by_type,
        "potential_missing_candidates": [item for values in top_by_type.values() for item in values],
        "gaps_no_verificado": gaps,
        "version": 1,
    }
    return report


def _write_reports(root: str | Path, report: Dict[str, Any]) -> Dict[str, str]:
    canonical_root = get_canonical_root(root)
    _save_json(canonical_root / STATE_PATH, report)
    _save_json(canonical_root / REPORT_JSON, report)
    _save_json(canonical_root / REPORT_LOG, report)

    lines = [
        "# Legacy Capability Inventory",
        "",
        f"- Canonical root: `{report['canonical_root']}`",
        f"- Version: `{report.get('version', '?')}`",
        f"- Legacy scanned: {report['summary']['legacy_items_scanned_count']}",
        f"- Unique: {report['summary']['legacy_unique_count']}",
        f"- Filtered capability items: {report['summary']['legacy_filtered_count']}",
        f"- Suppressed duplicates: {report['summary']['suppressed_duplicates_count']}",
        f"- Counts by type: `{json.dumps(report['summary']['counts_by_type'], sort_keys=True, ensure_ascii=False)}`",
        f"- Potential missing by type: `{json.dumps(report['summary']['potential_missing_by_type_counts'], sort_keys=True, ensure_ascii=False)}`",
        f"- GAP/NO VERIFICADO count: {report['summary']['gaps_count']}",
        f"- JSON report: `{REPORT_JSON.as_posix()}`",
        f"- Log report: `{REPORT_LOG.as_posix()}`",
        "",
        "## Top candidates by type",
        "",
    ]
    tops = report.get("top_candidates_by_type", {})
    if not tops:
        lines.append("- none")
    else:
        for kind, items in sorted(tops.items()):
            lines.append(f"- `{kind}` ({len(items)}):")
            for item in items[:8]:
                lines.append(
                    f"  - `{item['path']}` | score={item.get('priority_score', 0)} | present={item.get('present_in_current', False)}"
                )

    lines.extend(["", "## GAPS / NO VERIFICADO", ""])
    gaps = report.get("gaps_no_verificado", [])
    if not gaps:
        lines.append("- none")
    else:
        for gap in gaps[:40]:
            lines.append(f"- `{gap['path']}` | type={gap['legacy_type']} | {gap['reason']}")

    (canonical_root / REPORT_MD).parent.mkdir(parents=True, exist_ok=True)
    (canonical_root / REPORT_MD).write_text("\n".join(lines) + "\n", encoding="utf-8")

    return {
        "state": STATE_PATH.as_posix(),
        "json": REPORT_JSON.as_posix(),
        "markdown": REPORT_MD.as_posix(),
        "log": REPORT_LOG.as_posix(),
    }


def run_scan(root: str | Path) -> Dict[str, Any]:
    report = build_legacy_capability_inventory(root)
    paths = _write_reports(root, report)
    return {"report": report, "paths": paths}


def main() -> int:
    parser = argparse.ArgumentParser(description="Build legacy capability inventory.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--scan", action="store_true")
    args = parser.parse_args()

    out = run_scan(args.root)
    print(
        json.dumps(
            {
                "canonical_root": out["report"]["canonical_root"],
                "summary": out["report"]["summary"],
                "paths": out["paths"],
                "version": out["report"].get("version", 0),
            },
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
