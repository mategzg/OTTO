#!/usr/bin/env python3
from __future__ import annotations

from typing import Any, Dict, List


def _citation_from_chunk(chunk: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "doc_id": str(chunk.get("doc_id", "")),
        "doc_version": str(chunk.get("doc_version", "")),
        "path": str(chunk.get("path", "")),
        "section_path": str(chunk.get("section_path", "")),
        "locator": chunk.get("locator", {}),
        "content_hash": str(chunk.get("content_hash", "")),
    }


def build_and_validate(
    *,
    mode: str,
    answer: str,
    retrieval_pack: Dict[str, Any] | None,
    confidence: str = "low",
    actions_taken: List[str] | None = None,
) -> Dict[str, Any]:
    pack = retrieval_pack or {}
    topk = pack.get("final_topk", []) if isinstance(pack.get("final_topk", []), list) else []
    citations = [_citation_from_chunk(c) for c in topk]
    gaps: List[str] = []
    actions_taken = actions_taken or []

    diag = pack.get("diagnostics", {}) if isinstance(pack.get("diagnostics"), dict) else {}
    abstention_hint = bool(diag.get("abstention_hint", False))

    enforced_mode = mode
    if mode not in {"grounded_answer", "action", "exploration", "chat_normal"}:
        enforced_mode = "chat_normal"

    if enforced_mode == "grounded_answer":
        if not citations or abstention_hint:
            gaps.append("No hay evidencia suficiente en retrieval para responder con certeza.")
            return {
                "valid": False,
                "output": {
                    "mode": "grounded_answer",
                    "answer": "NO_VERIFICADO",
                    "citations": citations,
                    "gaps": gaps,
                    "confidence": "low",
                    "actions_taken": actions_taken,
                },
                "reason": "missing_or_weak_evidence",
            }

    return {
        "valid": True,
        "output": {
            "mode": enforced_mode,
            "answer": answer,
            "citations": citations,
            "gaps": gaps,
            "confidence": confidence,
            "actions_taken": actions_taken,
        },
        "reason": "ok",
    }
