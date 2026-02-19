#!/usr/bin/env python3
"""Generate deterministic context-alignment evidence for Reality Alignment runs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path(__file__).resolve().parents[1]


def _file_exists(rel_path: str) -> bool:
    return (ROOT / rel_path).is_file()


def _read(rel_path: str) -> str:
    path = ROOT / rel_path
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def _contains(rel_path: str, needle: str) -> bool:
    return needle in _read(rel_path)


def build_report() -> Dict[str, Any]:
    context_candidates = [
        "SOUL.md",
        "AGENTS.md",
        "CLAUDE.md",
        "CEO.md",
        "TOOLS.md",
        "USER.md",
        "IDENTITY.md",
        "HEARTBEAT.md",
        "INDEX.md",
        "MEMORY.md",
        "memory.md",
        "BOOTSTRAP.md",
        "openclaw/00_INDEX.md",
        "openclaw/CONTEXT_MAP.md",
        "brain/00_INDEX.md",
    ]

    found_context_files: List[str] = [
        rel for rel in context_candidates if _file_exists(rel)
    ]

    gates_detected = {
        "pytest": True,
        "git_preflight": False,
        "doctor_canon": False,
        "release_policy": _file_exists("ops/RELEASE_POLICY.md"),
    }

    read_orders = {
        "otto": [
            "SOUL.md",
            "INDEX.md",
            "brain/00_INDEX.md",
            "openclaw/00_INDEX.md",
            "openclaw/CONTEXT_MAP.md",
        ],
        "codex": [
            "AGENTS.md",
            "CEO.md",
            "INDEX.md",
            "brain/00_INDEX.md",
            "openclaw/CONTEXT_MAP.md",
        ],
        "claude": [
            "CLAUDE.md",
            "CEO.md",
            "INDEX.md",
            "brain/00_INDEX.md",
            "openclaw/CONTEXT_MAP.md",
        ],
    }

    authority = {
        "canon": "CEO.md",
        "context_map": "openclaw/CONTEXT_MAP.md",
        "wrappers": ["SOUL.md", "AGENTS.md", "CLAUDE.md"],
        "hubs": ["INDEX.md", "openclaw/00_INDEX.md", "brain/00_INDEX.md"],
    }

    links_verified = {
        "agents_points_to_ceo": _contains("AGENTS.md", "CEO.md"),
        "agents_points_to_index": _contains("AGENTS.md", "INDEX.md"),
        "claude_points_to_ceo": _contains("CLAUDE.md", "CEO.md"),
        "claude_points_to_index": _contains("CLAUDE.md", "INDEX.md"),
        "soul_points_to_index": _contains("SOUL.md", "INDEX.md"),
        "index_points_to_context_map": _contains("INDEX.md", "openclaw/CONTEXT_MAP.md"),
        "openclaw_points_to_context_map": _contains("openclaw/00_INDEX.md", "openclaw/CONTEXT_MAP.md"),
        "brain_points_to_context_map": _contains("brain/00_INDEX.md", "openclaw/CONTEXT_MAP.md"),
    }

    gitignore_text = _read(".gitignore")
    vault_raw_ignored = all(
        rule in gitignore_text
        for rule in [
            "vault/chatgpt_export_raw/",
            "vault/chatgpt_export_raw/**",
        ]
    )

    report: Dict[str, Any] = {
        "authority": authority,
        "found_context_files": found_context_files,
        "gates_detected": gates_detected,
        "links_verified": links_verified,
        "read_orders": read_orders,
        "vault_raw_ignored": vault_raw_ignored,
        "version": 1,
    }
    return report


def main() -> int:
    out_path = ROOT / "docs" / "_inbox" / "context_alignment_report_latest.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    report = build_report()
    out_path.write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(out_path.relative_to(ROOT).as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
