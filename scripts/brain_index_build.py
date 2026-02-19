#!/usr/bin/env python3
"""Deterministic Brain Graph index builder."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Set, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.repo_root import TOPLEVEL_ALLOWLIST, get_canonical_root
from scripts.workspace_hygiene_policy import assert_policy_root, is_ignored_relpath, load_policy

MD_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
SECTION_TAGS_RE = re.compile(r"^\s*tags\s*:\s*(.*)$", re.IGNORECASE)


DEFAULT_EXCLUDE_PREFIXES = (
    "vault/_quarantine",
    "vault/_salvage",
    "__pycache__",
    ".git",
)


def _split_tag_values(raw: str) -> List[str]:
    value = raw.strip()
    if not value:
        return []
    if value.startswith("[") and value.endswith("]"):
        value = value[1:-1]
    return [item.strip().strip('"').strip("'") for item in value.split(",") if item.strip()]


def _parse_frontmatter_tags(lines: Sequence[str]) -> Tuple[List[str], int]:
    if not lines or lines[0].strip() != "---":
        return [], 0

    tags: List[str] = []
    i = 1
    while i < len(lines):
        line = lines[i].rstrip("\n")
        if line.strip() == "---":
            return tags, i + 1

        match = SECTION_TAGS_RE.match(line)
        if match:
            inline = match.group(1).strip()
            if inline:
                tags.extend(_split_tag_values(inline))
            j = i + 1
            while j < len(lines):
                bullet = lines[j].strip()
                if bullet.startswith("- "):
                    tags.append(bullet[2:].strip().strip('"').strip("'"))
                    j += 1
                    continue
                break
            i = j
            continue
        i += 1

    return tags, 0


def _parse_section_tags(lines: Sequence[str], start_index: int = 0) -> List[str]:
    tags: List[str] = []
    i = start_index
    while i < len(lines):
        line = lines[i].rstrip("\n")
        match = SECTION_TAGS_RE.match(line)
        if not match:
            i += 1
            continue

        inline = match.group(1).strip()
        if inline:
            tags.extend(_split_tag_values(inline))

        j = i + 1
        while j < len(lines):
            candidate = lines[j].strip()
            if not candidate:
                break
            if candidate.startswith("#"):
                break
            if candidate.startswith("- "):
                tags.append(candidate[2:].strip().strip('"').strip("'"))
                j += 1
                continue
            break
        i = j

    return tags


def _parse_deep_links(text: str) -> List[str]:
    links: Set[str] = set()
    for match in MD_LINK_RE.finditer(text):
        link = match.group(1).strip()
        if not link:
            continue
        if link.startswith("#"):
            continue
        if "://" in link:
            continue
        links.add(link)
    return sorted(links)


def _normalize_tags(tags: Sequence[str]) -> List[str]:
    normalized = {tag.strip() for tag in tags if tag and tag.strip()}
    return sorted(normalized)


def _load_nested_copy_excludes(root: Path) -> Set[str]:
    report_path = root / "docs" / "_inbox" / "repo_reality_report_latest.json"
    if not report_path.is_file():
        return set()

    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return set()

    excludes: Set[str] = set()
    for item in payload.get("candidates", []):
        rel = str(item.get("path", "")).strip("/")
        if rel:
            disposition = str(item.get("disposition", "pending")).strip().lower()
            if disposition in {"pending", "kept", "quarantined"}:
                excludes.add(rel)
    return excludes


def _load_state_copy_excludes(root: Path) -> Set[str]:
    excludes: Set[str] = set()

    allowlist_path = root / "state" / "repo_reality_allowlist.json"
    if allowlist_path.is_file():
        try:
            payload = json.loads(allowlist_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {}
        kept_paths = payload.get("kept_paths", {})
        if isinstance(kept_paths, dict):
            for rel in kept_paths.values():
                rel_text = str(rel).strip("/")
                if rel_text:
                    excludes.add(rel_text)

    state_path = root / "state" / "repo_reality_state.json"
    if state_path.is_file():
        try:
            payload = json.loads(state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {}
        for move in payload.get("quarantine_moves", []):
            rel = str(move.get("from", "")).strip("/")
            if rel:
                excludes.add(rel)

    return excludes


def _is_excluded(rel_path: str, excluded_prefixes: Set[str]) -> bool:
    rel = rel_path.strip().strip("/")
    if not rel:
        return False

    for prefix in excluded_prefixes:
        clean = prefix.strip().strip("/")
        if rel == clean or rel.startswith(clean + "/"):
            return True
    return False


def _load_policy_excludes(root: Path) -> Set[str]:
    policy = load_policy(root, create_if_missing=False)
    assert_policy_root(root, policy)

    excludes: Set[str] = set()
    for name in policy.get("tooling_dirs", []):
        if not name:
            continue
        excludes.add(str(name).strip("/"))
    for pattern in policy.get("ignore_globs", []):
        clean = str(pattern).strip().strip("/")
        if not clean:
            continue
        if clean.endswith("/**"):
            clean = clean[: -len("/**")]
        excludes.add(clean)
    return excludes


def _iter_markdown_paths(root: Path, namespace: str) -> Iterable[Path]:
    namespace_top = namespace.split("/", 1)[0]
    if namespace_top not in TOPLEVEL_ALLOWLIST:
        raise ValueError(f"Namespace '{namespace}' is outside allowlist: {sorted(TOPLEVEL_ALLOWLIST)}")

    namespace_dir = root / namespace
    if not namespace_dir.exists():
        return []

    policy = load_policy(root, create_if_missing=False)
    assert_policy_root(root, policy)
    policy_tooling = set(policy.get("tooling_dirs", []))

    excluded_prefixes = set(DEFAULT_EXCLUDE_PREFIXES)
    excluded_prefixes.update(_load_nested_copy_excludes(root))
    excluded_prefixes.update(_load_state_copy_excludes(root))
    excluded_prefixes.update(_load_policy_excludes(root))

    collected: List[Path] = []
    for dirpath, dirnames, filenames in os.walk(namespace_dir, topdown=True, followlinks=False):
        current = Path(dirpath)
        rel_current = current.resolve().relative_to(root.resolve()).as_posix()

        pruned: List[str] = []
        for dirname in sorted(dirnames):
            child = current / dirname
            child_rel = child.resolve().relative_to(root.resolve()).as_posix()
            if dirname in policy_tooling:
                continue
            if _is_excluded(child_rel, excluded_prefixes) or is_ignored_relpath(child_rel, policy):
                continue
            pruned.append(dirname)
        dirnames[:] = pruned

        if _is_excluded(rel_current, excluded_prefixes) or is_ignored_relpath(rel_current, policy):
            continue

        for filename in sorted(filenames):
            if not filename.endswith(".md"):
                continue
            path = current / filename
            rel_path = path.resolve().relative_to(root.resolve()).as_posix()
            if any(part in policy_tooling for part in Path(rel_path).parts):
                continue
            if _is_excluded(rel_path, excluded_prefixes) or is_ignored_relpath(rel_path, policy):
                continue
            collected.append(path)

    return sorted(collected, key=lambda p: p.as_posix())


def build_registry(root: Path, namespace: str = "brain") -> Dict[str, Any]:
    namespace_dir = root / namespace
    nodes: List[Dict[str, Any]] = []

    if not namespace_dir.exists():
        return {
            "namespace": namespace,
            "node_count": 0,
            "nodes": [],
            "registry_version": 1,
        }

    for md_path in _iter_markdown_paths(root=root, namespace=namespace):
        text = md_path.read_text(encoding="utf-8")
        lines = text.splitlines(keepends=True)
        frontmatter_tags, body_start = _parse_frontmatter_tags(lines)
        body_tags = _parse_section_tags(lines, start_index=body_start)
        tags = _normalize_tags([*frontmatter_tags, *body_tags])
        deep_links = _parse_deep_links(text)

        nodes.append(
            {
                "path": md_path.resolve().relative_to(root.resolve()).as_posix(),
                "tags": tags,
                "deep_links": deep_links,
            }
        )

    return {
        "namespace": namespace,
        "node_count": len(nodes),
        "nodes": nodes,
        "registry_version": 1,
    }


def _is_state_versioned(root: Path) -> bool:
    git_dir = root / ".git"
    if not git_dir.exists():
        return False

    try:
        result = subprocess.run(
            ["git", "-C", str(root), "ls-files", "state"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return False

    return result.returncode == 0 and bool(result.stdout.strip())


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def write_outputs(root: Path, registry: Dict[str, Any]) -> List[Path]:
    outputs: List[Path] = []

    if _is_state_versioned(root):
        registry_path = root / "state" / "brain_registry.json"
        _write_json(registry_path, registry)
        outputs.append(registry_path)
        return outputs

    registry_path = root / "docs" / "_inbox" / "brain_registry_latest.json"
    _write_json(registry_path, registry)
    outputs.append(registry_path)

    log_path = root / "logs" / "brain_index_build_latest.json"
    log_payload = {
        "namespace": registry["namespace"],
        "node_count": registry["node_count"],
        "output": registry_path.relative_to(root).as_posix(),
        "registry_version": registry["registry_version"],
    }
    _write_json(log_path, log_payload)
    outputs.append(log_path)

    return outputs


def main() -> int:
    parser = argparse.ArgumentParser(description="Build deterministic Brain Graph registry")
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument("--namespace", default="brain", help="Brain namespace directory")
    args = parser.parse_args()

    canonical_root = get_canonical_root(args.root)
    registry = build_registry(root=canonical_root, namespace=args.namespace)
    output_paths = write_outputs(root=canonical_root, registry=registry)

    for output in output_paths:
        print(output.relative_to(canonical_root).as_posix())

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
