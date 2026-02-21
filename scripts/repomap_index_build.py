#!/usr/bin/env python3
from __future__ import annotations
import json, re, sys
from pathlib import Path
from typing import Dict, Any, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.repo_root import get_canonical_root

TITLE_RE = re.compile(r"^\s*#\s+(.+?)\s*$")
TOKEN_RE = re.compile(r"[a-z0-9_]{3,}")


def _title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        m = TITLE_RE.match(line)
        if m:
            return m.group(1).strip()[:180]
    return fallback


def build(root: str | Path) -> Dict[str, Any]:
    r = get_canonical_root(root)
    paths: List[Path] = []
    top = r / "REPO_MAP.md"
    if top.is_file():
        paths.append(top)
    rm = r / "repo_map"
    if rm.is_dir():
        paths.extend(sorted([p for p in rm.glob("*.md") if p.is_file()], key=lambda p: p.name))

    records: Dict[str, Any] = {}
    inverted: Dict[str, List[str]] = {}
    for p in paths:
        rel = p.resolve().relative_to(r.resolve()).as_posix()
        txt = p.read_text(encoding="utf-8", errors="ignore")
        rid = f"repomap::{rel}"
        rec = {"id": rid, "path": rel, "title": _title(txt, p.stem), "source_ref": f"{rel}#md"}
        records[rid] = rec
        basis = (rec["title"] + "\n" + rel + "\n" + txt[:6000]).lower()
        for t in sorted(set(TOKEN_RE.findall(basis))):
            inverted.setdefault(t, []).append(rid)

    payload = {
        "version": 1,
        "updated_at": __import__('datetime').datetime.utcnow().isoformat() + 'Z',
        "records": records,
        "inverted": inverted,
        "summary": {"record_count": len(records), "token_count": len(inverted)},
    }
    out = r / "state" / "repomap_registry.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(out.resolve().relative_to(r.resolve()).as_posix())
    return payload


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    args = ap.parse_args()
    build(args.root)
