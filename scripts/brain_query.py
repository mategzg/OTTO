#!/usr/bin/env python3
"""Query Brain registry for relevant markdown nodes."""

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

from scripts.repo_root import get_canonical_root
from scripts.brain_index_build import build_registry

TOKEN_RE = re.compile(r"[a-z0-9_]+")
STATE_REGISTRY = Path("state/brain_registry.json")
INBOX_REGISTRY = Path("docs/_inbox/brain_registry_latest.json")


def _tokenize(text: str) -> List[str]:
    return [t for t in TOKEN_RE.findall(text.lower()) if len(t) > 2]


def _load_registry(root: Path, namespace: str = "brain") -> Dict[str, Any]:
    for rel in (STATE_REGISTRY, INBOX_REGISTRY):
        path = root / rel
        if path.is_file():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                return payload
    return build_registry(root=root, namespace=namespace)


def _score_node(node: Dict[str, Any], tokens: Sequence[str]) -> int:
    basis = " ".join(
        [
            str(node.get("path", "")),
            str(node.get("title", "")),
            " ".join(node.get("tags", []) if isinstance(node.get("tags"), list) else []),
        ]
    ).lower()
    overlap = len({tok for tok in tokens if tok in basis})
    score = overlap * 10
    if str(node.get("path", "")).startswith("brain/domains/"):
        score += 2
    return score


def run_brain_query(root: str | Path, *, question: str, k: int = 6, namespace: str = "brain") -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    registry = _load_registry(canonical_root, namespace=namespace)
    tokens = sorted(set(_tokenize(question)))

    nodes = registry.get("nodes", []) if isinstance(registry.get("nodes"), list) else []
    scored: List[tuple[int, Dict[str, Any]]] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        score = _score_node(node, tokens)
        if tokens and score <= 0:
            continue
        scored.append((score, node))

    scored.sort(key=lambda item: item[0], reverse=True)
    top = [
        {
            "path": str(node.get("path", "")),
            "title": str(node.get("title", "")),
            "tags": node.get("tags", []),
            "score": score,
        }
        for score, node in scored[: max(1, k)]
    ]

    return {
        "canonical_root": str(canonical_root.resolve()),
        "question": question,
        "tokens": tokens,
        "result_count": len(top),
        "results": top,
        "version": 1,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Query Brain registry")
    parser.add_argument("--root", default=".")
    parser.add_argument("--q", required=True)
    parser.add_argument("--k", type=int, default=6)
    parser.add_argument("--namespace", default="brain")
    args = parser.parse_args()

    out = run_brain_query(args.root, question=args.q, k=max(1, args.k), namespace=args.namespace)
    print(json.dumps(out, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
