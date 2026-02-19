import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.repo_root import set_canonical_root
from scripts.session_memory_manager import (
    DEFAULT_POLICY,
    POLICY_PATH,
    append_event,
    apply_compact,
    apply_distill,
    build_session_id,
    needs_compact,
    needs_distill,
)


def _mk_workspace(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "CEO.md").write_text("# CEO\n", encoding="utf-8")
    (root / "INDEX.md").write_text("# INDEX\n", encoding="utf-8")
    (root / "openclaw").mkdir(parents=True, exist_ok=True)
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    (root / "ops").mkdir(parents=True, exist_ok=True)
    (root / "brain").mkdir(parents=True, exist_ok=True)


def _setup(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    workspace = home / "workspace"
    _mk_workspace(workspace)
    monkeypatch.setenv("HOME", str(home))
    set_canonical_root(workspace, created_by="test")
    return workspace


def _write_test_policy(workspace: Path) -> None:
    policy = deepcopy(DEFAULT_POLICY)
    policy["tiers"]["whatsapp_client"]["rolling_max_events"] = 6
    policy["tiers"]["whatsapp_client"]["compact_trigger_events"] = 5
    policy["tiers"]["whatsapp_client"]["rolling_max_chars"] = 100000
    (workspace / POLICY_PATH).parent.mkdir(parents=True, exist_ok=True)
    (workspace / POLICY_PATH).write_text(
        json.dumps(policy, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def test_session_id_is_deterministic_and_not_mixed(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    policy = deepcopy(DEFAULT_POLICY)

    base = {
        "agent_id": "otto",
        "channel": "discord",
        "account_id": "acc1",
        "chat_type": "channel",
        "peer_id": "p1",
        "channel_id": "c1",
        "thread_id": "t1",
    }
    sid_a1 = build_session_id(base, policy)["session_id"]
    sid_a2 = build_session_id(base, policy)["session_id"]
    sid_b = build_session_id({**base, "thread_id": "t2"}, policy)["session_id"]
    assert sid_a1 == sid_a2
    assert sid_a1 != sid_b

    first = append_event(
        workspace,
        {
            **base,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message_id": "m1",
            "text": "hola thread 1",
        },
    )
    second = append_event(
        workspace,
        {
            **base,
            "thread_id": "t2",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message_id": "m2",
            "text": "hola thread 2",
        },
    )
    assert first["session_id"] != second["session_id"]
    assert (workspace / "state" / "sessions" / first["session_id"] / "rolling.ndjson").is_file()
    assert (workspace / "state" / "sessions" / second["session_id"] / "rolling.ndjson").is_file()


def test_compaction_trigger_by_tier_and_apply(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    _write_test_policy(workspace)

    for idx in range(8):
        append_event(
            workspace,
            {
                "agent_id": "otto",
                "channel": "whatsapp",
                "actor_type": "client",
                "peer_id": "client-001",
                "chat_type": "dm",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "message_id": f"m{idx}",
                "text": f"mensaje {idx}",
                "labels": ["chat_normal"],
            },
        )

    sid = build_session_id(
        {
            "agent_id": "otto",
            "channel": "whatsapp",
            "actor_type": "client",
            "peer_id": "client-001",
            "chat_type": "dm",
        },
        deepcopy(DEFAULT_POLICY),
    )["session_id"]

    assert needs_compact(workspace, sid) is True
    out = apply_compact(workspace, sid)
    assert out["status"] == "success"
    assert out["after"]["rolling_events"] <= 6
    assert (workspace / out["paths"]["summary"]).is_file()


def test_distill_for_inactive_discord_thread(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    old_ts = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()

    ev = append_event(
        workspace,
        {
            "agent_id": "otto",
            "channel": "discord",
            "chat_type": "thread",
            "peer_id": "user-01",
            "channel_id": "sales",
            "thread_id": "case-77",
            "timestamp": old_ts,
            "message_id": "m-old",
            "text": "Decision del caso para cierre",
            "labels": ["memory_worthy"],
        },
    )
    sid = ev["session_id"]

    assert needs_distill(workspace, sid) is True
    out = apply_distill(workspace, sid)
    assert out["status"] == "success"
    target = workspace / out["target_rel"]
    assert (target / "source" / "thread_summary.md").is_file()
    assert (target / "source" / "domain_learnings.md").is_file()
    assert (target / "source" / "DISTILL_META.json").is_file()
