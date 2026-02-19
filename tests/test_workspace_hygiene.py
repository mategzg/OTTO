from pathlib import Path

from scripts import openclaw_hook
from scripts.home_hygiene_doctor import run_home_clean_obvious, run_home_scan
from scripts.repo_root import set_canonical_root
from scripts.workspace_hygiene_doctor import run_workspace_clean, scan_workspace


def _mk_workspace(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "CEO.md").write_text("# CEO\n", encoding="utf-8")
    (root / "INDEX.md").write_text("# INDEX\n", encoding="utf-8")
    (root / "openclaw").mkdir(parents=True, exist_ok=True)
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    (root / "ops").mkdir(parents=True, exist_ok=True)
    (root / "brain").mkdir(parents=True, exist_ok=True)
    (root / "docs").mkdir(parents=True, exist_ok=True)
    (root / "state").mkdir(parents=True, exist_ok=True)
    (root / "vault").mkdir(parents=True, exist_ok=True)
    (root / ".git").mkdir(parents=True, exist_ok=True)


def test_workspace_scan_classifies_junk_and_sensitive(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    workspace = home / "workspace"
    _mk_workspace(workspace)
    monkeypatch.setenv("HOME", str(home))
    set_canonical_root(workspace, created_by="test")

    (workspace / "RANDOM.tmp").write_text("junk", encoding="utf-8")
    (workspace / "API KEY ODOO.txt").write_text("secret", encoding="utf-8")

    report = scan_workspace(workspace)
    by_path = {item["rel_path"]: item for item in report["clean_candidates"]}
    assert by_path["RANDOM.tmp"]["classification"] == "junk"
    assert by_path["API KEY ODOO.txt"]["classification"] == "sensitive"


def test_workspace_clean_moves_sensitive_to_quarantine(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    workspace = home / "workspace"
    _mk_workspace(workspace)
    monkeypatch.setenv("HOME", str(home))
    set_canonical_root(workspace, created_by="test")

    (workspace / "docs" / "API_KEY_LEAK.txt").write_text("leak", encoding="utf-8")
    out = run_workspace_clean(workspace, max_moves=100)
    assert out["status"] == "ok"
    assert out["result"]["moved_count"] >= 1
    assert not (workspace / "docs" / "API_KEY_LEAK.txt").exists()

    secrets_dir = workspace / "vault" / "_quarantine" / "secrets"
    assert secrets_dir.exists()
    assert list(secrets_dir.rglob("MANIFEST.json"))
    assert list(secrets_dir.rglob("README.md"))


def test_home_hygiene_skips_dot_dirs_and_moves_obvious(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    workspace = home / "workspace"
    _mk_workspace(workspace)
    monkeypatch.setenv("HOME", str(home))
    set_canonical_root(workspace, created_by="test")

    (home / ".cache").mkdir(parents=True, exist_ok=True)
    (home / ".cache" / "keep.txt").write_text("keep", encoding="utf-8")
    (home / "API KEY ODOO.txt").write_text("secret", encoding="utf-8")
    bad = home / "C:\\Users\\demo"
    bad.mkdir(parents=True, exist_ok=True)
    (bad / "x.txt").write_text("x", encoding="utf-8")

    scan = run_home_scan(workspace, home)
    assert scan["report"]["summary"]["candidate_count"] >= 2
    assert all(not item["path"].split("/")[-1].startswith(".") for item in scan["report"]["candidates"])

    clean = run_home_clean_obvious(workspace, home, max_moves=100)
    assert clean["status"] == "ok"
    assert clean["result"]["moved_count"] >= 2
    assert (home / ".cache").exists()
    assert not (home / "API KEY ODOO.txt").exists()


def test_openclaw_hook_supports_hygiene_commands(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    workspace = home / "workspace"
    _mk_workspace(workspace)
    monkeypatch.setenv("HOME", str(home))
    set_canonical_root(workspace, created_by="test")

    (workspace / "API KEY ODOO.txt").write_text("secret", encoding="utf-8")
    (home / "API KEY HOME.txt").write_text("secret-home", encoding="utf-8")

    monkeypatch.setattr(openclaw_hook, "send_telegram_message", lambda _text: {"ok": False, "sent": False, "reason": "missing_config"})

    repo_scan = openclaw_hook.handle_repo_command("/repo hygiene", root=workspace)
    assert repo_scan["ok"] is True

    repo_clean = openclaw_hook.handle_repo_command("/repo clean", root=workspace)
    assert repo_clean["ok"] is True

    home_scan = openclaw_hook.handle_repo_command("/home hygiene", root=workspace)
    assert home_scan["ok"] is True

    home_clean = openclaw_hook.handle_repo_command("/home clean", root=workspace)
    assert home_clean["ok"] is True

    outbox = workspace / "docs" / "_inbox" / "outbox_latest.md"
    assert outbox.exists()


def test_workspace_scan_treats_project_docs_and_repo_map_as_canon(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    workspace = home / "workspace"
    _mk_workspace(workspace)
    monkeypatch.setenv("HOME", str(home))
    set_canonical_root(workspace, created_by="test")

    (workspace / "PROJECT_BRIEF.md").write_text("# brief\n", encoding="utf-8")
    (workspace / "REPO_MAP.md").write_text("# map\n", encoding="utf-8")
    (workspace / "repo_map").mkdir(parents=True, exist_ok=True)
    (workspace / "repo_map" / "00_INDEX.md").write_text("# idx\n", encoding="utf-8")

    report = scan_workspace(workspace)
    by_path = {item["rel_path"]: item for item in report["entries"]}
    assert by_path["PROJECT_BRIEF.md"]["classification"] == "canon"
    assert by_path["REPO_MAP.md"]["classification"] == "canon"
    assert by_path["repo_map"]["classification"] == "canon"


def test_workspace_scan_excludes_sensitive_patterns_under_tests_path(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    workspace = home / "workspace"
    _mk_workspace(workspace)
    monkeypatch.setenv("HOME", str(home))
    set_canonical_root(workspace, created_by="test")

    tests_dir = workspace / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    (tests_dir / "test_password_rotation.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")

    report = scan_workspace(workspace)
    candidates = {item["rel_path"]: item for item in report["clean_candidates"]}
    assert "tests/test_password_rotation.py" not in candidates
