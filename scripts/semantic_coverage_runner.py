#!/usr/bin/env python3
"""Semantic coverage runner (M7): chunk docs, apply synonyms, evaluate representative queries."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.repo_root import get_canonical_root

POLICY_PATH = Path("state/semantic_coverage_policy.json")
REPORT_JSON = Path("docs/_inbox/semantic_coverage_latest.json")
REPORT_MD = Path("docs/_inbox/semantic_coverage_latest.md")

TOKEN_RE = re.compile(r"[a-z0-9_áéíóúñ]+", re.IGNORECASE)
HEADING_RE = re.compile(r"^#{1,6}\s+(.+)$")


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


def _tokenize(text: str) -> List[str]:
    return [t.lower() for t in TOKEN_RE.findall(text or "") if len(t) > 2]


def _expand_tokens(tokens: List[str], synonyms: Dict[str, List[str]]) -> List[str]:
    expanded = set(tokens)
    reverse: Dict[str, str] = {}
    for base, syns in synonyms.items():
        base_l = str(base).lower()
        reverse[base_l] = base_l
        for s in syns:
            reverse[str(s).lower()] = base_l
    for t in list(expanded):
        if t in synonyms:
            expanded.update([str(x).lower() for x in synonyms.get(t, [])])
        if t in reverse:
            expanded.add(reverse[t])
            expanded.update([str(x).lower() for x in synonyms.get(reverse[t], [])])
    return sorted(expanded)


def _chunks_from_md(rel_path: str, text: str) -> List[Dict[str, Any]]:
    lines = text.splitlines()
    chunks: List[Dict[str, Any]] = []
    current_title = ""
    buffer: List[str] = []
    start_line = 1

    def flush(end_line: int) -> None:
        nonlocal buffer, current_title, start_line
        body = "\n".join(buffer).strip()
        if not body:
            return
        chunks.append(
            {
                "path": rel_path,
                "title": current_title or "(no_heading)",
                "start_line": start_line,
                "end_line": end_line,
                "text": body,
                "tokens": _tokenize((current_title + "\n" + body).strip()),
            }
        )

    for idx, line in enumerate(lines, start=1):
        m = HEADING_RE.match(line.strip())
        if m:
            flush(idx - 1)
            current_title = m.group(1).strip()
            buffer = []
            start_line = idx
        else:
            buffer.append(line)
    flush(len(lines))
    return chunks


def run_semantic_coverage(root: str | Path) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    policy = _load_json(canonical_root / POLICY_PATH)
    domains = policy.get("domains", {}) if isinstance(policy.get("domains"), dict) else {}

    domain_reports: Dict[str, Any] = {}

    for domain, cfg in domains.items():
        paths = [str(p) for p in cfg.get("paths", [])]
        synonyms = {str(k).lower(): [str(x).lower() for x in v] for k, v in (cfg.get("synonyms", {}) or {}).items()}
        queries = [str(q) for q in cfg.get("representative_queries", [])]

        chunks: List[Dict[str, Any]] = []
        for rel in paths:
            base = canonical_root / rel
            if not base.exists():
                continue
            for path in base.rglob("*.md"):
                rel_path = path.relative_to(canonical_root).as_posix()
                text = path.read_text(encoding="utf-8", errors="replace")
                chunks.extend(_chunks_from_md(rel_path, text))

        query_results: List[Dict[str, Any]] = []
        for q in queries:
            qt = _expand_tokens(_tokenize(q), synonyms)
            scored: List[Tuple[int, Dict[str, Any]]] = []
            for c in chunks:
                overlap = len(set(qt).intersection(set(c.get("tokens", []))))
                if overlap > 0:
                    scored.append((overlap, c))
            scored.sort(key=lambda x: (-x[0], x[1].get("path", "")))
            top = [
                {
                    "score": s,
                    "path": c.get("path", ""),
                    "title": c.get("title", ""),
                    "start_line": c.get("start_line", 0),
                }
                for s, c in scored[:3]
            ]
            query_results.append({"query": q, "hits": len(scored), "top_matches": top})

        covered = sum(1 for r in query_results if int(r.get("hits", 0)) > 0)
        domain_reports[domain] = {
            "chunks_count": len(chunks),
            "queries_total": len(query_results),
            "queries_with_hits": covered,
            "recall_proxy": round(covered / max(1, len(query_results)), 4),
            "query_results": query_results,
            "synonyms_count": len(synonyms),
        }

    overall_queries = sum(int(v.get("queries_total", 0)) for v in domain_reports.values())
    overall_hits = sum(int(v.get("queries_with_hits", 0)) for v in domain_reports.values())
    report = {
        "created_at": _utc_now(),
        "status": "ok" if overall_hits == overall_queries else "needs_improvement",
        "summary": {
            "domains": sorted(domain_reports.keys()),
            "queries_total": overall_queries,
            "queries_with_hits": overall_hits,
            "recall_proxy": round(overall_hits / max(1, overall_queries), 4),
        },
        "domains": domain_reports,
        "version": 1,
    }

    _save_json(canonical_root / REPORT_JSON, report)
    lines = [
        "# Semantic Coverage Report",
        "",
        f"- Status: `{report['status']}`",
        f"- Queries total: `{report['summary']['queries_total']}`",
        f"- Queries with hits: `{report['summary']['queries_with_hits']}`",
        f"- Recall proxy: `{report['summary']['recall_proxy']}`",
    ]
    (canonical_root / REPORT_MD).parent.mkdir(parents=True, exist_ok=True)
    (canonical_root / REPORT_MD).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run semantic coverage evaluation")
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    out = run_semantic_coverage(args.root)
    print(json.dumps({"status": out.get("status"), "summary": out.get("summary", {})}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
