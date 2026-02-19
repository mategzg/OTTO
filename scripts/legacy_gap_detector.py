#!/usr/bin/env python3
"""Legacy gap detector v2: dedupe, noise suppression, artifact filtering, capability ranking."""

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

INVENTORY_PATH = Path("state/capability_inventory.json")
COLDSTORE_PATH = Path("state/legacy_coldstore_index.json")

STATE_PATH = Path("state/legacy_gap_report.json")
REPORT_JSON = Path("docs/_inbox/legacy_gap_report_latest.json")
REPORT_MD = Path("docs/_inbox/legacy_gap_report_latest.md")
REPORT_LOG = Path("logs/legacy_gap_report_latest.json")

ARTIFACT_GLOBS = (
    "*/docs/_inbox/**",
    "*/logs/**",
    "*/ops/**",
    "*/copilots/**",
    "*/state/**",
)
ARTIFACT_NAME_HINTS = ("report", "latest", "ledger", "_inbox", "manifest", "conflicts")
NOISE_HINTS = ("bad_path_roots/", "nested_repo_copies/")


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


def _semantic_key(path: str, feature_signature: str, value_keywords: List[str]) -> str:
    normalized_name = Path(path).name.lower()
    seed = "|".join([normalized_name, feature_signature, ",".join(sorted(value_keywords))])
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]


def _normalize_path(path: str) -> str:
    raw = path.strip()
    if not raw:
        return ""
    raw = raw.replace("\\", "/")
    raw = re.sub(r"/+", "/", raw)
    parts: List[str] = []
    for token in raw.split("/"):
        clean = token.strip()
        if not clean or clean == ".":
            continue
        if parts and parts[-1].lower() == clean.lower():
            continue
        parts.append(clean)
    return "/".join(parts)


def _path_noise_signals(path: str, normalized_path: str) -> Tuple[bool, List[str], float]:
    reasons: List[str] = []
    lower_raw = path.lower()
    lower_norm = normalized_path.lower()

    for marker in NOISE_HINTS:
        if marker in lower_raw:
            reasons.append(f"contains:{marker.rstrip('/')}")

    win_count = lower_raw.count("c:\\users") + lower_raw.count("c:/users")
    if win_count > 1:
        reasons.append("repeated_windows_user_prefix")

    if len(path) > 320:
        reasons.append("extreme_path_length")

    parts = [part.lower() for part in normalized_path.split("/") if part]
    repeated = False
    seen: Dict[str, int] = {}
    for part in parts:
        seen[part] = seen.get(part, 0) + 1
        if seen[part] >= 4:
            repeated = True
    if repeated:
        reasons.append("segment_repetition")

    quality = 1.0
    if "contains:bad_path_roots" in reasons or "contains:nested_repo_copies" in reasons:
        quality -= 0.5
    if "repeated_windows_user_prefix" in reasons:
        quality -= 0.25
    if "extreme_path_length" in reasons:
        quality -= 0.2
    if "segment_repetition" in reasons:
        quality -= 0.25
    if "docs/_inbox/" in lower_norm:
        quality -= 0.1

    quality = max(0.0, min(1.0, quality))
    return bool(reasons), sorted(set(reasons)), quality


def _is_artifact_execution_path(path: str) -> Tuple[bool, str]:
    norm = _normalize_path(path).lower()
    padded = f"/{norm}"
    for pattern in ARTIFACT_GLOBS:
        glob = pattern.lower().replace("**", "*")
        if fnmatch.fnmatch(padded, glob) or fnmatch.fnmatch(norm, glob):
            return True, f"glob:{pattern}"
    basename = Path(norm).name
    for hint in ARTIFACT_NAME_HINTS:
        if hint in basename:
            return True, f"name_hint:{hint}"
    return False, ""


def _canonical_coldstore_key(item: Dict[str, Any], normalized_path: str) -> str:
    content_hash = str(item.get("sha256", "")).strip()
    basename = Path(normalized_path or str(item.get("path", ""))).name.lower()
    size = str(int(item.get("size", 0)))
    if content_hash:
        seed = f"{content_hash}|{basename}|{size}"
    else:
        seed = f"{normalized_path}|{basename}|{size}|{item.get('feature_signature', '')}"
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:18]


def _capability_type(item: Dict[str, Any], normalized_path: str) -> str:
    lower = normalized_path.lower()
    keywords = [str(x).lower() for x in item.get("value_keywords", [])]
    kind = str(item.get("kind_heuristic", "")).lower()

    if "/hooks/" in lower:
        return "hook"
    if "/skills/" in lower:
        return "skill"
    if "/brain/" in lower:
        return "brain"
    if "/state/" in lower and lower.endswith(".json"):
        return "policy"
    if "/scripts/" in lower and lower.endswith(".py"):
        return "code"
    if any(x in keywords for x in ("runtime", "autonomy", "session", "ingest", "outbox", "openclaw")):
        return "runtime"
    if kind == "code":
        return "code"
    return "doc"


def _priority_score(item: Dict[str, Any]) -> int:
    value_score = int(item.get("value_score", 0))
    size = int(item.get("size", 0))
    size_bonus = min(size // 2048, 60)
    type_bonus = {
        "hook": 160,
        "skill": 150,
        "policy": 130,
        "brain": 120,
        "runtime": 110,
        "code": 100,
        "doc": 40,
    }.get(str(item.get("capability_type", "doc")), 20)

    penalty = 0
    path_quality = float(item.get("path_quality_score", 1.0))
    if path_quality < 0.9:
        penalty += int((1.0 - path_quality) * 220)
    if bool(item.get("is_artifact_execution", False)):
        penalty += 500
    if bool(item.get("path_noise", False)):
        penalty += 250

    basename = Path(str(item.get("normalized_path", item.get("path", "")))).name.lower()
    if any(hint in basename for hint in ARTIFACT_NAME_HINTS):
        penalty += 180
    if basename in {"manifest.json", "conflicts.json", "readme.md"}:
        penalty += 220

    return (value_score * 100) + size_bonus + type_bonus - penalty


def _status_against_current(item: Dict[str, Any], inv_sha: set[str], inv_semantic: set[str]) -> Tuple[str, str]:
    cold_sha = str(item.get("sha256", "")).strip()
    semantic = str(item.get("semantic_key", "")).strip()
    if cold_sha and cold_sha in inv_sha:
        return "duplicate_exact", "content_hash_match"
    if semantic and semantic in inv_semantic:
        return "duplicate_semantic", "semantic_match"
    return "missing_candidate", "not_found_in_current"


def _group_first(items: Iterable[Dict[str, Any]], key_name: str) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for item in items:
        key = str(item.get(key_name, "")).strip()
        if not key:
            continue
        if key not in out:
            out[key] = item
            continue
        current = out[key]
        if int(item.get("priority_score", 0)) > int(current.get("priority_score", 0)):
            out[key] = item
    return out


def _why_noise(summary: Dict[str, Any]) -> List[str]:
    lines: List[str] = []
    if int(summary.get("suppressed_path_noise_count", 0)) > 0:
        lines.append(
            f"Se suprimieron {summary['suppressed_path_noise_count']} candidatos por path_noise (bad_path_roots/nested/windows repetido)."
        )
    if int(summary.get("excluded_artifacts_count", 0)) > 0:
        lines.append(
            f"Se excluyeron {summary['excluded_artifacts_count']} artefactos de ejecución (docs/_inbox, logs, ops, copilots, state latest/report)."
        )
    if int(summary.get("suppressed_duplicates_count", 0)) > 0:
        lines.append(
            f"Se suprimieron {summary['suppressed_duplicates_count']} duplicados por canonical_coldstore_key/content_hash."
        )
    if not lines:
        lines.append("No se detectó ruido dominante en esta corrida.")
    return lines


def build_gap_report(root: str | Path) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    inventory = _load_json(canonical_root / INVENTORY_PATH)
    coldstore = _load_json(canonical_root / COLDSTORE_PATH)

    inv_items = inventory.get("items", []) if isinstance(inventory.get("items"), list) else []
    cold_items = coldstore.get("items", []) if isinstance(coldstore.get("items"), list) else []

    inv_sha = {str(item.get("sha256", "")).strip() for item in inv_items if str(item.get("sha256", "")).strip()}
    inv_semantic = {
        _semantic_key(
            path=str(item.get("path", "")),
            feature_signature=str(item.get("feature_signature", "")),
            value_keywords=[str(kw) for kw in item.get("keywords", []) if str(kw).strip()],
        )
        for item in inv_items
    }

    compared: List[Dict[str, Any]] = []
    for item in cold_items:
        bucket = str(item.get("bucket", "")).strip()
        if bucket not in {"doc_recoverable", "code_candidate_review"}:
            continue

        raw_path = str(item.get("path", ""))
        normalized_path = _normalize_path(raw_path)
        path_noise, path_noise_reasons, path_quality = _path_noise_signals(raw_path, normalized_path)
        artifact, artifact_reason = _is_artifact_execution_path(normalized_path)
        value_keywords = [str(kw) for kw in item.get("value_keywords", []) if str(kw).strip()]
        semantic = _semantic_key(
            path=raw_path,
            feature_signature=str(item.get("feature_signature", "")),
            value_keywords=value_keywords,
        )
        candidate: Dict[str, Any] = {
            "candidate_id": str(item.get("candidate_id", "")).strip(),
            "path": raw_path,
            "normalized_path": normalized_path,
            "bucket": bucket,
            "kind_heuristic": str(item.get("kind_heuristic", "")),
            "size": int(item.get("size", 0)),
            "sha256": str(item.get("sha256", "")).strip(),
            "content_hash": str(item.get("sha256", "")).strip(),
            "value_score": int(item.get("value_score", 0)),
            "value_keywords": value_keywords,
            "feature_signature": str(item.get("feature_signature", "")).strip(),
            "semantic_key": semantic,
            "path_noise": path_noise,
            "path_noise_reasons": path_noise_reasons,
            "path_quality_score": round(path_quality, 4),
            "is_artifact_execution": artifact,
            "artifact_reason": artifact_reason,
        }
        candidate["canonical_coldstore_key"] = _canonical_coldstore_key(candidate, normalized_path)
        candidate["capability_type"] = _capability_type(candidate, normalized_path)
        status, reason = _status_against_current(candidate, inv_sha, inv_semantic)
        candidate["status"] = status
        candidate["status_reason"] = reason
        candidate["priority_score"] = _priority_score(candidate)
        compared.append(candidate)

    compared.sort(key=lambda item: (-int(item["priority_score"]), item["normalized_path"], item["path"]))
    missing_all = [item for item in compared if item["status"] == "missing_candidate"]
    duplicates_exact = [item for item in compared if item["status"] == "duplicate_exact"]
    duplicates_semantic = [item for item in compared if item["status"] == "duplicate_semantic"]

    artifact_excluded = [item for item in missing_all if bool(item["is_artifact_execution"])]
    path_noise_suppressed = [item for item in missing_all if bool(item["path_noise"]) and not bool(item["is_artifact_execution"])]
    eligible = [item for item in missing_all if not bool(item["is_artifact_execution"]) and not bool(item["path_noise"])]

    grouped = _group_first(eligible, "canonical_coldstore_key")
    unique_missing = sorted(grouped.values(), key=lambda item: (-int(item["priority_score"]), item["normalized_path"], item["path"]))
    suppressed_duplicates_count = max(0, len(eligible) - len(unique_missing))

    top_missing_unique = unique_missing[:50]
    doc_missing = [item for item in unique_missing if item["bucket"] == "doc_recoverable"]
    code_missing = [item for item in unique_missing if item["bucket"] == "code_candidate_review"]

    type_counts: Dict[str, int] = {}
    for item in unique_missing:
        key = str(item.get("capability_type", "doc"))
        type_counts[key] = type_counts.get(key, 0) + 1

    summary = {
        "compared_count": len(compared),
        "missing_count": len(missing_all),
        "missing_unique_count": len(unique_missing),
        "doc_missing_count": len(doc_missing),
        "code_missing_count": len(code_missing),
        "duplicate_exact_count": len(duplicates_exact),
        "duplicate_semantic_count": len(duplicates_semantic),
        "suppressed_duplicates_count": suppressed_duplicates_count,
        "suppressed_path_noise_count": len(path_noise_suppressed),
        "excluded_artifacts_count": len(artifact_excluded),
        "bucket_by_type": dict(sorted(type_counts.items())),
    }

    report = {
        "canonical_root": str(canonical_root.resolve()),
        "created_at": _utc_now(),
        "sources": {
            "inventory": INVENTORY_PATH.as_posix(),
            "coldstore_index": COLDSTORE_PATH.as_posix(),
        },
        "summary": summary,
        "items": compared,
        "top_missing_unique": top_missing_unique,
        "doc_recoverable_missing": doc_missing[:500],
        "code_candidate_review_missing": code_missing[:500],
        "duplicates_exact": duplicates_exact[:300],
        "duplicates_semantic": duplicates_semantic[:300],
        "suppressed_artifact_candidates": artifact_excluded[:300],
        "suppressed_path_noise_candidates": path_noise_suppressed[:300],
        "why_prior_top20_was_noise": _why_noise(summary),
        "version": 2,
    }
    return report


def _write_reports(root: str | Path, report: Dict[str, Any]) -> Dict[str, str]:
    canonical_root = get_canonical_root(root)
    _save_json(canonical_root / STATE_PATH, report)
    _save_json(canonical_root / REPORT_JSON, report)
    _save_json(canonical_root / REPORT_LOG, report)

    lines = [
        "# Legacy Gap Report v2",
        "",
        f"- Canonical root: `{report['canonical_root']}`",
        f"- Version: `{report.get('version', '?')}`",
        f"- Compared: {report['summary']['compared_count']}",
        f"- Missing (raw): {report['summary']['missing_count']}",
        f"- Missing unique: {report['summary']['missing_unique_count']}",
        f"- Suppressed duplicates: {report['summary']['suppressed_duplicates_count']}",
        f"- Suppressed path noise: {report['summary']['suppressed_path_noise_count']}",
        f"- Excluded artifacts: {report['summary']['excluded_artifacts_count']}",
        f"- Bucket by type: `{json.dumps(report['summary']['bucket_by_type'], sort_keys=True, ensure_ascii=False)}`",
        f"- JSON report: `{REPORT_JSON.as_posix()}`",
        f"- Log report: `{REPORT_LOG.as_posix()}`",
        "",
        "## Why prior top20 was noise",
        "",
    ]
    for reason in report.get("why_prior_top20_was_noise", []):
        lines.append(f"- {reason}")

    lines.extend(["", "## Top Missing Unique Candidates (max 50)", ""])
    top_missing = report.get("top_missing_unique", [])
    if not top_missing:
        lines.append("- none")
    else:
        for item in top_missing:
            lines.append(
                f"- `{item['path']}` | type={item.get('capability_type','')} | score={item['priority_score']} | key={item.get('canonical_coldstore_key','')}"
            )

    (canonical_root / REPORT_MD).parent.mkdir(parents=True, exist_ok=True)
    (canonical_root / REPORT_MD).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "state": STATE_PATH.as_posix(),
        "json": REPORT_JSON.as_posix(),
        "markdown": REPORT_MD.as_posix(),
        "log": REPORT_LOG.as_posix(),
    }


def run_scan(root: str | Path) -> Dict[str, Any]:
    report = build_gap_report(root)
    paths = _write_reports(root, report)
    return {"report": report, "paths": paths}


def main() -> int:
    parser = argparse.ArgumentParser(description="Detect capability gaps between coldstore and current repo (v2).")
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
