#!/usr/bin/env python3
"""Build deterministic Brain Router v1 report and optional raw source ingest."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.repo_root import get_canonical_root

DOMAIN_DIR = Path("brain/domains/openclaw_ops")
CARDS_DIR = Path("brain/cards/openclaw_ops")
REPORT_MD = Path("docs/_inbox/brain_ops_router_report_latest.md")
REPORT_JSON = Path("docs/_inbox/brain_ops_router_report_latest.json")
REPORT_LOG = Path("logs/brain_ops_router_latest.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _save_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_lines(path: Path) -> List[str]:
    return path.read_text(encoding="utf-8").splitlines()


def _extract_source_refs(card_path: Path) -> List[str]:
    refs: List[str] = []
    for line in _read_lines(card_path):
        if not line.lower().startswith("source_ref:"):
            continue
        raw = line.split(":", 1)[1].strip()
        for chunk in raw.split(";"):
            ref = chunk.strip()
            if ref:
                refs.append(ref)
    return sorted(set(refs))


def _extract_routes(router_path: Path) -> List[str]:
    routes: List[str] = []
    for line in _read_lines(router_path):
        clean = line.strip()
        if "->" not in clean:
            continue
        if clean.startswith("- ") or clean.startswith("1.") or clean.startswith("2.") or clean.startswith("3."):
            routes.append(clean)
    return sorted(set(routes))


def _iter_files(root: Path) -> Sequence[Path]:
    out: List[Path] = []
    for dirpath, _dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        current = Path(dirpath)
        for filename in sorted(filenames):
            fp = current / filename
            if fp.is_symlink():
                continue
            out.append(fp)
    return sorted(out, key=lambda p: p.as_posix())


def _ingest_raw_source(canonical_root: Path, source_dir: Path) -> Dict[str, Any]:
    if not source_dir.exists():
        return {"ingested": False, "reason": "source_missing", "source_dir": str(source_dir)}
    if not source_dir.is_dir():
        return {"ingested": False, "reason": "source_not_dir", "source_dir": str(source_dir)}

    stamp = _stamp()
    target_root = canonical_root / "vault" / "inbox_raw" / "claude_inverse_engineering" / stamp
    source_out = target_root / "source"
    source_out.mkdir(parents=True, exist_ok=True)

    manifest_entries: List[Dict[str, Any]] = []
    for src in _iter_files(source_dir):
        rel = src.resolve().relative_to(source_dir.resolve()).as_posix()
        dst = source_out / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

        stat = src.stat()
        manifest_entries.append(
            {
                "mtime": stat.st_mtime,
                "rel_path": rel,
                "sha256": _sha256(dst),
                "size": stat.st_size,
                "source_path": str(src.resolve()),
            }
        )

    manifest_entries.sort(key=lambda item: item["rel_path"])
    manifest = {
        "created_at": _utc_now(),
        "entry_count": len(manifest_entries),
        "entries": manifest_entries,
        "source_dir": str(source_dir.resolve()),
        "target_dir": str(target_root.resolve()),
        "version": 1,
    }
    manifest_path = target_root / "MANIFEST.json"
    _save_json(manifest_path, manifest)

    readme = target_root / "README.md"
    readme.write_text(
        "\n".join(
            [
                "# Claude Inverse Engineering Raw Source",
                "",
                f"- Source dir: `{source_dir.resolve()}`",
                f"- Target dir: `{target_root.resolve()}`",
                "- Reason: preserve raw corpus as source-of-derivation for Brain patterns.",
                "- Rule: raw source is not indexed by Brain indexer; derived knowledge lives in brain/domain nodes and cards.",
                "- Rebuild: rerun `python3 scripts/brain_ops_router_build.py --ingest-source <path>`.",
                "- Manifest: `MANIFEST.json`.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    return {
        "ingested": True,
        "entry_count": len(manifest_entries),
        "manifest": manifest_path.resolve().relative_to(canonical_root.resolve()).as_posix(),
        "readme": readme.resolve().relative_to(canonical_root.resolve()).as_posix(),
        "target_dir": target_root.resolve().relative_to(canonical_root.resolve()).as_posix(),
    }


def build_report(canonical_root: Path, raw_ingest: Dict[str, Any]) -> Dict[str, Any]:
    domain_dir = canonical_root / DOMAIN_DIR
    cards_dir = canonical_root / CARDS_DIR

    domain_nodes = sorted(
        [p.resolve().relative_to(canonical_root.resolve()).as_posix() for p in domain_dir.glob("*.md") if p.is_file()]
    )
    cards = sorted([p for p in cards_dir.glob("*.md") if p.is_file()], key=lambda p: p.name)
    card_paths = [p.resolve().relative_to(canonical_root.resolve()).as_posix() for p in cards]

    source_refs: List[Dict[str, Any]] = []
    for card in cards:
        refs = _extract_source_refs(card)
        for ref in refs:
            exists = (canonical_root / ref).exists()
            source_refs.append(
                {
                    "card": card.resolve().relative_to(canonical_root.resolve()).as_posix(),
                    "exists": exists,
                    "source_ref": ref,
                }
            )
    source_refs.sort(key=lambda item: (item["card"], item["source_ref"]))

    routes = _extract_routes(canonical_root / DOMAIN_DIR / "01_ROUTER.md")
    unresolved_refs = [item for item in source_refs if not item["exists"]]

    return {
        "canonical_root": str(canonical_root.resolve()),
        "created_at": _utc_now(),
        "domain_hub": "brain/domains/openclaw_ops/00_INDEX.md",
        "domain_nodes": domain_nodes,
        "cards": card_paths,
        "routes": routes,
        "source_refs": source_refs,
        "raw_ingest": raw_ingest,
        "summary": {
            "card_count": len(card_paths),
            "domain_node_count": len(domain_nodes),
            "route_count": len(routes),
            "source_ref_count": len(source_refs),
            "unresolved_source_refs": len(unresolved_refs),
        },
        "unresolved_source_refs": unresolved_refs,
        "version": 1,
    }


def write_report(canonical_root: Path, report: Dict[str, Any]) -> Dict[str, str]:
    _save_json(canonical_root / REPORT_JSON, report)
    _save_json(canonical_root / REPORT_LOG, report)

    lines: List[str] = [
        "# Brain Ops Router Report",
        "",
        f"- Canonical root: `{report['canonical_root']}`",
        f"- Domain hub: `{report['domain_hub']}`",
        f"- Domain nodes: {report['summary']['domain_node_count']}",
        f"- Cards: {report['summary']['card_count']}",
        f"- Routes: {report['summary']['route_count']}",
        f"- Source refs: {report['summary']['source_ref_count']}",
        f"- Unresolved source refs: {report['summary']['unresolved_source_refs']}",
        f"- JSON report: `{REPORT_JSON.as_posix()}`",
        f"- Log report: `{REPORT_LOG.as_posix()}`",
        "",
        "## Domain Nodes",
        "",
    ]
    lines.extend([f"- `{item}`" for item in report["domain_nodes"]] or ["- None"])

    lines.extend(["", "## Cards", ""])
    lines.extend([f"- `{item}`" for item in report["cards"]] or ["- None"])

    lines.extend(["", "## Recommended Routes", ""])
    lines.extend([f"- {item}" for item in report["routes"]] or ["- None"])

    lines.extend(["", "## Raw Source", ""])
    raw = report["raw_ingest"]
    if raw.get("ingested"):
        lines.append(f"- Ingested: true ({raw.get('entry_count', 0)} files)")
        lines.append(f"- Target: `{raw['target_dir']}`")
        lines.append(f"- Manifest: `{raw['manifest']}`")
        lines.append(f"- README: `{raw['readme']}`")
    else:
        lines.append(f"- Ingested: false ({raw.get('reason', 'unknown')})")
        lines.append(f"- Source dir checked: `{raw.get('source_dir', '')}`")

    lines.extend(["", "## Source Refs", ""])
    for item in report["source_refs"]:
        lines.append(
            f"- `{item['card']}` -> `{item['source_ref']}` | exists={item['exists']}"
        )

    md_path = canonical_root / REPORT_MD
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "json": REPORT_JSON.as_posix(),
        "markdown": REPORT_MD.as_posix(),
        "log": REPORT_LOG.as_posix(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Brain Router v1 reports for OpenClaw Ops domain.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--ingest-source", default="/home/agente/SISTEM PROMPTS DE CLAUDE PARA INVERSE ENGINEERING")
    args = parser.parse_args()

    canonical_root = get_canonical_root(args.root)
    raw_ingest = _ingest_raw_source(canonical_root, Path(args.ingest_source))
    report = build_report(canonical_root, raw_ingest)
    paths = write_report(canonical_root, report)
    print(json.dumps({"paths": paths, "summary": report["summary"], "raw_ingest": raw_ingest}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
