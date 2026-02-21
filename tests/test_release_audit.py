import json
import subprocess
from pathlib import Path

from scripts.release_audit import REPORT_JSON, REPORT_MD, REQUIRED_ARTIFACTS, run_release_audit


def _git(cmd: list[str], cwd: Path) -> None:
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True)


def _init_git_repo(root: Path) -> None:
    _git(["git", "init"], root)
    _git(["git", "config", "user.email", "audit@test.local"], root)
    _git(["git", "config", "user.name", "Audit Test"], root)


def _write_required_artifacts(root: Path, *, missing: set[str] | None = None) -> None:
    missing = missing or set()
    for rel in REQUIRED_ARTIFACTS:
        if rel in missing:
            continue
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}\n", encoding="utf-8")


def _seed_repo(root: Path, *, missing_artifacts: set[str] | None = None) -> None:
    (root / "docs" / "_inbox").mkdir(parents=True, exist_ok=True)
    (root / "tracked.txt").write_text("baseline\n", encoding="utf-8")
    _write_required_artifacts(root, missing=missing_artifacts)
    _init_git_repo(root)
    _git(["git", "add", "."], root)
    _git(["git", "commit", "-m", "seed"], root)


def _passing_tests(_root: Path, tests: list[str]) -> dict:
    return {
        "passed": True,
        "command": ["python3", "-m", "pytest", "-q", *tests],
        "exit_code": 0,
        "error": "",
        "stdout_tail": ["all tests passed"],
        "stderr_tail": [],
        "tests": tests,
    }


def test_release_audit_fails_when_repo_dirty(tmp_path: Path, monkeypatch):
    _seed_repo(tmp_path)
    (tmp_path / "tracked.txt").write_text("changed\n", encoding="utf-8")

    import scripts.release_audit as audit

    monkeypatch.setattr(audit, "get_canonical_root", lambda root: Path(root).resolve())
    monkeypatch.setattr(audit, "_run_critical_tests", _passing_tests)

    report = run_release_audit(tmp_path)
    assert report["status"] == "fail"
    assert "dirty_repo" in report["failures"]
    assert report["checks"]["repo_clean"]["clean"] is False
    assert (tmp_path / REPORT_JSON).is_file()
    assert (tmp_path / REPORT_MD).is_file()


def test_release_audit_fails_when_required_artifacts_missing(tmp_path: Path, monkeypatch):
    _seed_repo(tmp_path, missing_artifacts={"state/golden_set_spec002.json"})

    import scripts.release_audit as audit

    monkeypatch.setattr(audit, "get_canonical_root", lambda root: Path(root).resolve())
    monkeypatch.setattr(audit, "_run_critical_tests", _passing_tests)

    report = run_release_audit(tmp_path)
    assert report["status"] == "fail"
    assert "missing_artifacts" in report["failures"]
    missing = report["checks"]["required_artifacts"]["missing"]
    assert "state/golden_set_spec002.json" in missing


def test_release_audit_succeeds_when_clean_artifacts_present_and_tests_pass(tmp_path: Path, monkeypatch):
    _seed_repo(tmp_path)

    import scripts.release_audit as audit

    monkeypatch.setattr(audit, "get_canonical_root", lambda root: Path(root).resolve())
    monkeypatch.setattr(audit, "_run_critical_tests", _passing_tests)

    report = run_release_audit(tmp_path)
    assert report["status"] == "ok"
    assert report["failures"] == []
    stored = json.loads((tmp_path / REPORT_JSON).read_text(encoding="utf-8"))
    assert stored["status"] == "ok"


def test_release_audit_fails_when_critical_tests_fail(tmp_path: Path, monkeypatch):
    _seed_repo(tmp_path)

    import scripts.release_audit as audit

    monkeypatch.setattr(audit, "get_canonical_root", lambda root: Path(root).resolve())

    def _failing_tests(_root: Path, tests: list[str]) -> dict:
        return {
            "passed": False,
            "command": ["python3", "-m", "pytest", "-q", *tests],
            "exit_code": 1,
            "error": "",
            "stdout_tail": ["1 failed"],
            "stderr_tail": [],
            "tests": tests,
        }

    monkeypatch.setattr(audit, "_run_critical_tests", _failing_tests)

    report = run_release_audit(tmp_path)
    assert report["status"] == "fail"
    assert "critical_tests_failed" in report["failures"]
