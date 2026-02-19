#!/usr/bin/env python3
"""Legacy recovery worker v2: policy-gated safe packaging from coldstore candidates."""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import re
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.repo_root import get_canonical_root

LEGACY_INVENTORY_PATH = Path("state/legacy_capability_inventory.json")
GAP_REPORT_PATH = Path("state/legacy_gap_report.json")
POLICY_PATH = Path("state/legacy_recovery_policy.json")
STATE_PATH = Path("state/legacy_recovery_state.json")

TARGET_BASE = Path("vault/inbox_raw/_pending_drop/legacy_recovery")
ALLOWED_SOURCE_PREFIXES = ("vault/_salvage/", "vault/_quarantine/")
RESERVED_RE = re.compile(r"^(agents(\.override)?|claude(\.local)?)\.md$", re.IGNORECASE)

REPORT_JSON = Path("docs/_inbox/legacy_recovery_latest.json")
REPORT_MD = Path("docs/_inbox/legacy_recovery_latest.md")
REPORT_LOG = Path("logs/legacy_recovery_latest.json")

DEFAULT_POLICY: Dict[str, Any] = {
    "version": 2,
    "enabled": False,
    "interval_minutes": 720,
    "scan_interval_hours": 12,
    "max_items_per_tick": 10,
    "max_bytes_per_tick": 25 * 1024 * 1024,
    "allow_types": ["doc_value", "brain_node"],
    "recoverable_extensions": [".md", ".txt", ".pdf", ".json", ".ndjson", ".csv", ".html"],
    "denylist_extensions": [".env", ".pem", ".key", ".pfx", ".exe", ".dll", ".so", ".dylib", ".bin"],
    "forbidden_buckets": ["sensitive_blocked", "instruction_drift_blocked", "code_candidate_review"],
    "exclude_globs": [
        "*/docs/_inbox/**",
        "*/logs/**",
        "*/ops/**",
        "*/copilots/**",
        "*/state/**",
        "*latest*",
        "*report*",
        "*ledger*",
    ],
    "target_drop_base": TARGET_BASE.as_posix(),
    "secret_patterns": ["api key", "token", "secret", "password", "private key", "bearer", "credential"],
}

DEFAULT_STATE: Dict[str, Any] = {
    "version": 2,
    "last_run_utc": "",
    "last_status": "never",
    "last_scan_ts": "",
    "last_scan_status": "never",
    "last_batch_id": "",
    "last_packaged_ids": [],
    "processed_candidate_ids": [],
    "processed_batches": [],
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_now() -> str:
    return _utc_now().isoformat()


def _stamp() -> str:
    return _utc_now().strftime("%Y%m%dT%H%M%SZ")


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


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sample_text(path: Path, max_bytes: int = 64 * 1024) -> str:
    try:
        raw = path.read_bytes()[:max_bytes]
    except OSError:
        return ""
    return raw.decode("utf-8", errors="ignore")


def _parse_iso(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _normalize_path(path: str) -> str:
    return re.sub(r"/+", "/", path.strip().replace("\\", "/")).strip("/")


def _side_by_side_path(path: Path, marker: str) -> Path:
    if not path.exists():
        return path
    stem = path.with_suffix("") if path.suffix else path
    ext = path.suffix
    idx = 1
    while True:
        candidate = Path(f"{stem}__from_{marker}_{idx}{ext}") if ext else Path(f"{stem}__from_{marker}_{idx}")
        if not candidate.exists():
            return candidate
        idx += 1


def _load_policy(root: Path) -> Dict[str, Any]:
    path = root / POLICY_PATH
    payload = _load_json(path)
    policy = dict(DEFAULT_POLICY)
    policy.update(payload)

    # backward compatibility from v1 keys
    if "max_items_per_tick" not in payload and "max_files_per_tick" in payload:
        policy["max_items_per_tick"] = int(payload.get("max_files_per_tick", DEFAULT_POLICY["max_items_per_tick"]))
    if "max_bytes_per_tick" not in payload and "max_total_bytes_per_tick" in payload:
        policy["max_bytes_per_tick"] = int(payload.get("max_total_bytes_per_tick", DEFAULT_POLICY["max_bytes_per_tick"]))
    if not path.is_file():
        _save_json(path, policy)
    return policy


def _load_state(root: Path) -> Dict[str, Any]:
    path = root / STATE_PATH
    payload = _load_json(path)
    state = dict(DEFAULT_STATE)
    state.update(payload)
    for key in ("last_packaged_ids", "processed_candidate_ids", "processed_batches"):
        if not isinstance(state.get(key), list):
            state[key] = []
    if not path.is_file():
        _save_json(path, state)
    return state


def _is_allowed_source(rel_path: str) -> bool:
    clean = rel_path.strip()
    return any(clean.startswith(prefix) for prefix in ALLOWED_SOURCE_PREFIXES)


def _is_reserved_instruction_name(path: str) -> bool:
    return bool(RESERVED_RE.match(Path(path).name))


def _match_exclude_globs(path: str, globs: Iterable[str]) -> str:
    normalized = _normalize_path(path).lower()
    padded = f"/{normalized}"
    for pattern in globs:
        glob = str(pattern).lower().replace("**", "*")
        if fnmatch.fnmatch(normalized, glob) or fnmatch.fnmatch(padded, glob):
            return str(pattern)
        if fnmatch.fnmatch(Path(normalized).name, glob):
            return str(pattern)
    return ""


def _secret_hit(path: Path, policy: Dict[str, Any]) -> List[str]:
    haystack = f"{path.name.lower()}\n{_sample_text(path).lower()}"
    hits: List[str] = []
    for token in policy.get("secret_patterns", []):
        needle = str(token).strip().lower()
        if needle and needle in haystack:
            hits.append(needle)
    return sorted(set(hits))


def _load_candidate_pool(root: Path) -> List[Dict[str, Any]]:
    legacy_inventory = _load_json(root / LEGACY_INVENTORY_PATH)
    gap_report = _load_json(root / GAP_REPORT_PATH)

    # Prefer explicit potential missing from legacy capability inventory.
    potential = legacy_inventory.get("potential_missing_candidates", [])
    if isinstance(potential, list) and potential:
        out = [item for item in potential if isinstance(item, dict)]
        if out:
            return out

    # Fallback to v2 gap output.
    top_missing = gap_report.get("top_missing_unique", [])
    if isinstance(top_missing, list) and top_missing:
        return [item for item in top_missing if isinstance(item, dict)]

    # Backward fallback (v1 format).
    doc_missing = gap_report.get("doc_recoverable_missing", [])
    if isinstance(doc_missing, list):
        return [item for item in doc_missing if isinstance(item, dict)]
    return []


def _candidate_allowed(candidate: Dict[str, Any], policy: Dict[str, Any], root: Path) -> Tuple[bool, str]:
    bucket = str(candidate.get("bucket", "")).strip()
    if bucket in {str(x) for x in policy.get("forbidden_buckets", [])}:
        return False, f"forbidden_bucket:{bucket}"

    ctype = str(candidate.get("legacy_type", candidate.get("capability_type", "doc_value"))).strip()
    allow_types = {str(x) for x in policy.get("allow_types", [])}
    if ctype not in allow_types:
        return False, f"type_not_allowed:{ctype}"

    rel = _normalize_path(str(candidate.get("path", "")))
    if not rel or not _is_allowed_source(rel):
        return False, "path_not_allowed"
    if _is_reserved_instruction_name(rel):
        return False, "reserved_instruction_name"

    exclude_match = _match_exclude_globs(rel, policy.get("exclude_globs", []))
    if exclude_match:
        return False, f"exclude_glob:{exclude_match}"

    src = root / rel
    if not src.is_file():
        return False, "source_missing"

    ext = src.suffix.lower()
    deny = {str(x).lower() for x in policy.get("denylist_extensions", [])}
    allow = {str(x).lower() for x in policy.get("recoverable_extensions", [])}
    if ext in deny:
        return False, f"denylist_extension:{ext}"
    if ext not in allow:
        return False, f"extension_not_recoverable:{ext}"

    secret_hits = _secret_hit(src, policy)
    if secret_hits:
        return False, f"sensitive:{','.join(secret_hits)}"
    return True, "ok"


def _write_reports(root: Path, report: Dict[str, Any]) -> Dict[str, str]:
    _save_json(root / REPORT_JSON, report)
    _save_json(root / REPORT_LOG, report)

    lines = [
        "# Legacy Recovery Latest v2",
        "",
        f"- Status: `{report['status']}`",
        f"- Policy enabled: `{report['policy']['enabled']}`",
        f"- Legacy scan ran: `{report['summary'].get('legacy_scan_ran', False)}`",
        f"- Disabled reason: `{report['summary'].get('legacy_disabled_reason', '')}`",
        f"- Selected count: {report['summary']['selected_count']}",
        f"- Packaged count: {report['summary']['packaged_count']}",
        f"- Blocked count: {report['summary']['blocked_count']}",
        f"- Total bytes packaged: {report['summary']['packaged_bytes']}",
        f"- Batch path: `{report.get('batch_path', '')}`",
        f"- JSON report: `{REPORT_JSON.as_posix()}`",
        f"- Log report: `{REPORT_LOG.as_posix()}`",
        "",
        "## Selected",
        "",
    ]
    selected = report.get("selected", [])
    if not selected:
        lines.append("- none")
    else:
        for item in selected[:40]:
            lines.append(
                f"- `{item['path']}` | type={item.get('legacy_type', item.get('capability_type', ''))} | size={item['size']} | score={item.get('priority_score', 0)}"
            )
    lines.extend(["", "## Blocked", ""])
    blocked = report.get("blocked", [])
    if not blocked:
        lines.append("- none")
    else:
        for item in blocked[:40]:
            lines.append(f"- `{item.get('path', '')}` | reason={item.get('reason', '')}")

    (root / REPORT_MD).parent.mkdir(parents=True, exist_ok=True)
    (root / REPORT_MD).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "json": REPORT_JSON.as_posix(),
        "markdown": REPORT_MD.as_posix(),
        "log": REPORT_LOG.as_posix(),
        "policy": POLICY_PATH.as_posix(),
        "state": STATE_PATH.as_posix(),
    }


def run_once(root: str | Path, *, force: bool = False) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    policy = _load_policy(canonical_root)
    state = _load_state(canonical_root)
    now = _utc_now()

    run_interval = max(1, int(policy.get("interval_minutes", 720)))
    scan_interval_hours = max(1, int(policy.get("scan_interval_hours", 12)))
    last_run = _parse_iso(str(state.get("last_run_utc", "")))
    last_scan = _parse_iso(str(state.get("last_scan_ts", "")))

    report: Dict[str, Any] = {
        "canonical_root": str(canonical_root.resolve()),
        "created_at": now.isoformat(),
        "policy": {
            "enabled": bool(policy.get("enabled", False)),
            "interval_minutes": run_interval,
            "scan_interval_hours": scan_interval_hours,
            "max_items_per_tick": int(policy.get("max_items_per_tick", 10)),
            "max_bytes_per_tick": int(policy.get("max_bytes_per_tick", 25 * 1024 * 1024)),
            "allow_types": [str(x) for x in policy.get("allow_types", [])],
            "target_drop_base": str(policy.get("target_drop_base", TARGET_BASE.as_posix())),
        },
        "status": "unknown",
        "selected": [],
        "blocked": [],
        "packaged": [],
        "summary": {
            "legacy_scan_ran": False,
            "legacy_disabled_reason": "",
            "selected_count": 0,
            "packaged_count": 0,
            "blocked_count": 0,
            "packaged_bytes": 0,
        },
        "version": 2,
    }

    if not bool(policy.get("enabled", False)):
        report["status"] = "disabled"
        report["summary"]["legacy_disabled_reason"] = "policy_disabled"
        state["last_run_utc"] = now.isoformat()
        state["last_status"] = "disabled"
        _save_json(canonical_root / STATE_PATH, state)
        paths = _write_reports(canonical_root, report)
        return {"report": report, "paths": paths}

    if (not force) and last_run and (now - last_run) < timedelta(minutes=run_interval):
        report["status"] = "skipped_interval"
        report["summary"]["legacy_disabled_reason"] = "run_interval_not_elapsed"
        state["last_run_utc"] = now.isoformat()
        state["last_status"] = "skipped_interval"
        _save_json(canonical_root / STATE_PATH, state)
        paths = _write_reports(canonical_root, report)
        return {"report": report, "paths": paths}

    if (not force) and last_scan and (now - last_scan) < timedelta(hours=scan_interval_hours):
        report["status"] = "skipped_scan_interval"
        report["summary"]["legacy_disabled_reason"] = "scan_interval_not_elapsed"
        state["last_run_utc"] = now.isoformat()
        state["last_status"] = "skipped_scan_interval"
        _save_json(canonical_root / STATE_PATH, state)
        paths = _write_reports(canonical_root, report)
        return {"report": report, "paths": paths}

    report["summary"]["legacy_scan_ran"] = True
    state["last_scan_ts"] = now.isoformat()
    state["last_scan_status"] = "ran"

    pool = _load_candidate_pool(canonical_root)
    if not pool:
        report["status"] = "no_gap_candidates"
        report["summary"]["legacy_disabled_reason"] = "empty_candidate_pool"
        state["last_run_utc"] = now.isoformat()
        state["last_status"] = "no_gap_candidates"
        _save_json(canonical_root / STATE_PATH, state)
        paths = _write_reports(canonical_root, report)
        return {"report": report, "paths": paths}

    processed_ids = {str(item) for item in state.get("processed_candidate_ids", [])}
    max_items = max(1, int(policy.get("max_items_per_tick", 10)))
    max_bytes = max(1, int(policy.get("max_bytes_per_tick", 25 * 1024 * 1024)))

    selected: List[Dict[str, Any]] = []
    blocked: List[Dict[str, Any]] = []
    selected_bytes = 0
    for candidate in pool:
        candidate_id = str(candidate.get("candidate_id", "")).strip()
        rel = _normalize_path(str(candidate.get("path", "")))
        if not candidate_id or not rel:
            continue
        if candidate_id in processed_ids:
            continue

        allowed, reason = _candidate_allowed(candidate, policy, canonical_root)
        if not allowed:
            blocked.append({"candidate_id": candidate_id, "path": rel, "reason": reason})
            continue
        src = canonical_root / rel
        size = int(src.stat().st_size) if src.is_file() else int(candidate.get("size", 0))
        if len(selected) >= max_items:
            blocked.append({"candidate_id": candidate_id, "path": rel, "reason": "max_items_per_tick"})
            continue
        if selected_bytes + size > max_bytes:
            blocked.append({"candidate_id": candidate_id, "path": rel, "reason": "max_bytes_per_tick"})
            continue
        selected.append(candidate)
        selected_bytes += size

    report["selected"] = selected
    report["blocked"] = blocked
    report["summary"]["selected_count"] = len(selected)
    report["summary"]["blocked_count"] = len(blocked)

    if not selected:
        report["status"] = "no_candidates_selected"
        report["summary"]["legacy_disabled_reason"] = "selection_rules_filtered_all"
        state["last_run_utc"] = now.isoformat()
        state["last_status"] = "no_candidates_selected"
        _save_json(canonical_root / STATE_PATH, state)
        paths = _write_reports(canonical_root, report)
        return {"report": report, "paths": paths}

    target_base = canonical_root / str(policy.get("target_drop_base", TARGET_BASE.as_posix()))
    batch_key_seed = "|".join(sorted(str(item.get("canonical_coldstore_key", item.get("candidate_id", ""))) for item in selected))
    batch_id = hashlib.sha1(batch_key_seed.encode("utf-8")).hexdigest()[:12]
    batch_dir = target_base / f"{_stamp()}_{batch_id}"
    source_dir = batch_dir / "source"
    source_dir.mkdir(parents=True, exist_ok=True)

    manifest_entries: List[Dict[str, Any]] = []
    packaged: List[Dict[str, Any]] = []
    for item in selected:
        rel = _normalize_path(str(item.get("path", "")))
        src = canonical_root / rel
        marker = str(item.get("candidate_id", "na"))
        safe_name = rel.replace("/", "__")
        dst = _side_by_side_path(source_dir / safe_name, marker)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        stat = dst.stat()
        entry = {
            "candidate_id": marker,
            "legacy_type": str(item.get("legacy_type", item.get("capability_type", ""))),
            "source_path": rel,
            "rel_path": dst.resolve().relative_to(source_dir.resolve()).as_posix(),
            "size": stat.st_size,
            "mtime": stat.st_mtime,
            "sha256": _sha256_file(dst),
            "canonical_coldstore_key": str(item.get("canonical_coldstore_key", "")),
            "content_hash": str(item.get("content_hash", item.get("sha256", ""))),
            "origin_bucket": str(item.get("bucket", "")),
        }
        manifest_entries.append(entry)
        packaged.append(
            {
                "candidate_id": marker,
                "source_path": rel,
                "copied_path": dst.resolve().relative_to(canonical_root.resolve()).as_posix(),
                "size": stat.st_size,
                "legacy_type": entry["legacy_type"],
            }
        )

    manifest = {
        "created_at": _iso_now(),
        "source_kind": "legacy_recovery_v2",
        "file_count": len(manifest_entries),
        "entries": manifest_entries,
        "version": 2,
    }
    event_meta = {
        "created_at": _iso_now(),
        "source_kind": "legacy_recovery_v2",
        "recommended_domain": "external_ingest",
        "batch_id": batch_id,
        "origin_buckets": sorted({str(entry["origin_bucket"]) for entry in manifest_entries}),
        "canonical_coldstore_keys": sorted({str(entry["canonical_coldstore_key"]) for entry in manifest_entries if entry["canonical_coldstore_key"]}),
        "content_hashes": sorted({str(entry["content_hash"]) for entry in manifest_entries if entry["content_hash"]}),
        "source_refs": sorted({entry["source_path"] for entry in manifest_entries}),
        "version": 2,
    }
    readme = "\n".join(
        [
            "# Legacy Recovery Package v2",
            "",
            f"- Batch ID: `{batch_id}`",
            "- Source kind: `legacy_recovery_v2`",
            f"- File count: {len(manifest_entries)}",
            f"- Origin coldstore paths: {len(event_meta['source_refs'])}",
            "- Manifest: `MANIFEST.json`",
            "- Event meta: `EVENT_META.json`",
            "",
            "Paquete generado por policy-gated recovery v2. No contiene auto-merge de codigo.",
        ]
    )

    (batch_dir / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (batch_dir / "EVENT_META.json").write_text(
        json.dumps(event_meta, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (batch_dir / "README.md").write_text(readme + "\n", encoding="utf-8")

    state["last_run_utc"] = now.isoformat()
    state["last_status"] = "packaged"
    state["last_batch_id"] = batch_id
    state["last_packaged_ids"] = sorted({str(item.get("candidate_id", "")) for item in selected if str(item.get("candidate_id", ""))})[:500]
    state["processed_candidate_ids"] = sorted(processed_ids | set(state["last_packaged_ids"]))
    batches = list(state.get("processed_batches", []))
    batches.append(
        {
            "batch_id": batch_id,
            "created_at": _iso_now(),
            "batch_path": batch_dir.resolve().relative_to(canonical_root.resolve()).as_posix(),
            "file_count": len(manifest_entries),
            "source_kind": "legacy_recovery_v2",
        }
    )
    state["processed_batches"] = batches[-200:]
    _save_json(canonical_root / STATE_PATH, state)

    report["status"] = "packaged"
    report["batch_id"] = batch_id
    report["batch_path"] = batch_dir.resolve().relative_to(canonical_root.resolve()).as_posix()
    report["packaged"] = packaged
    report["summary"]["packaged_count"] = len(packaged)
    report["summary"]["packaged_bytes"] = sum(int(item["size"]) for item in packaged)

    paths = _write_reports(canonical_root, report)
    return {"report": report, "paths": paths}


def main() -> int:
    parser = argparse.ArgumentParser(description="Package safe legacy docs from coldstore into pending_drop (v2).")
    parser.add_argument("--root", default=".")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    out = run_once(args.root, force=args.force)
    print(
        json.dumps(
            {
                "canonical_root": out["report"]["canonical_root"],
                "status": out["report"]["status"],
                "summary": out["report"]["summary"],
                "paths": out["paths"],
                "version": out["report"].get("version", 0),
            },
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
    )
    return 0 if out["report"]["status"] in {"disabled", "skipped_interval", "skipped_scan_interval", "no_gap_candidates", "no_candidates_selected", "packaged"} else 3


if __name__ == "__main__":
    raise SystemExit(main())
