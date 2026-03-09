#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from scripts.repo_root import get_canonical_root

SUPPORTED = {".docx", ".pdf", ".html", ".htm", ".xlsx", ".txt", ".md"}


def detect_sharepoint_root() -> Path | None:
    candidates = [
        Path("/mnt/c/Users/sgaca/SG Acabados"),
        Path("/mnt/c/Users") / os.getenv("USERNAME", "") / "SG Acabados",
        Path.home() / "SG Acabados",
    ]
    for c in candidates:
        if c.is_dir():
            return c
    return None


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _to_markdown(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in {".md", ".txt"}:
        return path.read_text(encoding="utf-8", errors="replace")
    if ext in {".html", ".htm"}:
        raw = path.read_text(encoding="utf-8", errors="replace")
        clean = raw.replace("<br>", "\n").replace("<br/>", "\n")
        import re

        clean = re.sub(r"<[^>]+>", "", clean)
        return clean.strip()
    return f"[binary:{ext}] {path.name}"


def _classify(rel: str) -> Dict[str, str]:
    lower = rel.lower()
    audience = "sg"
    domain = "sg_acabados"
    if any(x in lower for x in ["personal", "privado", "mateo"]):
        audience = "personal"
        domain = "personal_ops"
    return {"audience_tag": audience, "domain_tag": domain}


def run_incremental_sync(root: str | Path, source_root: Path | None = None) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    source = source_root or detect_sharepoint_root()
    manifest_path = canonical_root / "state" / "sharepoint_sync_manifest.json"
    out_dir = canonical_root / "vault" / "inbox_raw" / "_processed" / "sharepoint_sg_acabados"
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    old = {"files": {}}
    if manifest_path.is_file():
        try:
            old = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            old = {"files": {}}
    old.setdefault("files", {})

    if source is None or not source.is_dir():
        report = {"status": "missing_source", "source": None, "processed": 0, "changed": 0}
        (canonical_root / "docs" / "_inbox").mkdir(parents=True, exist_ok=True)
        (canonical_root / "docs" / "_inbox" / "sharepoint_sync_latest.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        return report

    changed = 0
    processed = 0
    files: Dict[str, Any] = {}

    for p in source.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in SUPPORTED:
            continue
        rel = p.relative_to(source).as_posix()
        stat = p.stat()
        digest = _sha256(p)
        prev = old["files"].get(rel)
        same = prev and prev.get("hash") == digest and float(prev.get("mtime", 0)) == float(stat.st_mtime)
        meta = {"mtime": stat.st_mtime, "hash": digest, "size": stat.st_size, **_classify(rel)}
        files[rel] = meta
        if same:
            continue
        changed += 1
        md = _to_markdown(p)
        target_branch = "brain/domains/sg_acabados" if meta["audience_tag"] == "sg" else "brain/domains/personal_ops"
        target = out_dir / f"{digest[:12]}_{Path(rel).name}.md"
        target.write_text(f"# {p.name}\n\n<!-- audience:{meta['audience_tag']} domain:{meta['domain_tag']} -->\n\n{md}\n\nsource_rel: {rel}\nroute_target: {target_branch}\n", encoding="utf-8")
        processed += 1

    new_manifest = {
        "source_root": str(source),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "files": files,
    }
    manifest_path.write_text(json.dumps(new_manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    report = {
        "status": "ok",
        "source": str(source),
        "changed": changed,
        "processed": processed,
        "total_seen": len(files),
        "manifest": manifest_path.relative_to(canonical_root).as_posix(),
    }
    (canonical_root / "docs" / "_inbox").mkdir(parents=True, exist_ok=True)
    (canonical_root / "docs" / "_inbox" / "sharepoint_sync_latest.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report
