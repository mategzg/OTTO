#!/usr/bin/env python3
"""Deterministic release audit gate for SPEC-003 M0."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.repo_root import get_canonical_root

REQUIRED_ARTIFACTS: List[str] = [
    "state/skills_registry.json",
    "state/recipes_registry.json",
    "state/golden_set_spec002.json",
]

CRITICAL_TESTS: List[str] = [
    "tests/test_skill_recipe_registry.py",
    "tests/test_nl_skill_router.py",
    "tests/test_golden_regression_runner.py",
    "tests/test_release_audit.py",
]

REPORT_JSON = Path("docs/_inbox/release_audit_latest.json")
REPORT_MD = Path("docs/_inbox/release_audit_latest.md")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _save_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _tail_lines(text: str, *, limit: int = 80) -> List[str]:
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    if len(lines) <= limit:
        return lines
    return lines[-limit:]


def _git_clean_check(root: Path) -> Dict[str, Any]:
    cmd = ["git", "-C", str(root), "status", "--porcelain"]
    try:
        proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    except OSError as exc:
        return {
            "checked": False,
            "clean": False,
            "command": cmd,
            "exit_code": None,
            "error": f"git unavailable: {exc}",
            "dirty_entries": [],
        }

    all_dirty_entries = sorted(line.rstrip() for line in proc.stdout.splitlines() if line.strip())
    dirty_entries = all_dirty_entries[:200]
    return {
        "checked": proc.returncode == 0,
        "clean": proc.returncode == 0 and not dirty_entries,
        "command": cmd,
        "exit_code": proc.returncode,
        "error": "" if proc.returncode == 0 else _tail_lines(proc.stderr, limit=1)[0] if proc.stderr.strip() else "git status failed",
        "dirty_entries": dirty_entries,
        "dirty_count_total": len(all_dirty_entries),
        "dirty_truncated": len(all_dirty_entries) > len(dirty_entries),
    }


def _artifact_check(root: Path) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    missing: List[str] = []
    for rel in REQUIRED_ARTIFACTS:
        exists = (root / rel).is_file()
        rows.append({"path": rel, "exists": exists})
        if not exists:
            missing.append(rel)
    return {
        "required": rows,
        "missing": sorted(missing),
        "all_present": not missing,
    }


def _run_critical_tests(root: Path, tests: Sequence[str]) -> Dict[str, Any]:
    cmd = ["pytest", "-q", *tests]
    try:
        proc = subprocess.run(cmd, cwd=root, check=False, capture_output=True, text=True)
    except OSError as exc:
        return {
            "passed": False,
            "command": cmd,
            "exit_code": None,
            "error": f"pytest execution failed: {exc}",
            "stdout_tail": [],
            "stderr_tail": [],
            "tests": list(tests),
        }

    return {
        "passed": proc.returncode == 0,
        "command": cmd,
        "exit_code": proc.returncode,
        "error": "",
        "stdout_tail": _tail_lines(proc.stdout),
        "stderr_tail": _tail_lines(proc.stderr),
        "tests": list(tests),
    }


def _write_markdown(root: Path, report: Dict[str, Any]) -> None:
    git_check = report["checks"]["repo_clean"]
    artifacts = report["checks"]["required_artifacts"]
    tests = report["checks"]["critical_tests"]

    lines: List[str] = [
        "# Release Audit",
        "",
        f"- Canonical root: `{report['canonical_root']}`",
        f"- Created at: `{report['created_at']}`",
        f"- Status: `{report['status']}`",
        f"- Go/No-Go: `{report['go_no_go']}`",
        "",
        "## Gate Results",
        "",
        f"- Repo clean: `{git_check['clean']}`",
        f"- Required artifacts present: `{artifacts['all_present']}`",
        f"- Critical tests passed: `{tests['passed']}`",
        "",
        "## Required Artifacts",
        "",
    ]

    for row in artifacts["required"]:
        lines.append(f"- `{row['path']}`: `{'present' if row['exists'] else 'missing'}`")

    lines.extend(["", "## Dirty Entries", ""])
    if git_check["dirty_entries"]:
        lines.append(f"- Total dirty entries: `{git_check.get('dirty_count_total', len(git_check['dirty_entries']))}`")
        if git_check.get("dirty_truncated"):
            lines.append("- Showing first 200 sorted entries.")
        for entry in git_check["dirty_entries"]:
            lines.append(f"- `{entry}`")
    else:
        lines.append("- None")

    lines.extend(["", "## Critical Test Command", ""])
    lines.append(f"- Command: `{' '.join(tests['command'])}`")
    lines.append(f"- Exit code: `{tests['exit_code']}`")

    lines.extend(["", "## Failures", ""])
    if report["failures"]:
        for failure in report["failures"]:
            lines.append(f"- `{failure}`")
    else:
        lines.append("- None")

    (root / REPORT_MD).parent.mkdir(parents=True, exist_ok=True)
    (root / REPORT_MD).write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_release_audit(root: str | Path, *, critical_tests: Sequence[str] | None = None) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    tests = list(critical_tests) if critical_tests is not None else list(CRITICAL_TESTS)

    git_check = _git_clean_check(canonical_root)
    artifacts = _artifact_check(canonical_root)
    tests_result = _run_critical_tests(canonical_root, tests)

    failures: List[str] = []
    if not git_check.get("clean", False):
        failures.append("dirty_repo")
    if not artifacts.get("all_present", False):
        failures.append("missing_artifacts")
    if not tests_result.get("passed", False):
        failures.append("critical_tests_failed")

    report = {
        "version": 1,
        "canonical_root": str(canonical_root.resolve()),
        "created_at": _utc_now(),
        "status": "ok" if not failures else "fail",
        "go_no_go": "go" if not failures else "no_go",
        "checks": {
            "repo_clean": git_check,
            "required_artifacts": artifacts,
            "critical_tests": tests_result,
        },
        "failures": failures,
        "run_context": {
            "paths": {
                "json": REPORT_JSON.as_posix(),
                "markdown": REPORT_MD.as_posix(),
            }
        },
    }

    _save_json(canonical_root / REPORT_JSON, report)
    _write_markdown(canonical_root, report)

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run deterministic release audit gate")
    parser.add_argument("--root", default=".")
    parser.add_argument(
        "--critical-test",
        action="append",
        dest="critical_tests",
        default=None,
        help="Override critical pytest paths (can be passed multiple times)",
    )
    args = parser.parse_args()

    report = run_release_audit(args.root, critical_tests=args.critical_tests)
    print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if report.get("status") == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
