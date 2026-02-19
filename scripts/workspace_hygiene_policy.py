#!/usr/bin/env python3
"""Workspace hygiene policy helpers."""

from __future__ import annotations

import fnmatch
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

POLICY_PATH = Path("state/workspace_hygiene_policy.json")

DEFAULT_ALLOWLIST_ROOT_DIRS: Sequence[str] = (
    "brain",
    "memory",
    "docs",
    "openclaw",
    "scripts",
    "tests",
    "ops",
    "vault",
    "state",
    "logs",
    "copilots",
    "workers",
    "dashboard",
    "plans",
    "templates",
    "repo_map",
    ".openclaw",
)

DEFAULT_ALLOWLIST_ROOT_FILES: Sequence[str] = (
    ".gitignore",
    "AGENTS.md",
    "BOOT.md",
    "BOOTSTRAP.md",
    "CEO.md",
    "CLAUDE.md",
    "COMMAND_LOGGER.md",
    "HEARTBEAT.md",
    "IDENTITY.md",
    "INDEX.md",
    "PROJECT_BRIEF.md",
    "README.md",
    "REPO_MAP.md",
    "SESSION_MEMORY.md",
    "SOUL.md",
    "TOOLS.md",
    "USER.md",
    "dashboard_server.py",
    "hq_logging.py",
    "index_docs.py",
    "otto_state.py",
    "pytest.ini",
    "requirements.txt",
)

DEFAULT_TOOLING_DIRS: Sequence[str] = (
    ".git",
    ".vscode",
    ".idea",
    ".claude",
    ".codex",
    ".pytest_cache",
    "__pycache__",
    ".venv",
    "node_modules",
    "dist",
    "build",
)

DEFAULT_IGNORE_GLOBS: Sequence[str] = (
    "vault/_quarantine/**",
    "vault/_salvage/**",
    "vault/inbox_raw/**",
    ".git/**",
    "__pycache__/**",
    ".pytest_cache/**",
    ".venv/**",
    "node_modules/**",
    "dist/**",
    "build/**",
)

DEFAULT_SENSITIVE_PATTERNS: Sequence[str] = (
    r"(?i)api[ _-]*key",
    r"(?i)token",
    r"(?i)secret",
    r"(?i)password",
    r"(?i)credential",
    r"(?i)private[ _-]*key",
)

DEFAULT_SENSITIVE_PATH_EXCLUSIONS: Sequence[str] = (
    "tests/**",
)

DEFAULT_HOME_OBVIOUS_PATTERNS: Sequence[str] = (
    r"(?i)^_OLD_BAD_PATH_BACKUP",
    r"(?i)c:\\",
    r"(?i):\\",
    r"(?i)\\users\\",
    r"(?i)quarantine",
    r"(?i)salvage",
)


def _unique_sorted(values: Iterable[str]) -> List[str]:
    return sorted({str(value).strip() for value in values if str(value).strip()})


def build_default_policy(root: Path) -> Dict[str, Any]:
    resolved_root = root.resolve()
    return {
        "version": 1,
        "canonical_root": str(resolved_root),
        "allowlist_root_dirs": list(DEFAULT_ALLOWLIST_ROOT_DIRS),
        "allowlist_root_files": list(DEFAULT_ALLOWLIST_ROOT_FILES),
        "tooling_dirs": list(DEFAULT_TOOLING_DIRS),
        "ignore_globs": list(DEFAULT_IGNORE_GLOBS),
        "sensitive_name_patterns": list(DEFAULT_SENSITIVE_PATTERNS),
        "sensitive_path_exclusions": list(DEFAULT_SENSITIVE_PATH_EXCLUSIONS),
        "obvio_junk_patterns_home": list(DEFAULT_HOME_OBVIOUS_PATTERNS),
    }


def normalize_policy(policy: Dict[str, Any], root: Path) -> Dict[str, Any]:
    normalized = build_default_policy(root)
    normalized.update(policy or {})

    normalized["allowlist_root_dirs"] = _unique_sorted(normalized.get("allowlist_root_dirs", []))
    normalized["allowlist_root_files"] = _unique_sorted(normalized.get("allowlist_root_files", []))
    normalized["tooling_dirs"] = _unique_sorted(normalized.get("tooling_dirs", []))
    normalized["ignore_globs"] = _unique_sorted(normalized.get("ignore_globs", []))
    normalized["sensitive_name_patterns"] = _unique_sorted(normalized.get("sensitive_name_patterns", []))
    normalized["sensitive_path_exclusions"] = _unique_sorted(normalized.get("sensitive_path_exclusions", []))
    normalized["obvio_junk_patterns_home"] = _unique_sorted(normalized.get("obvio_junk_patterns_home", []))
    return normalized


def load_policy(root: Path, *, create_if_missing: bool = False) -> Dict[str, Any]:
    canonical_root = root.resolve()
    path = canonical_root / POLICY_PATH

    payload: Dict[str, Any] = {}
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            loaded = {}
        if isinstance(loaded, dict):
            payload = loaded

    policy = normalize_policy(payload, canonical_root)
    if create_if_missing and not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(policy, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    return policy


def assert_policy_root(canonical_root: Path, policy: Dict[str, Any]) -> None:
    expected = str(policy.get("canonical_root", "")).strip()
    if not expected:
        return
    if Path(expected).resolve() != canonical_root.resolve():
        raise RuntimeError(
            f"Root drift detected: expected canonical root {Path(expected).resolve()} "
            f"but script is running on {canonical_root.resolve()}."
        )


def is_tooling_name(name: str, policy: Dict[str, Any]) -> bool:
    return name in set(policy.get("tooling_dirs", []))


def is_ignored_relpath(rel_path: str, policy: Dict[str, Any]) -> bool:
    rel = rel_path.strip().strip("/")
    if not rel:
        return False
    for pattern in policy.get("ignore_globs", []):
        if fnmatch.fnmatch(rel, pattern):
            return True
    return False


def matches_patterns(value: str, patterns: Sequence[str]) -> bool:
    for pattern in patterns:
        try:
            if re.search(pattern, value):
                return True
        except re.error:
            continue
    return False


def is_sensitive_excluded_relpath(rel_path: str, policy: Dict[str, Any]) -> bool:
    rel = rel_path.strip().strip("/")
    if not rel:
        return False
    for pattern in policy.get("sensitive_path_exclusions", []):
        if fnmatch.fnmatch(rel, pattern):
            return True
    return False
