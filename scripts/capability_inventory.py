#!/usr/bin/env python3
"""Build a deterministic capability inventory from canonical repo sources."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.repo_root import get_canonical_root

STATE_PATH = Path("state/capability_inventory.json")
REPORT_JSON = Path("docs/_inbox/capability_inventory_latest.json")
REPORT_MD = Path("docs/_inbox/capability_inventory_latest.md")
REPORT_LOG = Path("logs/capability_inventory_latest.json")

MAX_SNIPPET_LINES = 60
MAX_SNIPPET_CHARS = 3000
MAX_FLAG_LINES = 200

KEYWORDS = (
    "skill",
    "plugin",
    "feature",
    "hook",
    "router",
    "doctor",
    "policy",
    "ingest",
    "memory",
    "outbox",
    "runtime",
    "openclaw",
    "approval",
    "session",
    "heartbeat",
    "safety",
)

TARGET_GROUPS: Sequence[Dict[str, Any]] = (
    {"area": "scripts", "patterns": ["scripts/*.py"]},
    {"area": "hooks", "patterns": ["hooks/**/*.js", "hooks/**/*.ts", "hooks/**/*.md"]},
    {"area": "brain", "patterns": ["brain/**/*.md"]},
    {"area": "memory", "patterns": ["memory/**/*"]},
    {"area": "state", "patterns": ["state/*.json"]},
    {
        "area": "context_docs",
        "patterns": [
            "AGENTS.md",
            "CLAUDE.md",
            "SOUL.md",
            "PROJECT_BRIEF.md",
            "REPO_MAP.md",
            "repo_map/**/*.md",
        ],
    },
    {"area": "tests", "patterns": ["tests/**/*.py"]},
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _save_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_text(path: Path, limit_chars: int = 120_000) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = path.read_text(encoding="utf-8", errors="ignore")
    return text[:limit_chars]


def _snippet(text: str) -> str:
    lines = text.splitlines()[:MAX_SNIPPET_LINES]
    compact = "\n".join(lines).strip()
    if len(compact) > MAX_SNIPPET_CHARS:
        return compact[: MAX_SNIPPET_CHARS - 1] + "…"
    return compact


def _detect_cli_flags(path: Path, text: str) -> List[str]:
    if path.suffix != ".py":
        return []
    lines = text.splitlines()[:MAX_FLAG_LINES]
    sample = "\n".join(lines)
    flags = set(re.findall(r"--[a-zA-Z0-9][a-zA-Z0-9_-]*", sample))
    return sorted(flags)


def _extract_keywords(rel_path: str, text: str) -> List[str]:
    haystack = f"{rel_path}\n{text[:2000]}".lower()
    found = [keyword for keyword in KEYWORDS if keyword in haystack]
    return sorted(set(found))


def _collect_files(root: Path) -> Dict[str, List[Path]]:
    out: Dict[str, List[Path]] = {}
    for group in TARGET_GROUPS:
        area = str(group["area"])
        selected: set[Path] = set()
        for pattern in group["patterns"]:
            for candidate in root.glob(str(pattern)):
                if not candidate.is_file():
                    continue
                selected.add(candidate.resolve())
        out[area] = sorted(selected, key=lambda p: p.as_posix())
    return out


def _kind_for(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".py", ".js", ".ts", ".sh", ".ps1"}:
        return "code"
    if suffix in {".md", ".txt"}:
        return "doc"
    if suffix in {".json", ".ndjson", ".yaml", ".yml", ".toml", ".ini", ".cfg"}:
        return "config_or_data"
    if suffix in {".pdf", ".html"}:
        return "document_blob"
    return "other"


def build_inventory(root: str | Path) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    grouped = _collect_files(canonical_root)

    items: List[Dict[str, Any]] = []
    for area, files in sorted(grouped.items()):
        for path in files:
            rel = path.resolve().relative_to(canonical_root.resolve()).as_posix()
            stat = path.stat()
            text = _read_text(path) if path.suffix.lower() in {".py", ".md", ".txt", ".json", ".ndjson", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".js", ".ts"} else ""
            snippet = _snippet(text) if text else ""
            cli_flags = _detect_cli_flags(path, text)
            keywords = _extract_keywords(rel, text if text else path.name)
            sha256 = _sha256_file(path)
            signature_seed = "|".join(
                [
                    area,
                    path.name.lower(),
                    ",".join(keywords),
                    ",".join(cli_flags),
                    _snippet(text[:1200]) if text else "",
                ]
            )
            feature_signature = hashlib.sha1(signature_seed.encode("utf-8")).hexdigest()[:16]
            items.append(
                {
                    "area": area,
                    "path": rel,
                    "basename": path.name,
                    "kind": _kind_for(path),
                    "size": stat.st_size,
                    "mtime": stat.st_mtime,
                    "sha256": sha256,
                    "keywords": keywords,
                    "cli_flags": cli_flags,
                    "feature_signature": feature_signature,
                    "snippet": snippet,
                }
            )

    items.sort(key=lambda item: item["path"])

    summary = {
        "items_count": len(items),
        "areas": {area: len(files) for area, files in sorted(grouped.items())},
        "kinds": {},
        "keyword_hits": {},
    }
    kinds: Dict[str, int] = {}
    keyword_hits: Dict[str, int] = {}
    for item in items:
        kinds[item["kind"]] = kinds.get(item["kind"], 0) + 1
        for keyword in item["keywords"]:
            keyword_hits[keyword] = keyword_hits.get(keyword, 0) + 1
    summary["kinds"] = dict(sorted(kinds.items()))
    summary["keyword_hits"] = dict(sorted(keyword_hits.items(), key=lambda kv: (-kv[1], kv[0]))[:30])

    return {
        "canonical_root": str(canonical_root.resolve()),
        "created_at": _utc_now(),
        "summary": summary,
        "items": items,
        "version": 1,
    }


def _write_reports(root: str | Path, report: Dict[str, Any]) -> Dict[str, str]:
    canonical_root = get_canonical_root(root)
    _save_json(canonical_root / STATE_PATH, report)
    _save_json(canonical_root / REPORT_JSON, report)
    _save_json(canonical_root / REPORT_LOG, report)

    lines = [
        "# Capability Inventory",
        "",
        f"- Canonical root: `{report['canonical_root']}`",
        f"- Items: {report['summary']['items_count']}",
        f"- Areas: `{json.dumps(report['summary']['areas'], sort_keys=True, ensure_ascii=False)}`",
        f"- Kinds: `{json.dumps(report['summary']['kinds'], sort_keys=True, ensure_ascii=False)}`",
        f"- JSON report: `{REPORT_JSON.as_posix()}`",
        f"- Log report: `{REPORT_LOG.as_posix()}`",
        "",
        "## Top Keyword Hits",
        "",
    ]
    keyword_hits = report["summary"].get("keyword_hits", {})
    if not keyword_hits:
        lines.append("- none")
    else:
        for key, value in keyword_hits.items():
            lines.append(f"- `{key}`: {value}")

    lines.extend(["", "## Sample Items", ""])
    for item in report["items"][:40]:
        lines.append(
            f"- `{item['path']}` | area={item['area']} | kind={item['kind']} | keywords={','.join(item['keywords']) or '-'}"
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
    report = build_inventory(root)
    paths = _write_reports(root, report)
    return {"report": report, "paths": paths}


def main() -> int:
    parser = argparse.ArgumentParser(description="Build deterministic capability inventory.")
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
            },
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
