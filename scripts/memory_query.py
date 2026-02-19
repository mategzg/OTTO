#!/usr/bin/env python3
"""Memory Query v1: fast O(1)-file query with evidence."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Sequence, Set

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.memory_common import get_canonical_root
from scripts.memory_index_build import INDEX_PATH, build_memory_index

LOG_PATH = Path("logs/memory_query_latest.json")
TOKEN_RE = re.compile(r"[a-z0-9_]+")

CONFIDENCE_SCORE = {
    "high": 3,
    "medium": 2,
    "low": 1,
}


def _save_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _tokenize(text: str) -> List[str]:
    return [token for token in TOKEN_RE.findall(text.lower()) if len(token) > 2]


def _load_index(root: Path) -> Dict[str, Any]:
    index_path = root / INDEX_PATH
    if index_path.is_file():
        try:
            payload = json.loads(index_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return payload
        except json.JSONDecodeError:
            pass
    return build_memory_index(root)


def _candidate_ids(index: Dict[str, Any], tokens: Sequence[str]) -> Set[str]:
    inverted = index.get("inverted", {})
    candidates: Set[str] = set()
    for token in tokens:
        for record_id in inverted.get(token, []):
            candidates.add(str(record_id))
    if candidates:
        return candidates
    return set(index.get("records", {}).keys())


def _score_record(record: Dict[str, Any], tokens: Sequence[str]) -> int:
    text = " ".join(
        [
            str(record.get("short_text", "")),
            str(record.get("key", "")),
            " ".join(record.get("tags", []) if isinstance(record.get("tags"), list) else []),
            str(record.get("type", "")),
        ]
    ).lower()
    overlap = len({token for token in tokens if token in text})
    score = overlap * 10
    if bool(record.get("best_known", False)):
        score += 5
    if str(record.get("status", "")) == "active":
        score += 3
    score += CONFIDENCE_SCORE.get(str(record.get("confidence", "medium")).lower(), 1)
    return score


def run_memory_query(
    root: str | Path,
    *,
    question: str,
    k: int = 8,
    types: Sequence[str] | None = None,
    include_superseded: bool = False,
    evidence: bool = True,
    output_format: str = "md",
) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    index = _load_index(canonical_root)

    tokens = sorted(set(_tokenize(question)))
    type_filter = {item.strip() for item in (types or []) if item.strip()}

    candidates = []
    for record_id in sorted(_candidate_ids(index, tokens)):
        record = index.get("records", {}).get(record_id)
        if not isinstance(record, dict):
            continue
        if type_filter and str(record.get("type", "")) not in type_filter:
            continue
        if not include_superseded and str(record.get("status", "")) == "superseded":
            continue
        score = _score_record(record, tokens)
        if score <= 0 and tokens:
            continue
        candidates.append((score, str(record.get("captured_at", "")), record_id, record))

    candidates.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    top = candidates[: max(1, k)]

    results: List[Dict[str, Any]] = []
    for score, _captured, record_id, record in top:
        results.append(
            {
                "id": record_id,
                "type": str(record.get("type", "")),
                "key": str(record.get("key", "")),
                "summary": str(record.get("short_text", "")),
                "status": str(record.get("status", "")),
                "best_known": bool(record.get("best_known", False)),
                "confidence": str(record.get("confidence", "medium")),
                "captured_at": str(record.get("captured_at", "")),
                "source_ref": str(record.get("source_ref", "")),
                "score": score,
            }
        )

    answer_lines = ["## Memory Answer", ""]
    if not results:
        answer_lines.append("- No matching memory records.")
    else:
        for item in results:
            answer_lines.append(
                f"- [{item['type']}] {item['summary']} (best_known={item['best_known']}, confidence={item['confidence']})"
            )

    if evidence:
        answer_lines.extend(["", "## EVIDENCIA", ""])
        if not results:
            answer_lines.append("- None.")
        else:
            for item in results:
                answer_lines.append(f"- `{item['id']}` -> `{item['source_ref']}`")

    response_md = "\n".join(answer_lines) + "\n"

    payload = {
        "canonical_root": str(canonical_root.resolve()),
        "question": question,
        "tokens": tokens,
        "k": k,
        "include_superseded": include_superseded,
        "types": sorted(type_filter),
        "result_count": len(results),
        "results": results,
        "response_md": response_md,
        "version": 1,
    }

    _save_json(canonical_root / LOG_PATH, payload)

    if output_format == "json":
        return payload

    return {
        "markdown": response_md,
        "result_count": len(results),
        "results": results,
        "canonical_root": str(canonical_root.resolve()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Query MemoryOS")
    parser.add_argument("--root", default=".")
    parser.add_argument("--q", required=True)
    parser.add_argument("--k", type=int, default=8)
    parser.add_argument("--types", default="")
    parser.add_argument("--include-superseded", action="store_true")
    parser.add_argument("--evidence", action="store_true", default=True)
    parser.add_argument("--format", choices=["md", "json"], default="md")
    args = parser.parse_args()

    types = [item.strip() for item in args.types.split(",") if item.strip()]
    out = run_memory_query(
        args.root,
        question=args.q,
        k=max(1, args.k),
        types=types,
        include_superseded=args.include_superseded,
        evidence=bool(args.evidence),
        output_format=args.format,
    )

    if args.format == "json":
        print(json.dumps(out, indent=2, sort_keys=True, ensure_ascii=False))
    else:
        print(out["markdown"].rstrip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
