from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent


def _safe_json_load(path: Path, default: object) -> object:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(default, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return default

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def _tail_ndjson(path: Path, tail: int) -> list[dict[str, object]]:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
        return []

    lines = path.read_text(encoding="utf-8").splitlines()
    if tail > 0:
        lines = lines[-tail:]

    result: list[dict[str, object]] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
            if isinstance(parsed, dict):
                result.append(parsed)
        except json.JSONDecodeError:
            continue
    return result


def _is_within(base: Path, target: Path) -> bool:
    try:
        target.relative_to(base)
        return True
    except ValueError:
        return False


def _list_docs(root: Path, docs_path: str) -> list[dict[str, object]]:
    candidate = (root / docs_path).resolve()
    if not _is_within(root, candidate):
        raise ValueError("path escapes project root")
    if not candidate.exists() or not candidate.is_dir():
        return []

    files = [path for path in candidate.rglob("*") if path.is_file()]
    files.sort(key=lambda p: p.relative_to(root).as_posix().lower())

    return [
        {
            "path": path.relative_to(root).as_posix(),
            "size": path.stat().st_size,
        }
        for path in files
    ]


def _parse_markdown_table_row(line: str) -> list[str]:
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return []
    cells = [cell.strip() for cell in stripped.strip("|").split("|")]
    return cells


def _load_ledger(root: Path, limit: int) -> list[dict[str, str]]:
    ledger_path = root / "docs" / "empresa" / "ledger.md"
    if not ledger_path.exists():
        return []

    lines = ledger_path.read_text(encoding="utf-8").splitlines()
    section = ""
    headers: list[str] = []
    items: list[dict[str, str]] = []

    for line in lines:
        lower = line.strip().lower()
        if lower.startswith("## licitaciones"):
            section = "licitaciones"
            headers = []
            continue
        if lower.startswith("## leads"):
            section = "leads"
            headers = []
            continue
        if not section:
            continue

        cells = _parse_markdown_table_row(line)
        if not cells:
            continue
        if all(cell.startswith("-") for cell in cells):
            continue
        if not headers:
            headers = [cell.lower() for cell in cells]
            continue
        if len(cells) != len(headers):
            continue

        row = {headers[idx]: cells[idx] for idx in range(len(headers))}
        row["table"] = section
        items.append(row)

    items.sort(key=lambda item: (item.get("fecha", ""), item.get("table", "")), reverse=True)
    return items[:limit]


def _deep_merge_defaults(value: object, defaults: object) -> object:
    if isinstance(defaults, dict):
        base = value if isinstance(value, dict) else {}
        merged: dict[str, object] = {}
        for key, default_val in defaults.items():
            merged[key] = _deep_merge_defaults(base.get(key), default_val)
        for key, extra_val in base.items():
            if key not in merged:
                merged[key] = extra_val
        return merged
    if isinstance(defaults, list):
        return value if isinstance(value, list) else defaults
    return defaults if value is None else value


def _run_json_command(command: list[str], timeout: float = 2.5) -> object:
    try:
        out = subprocess.check_output(command, text=True, timeout=timeout)
        return json.loads(out)
    except Exception:
        return {}


def _runtime_topbar_snapshot() -> dict[str, object]:
    sessions = _run_json_command(["openclaw", "sessions", "--active", "60", "--json"])
    if not isinstance(sessions, list):
        return {
            "active_delegations_total": 0,
            "active_subagents": 0,
            "active_coders": 0,
            "delegations": [],
            "source_mode": "fallback",
        }

    subagents = [s for s in sessions if isinstance(s, dict) and "subagent" in str(s.get("key", ""))]
    coders = [s for s in sessions if isinstance(s, dict) and any(x in str(s.get("key", "")).lower() for x in ["codex", "claude", "pi"])]

    delegations: list[dict[str, object]] = []
    for item in subagents[:3]:
        key = str(item.get("key", "subagent"))
        delegations.append({
            "label": key.split(":")[-1][:28],
            "type": "subagent",
            "progress": 65,
            "status": "running",
        })
    for item in coders[: max(0, 3 - len(delegations))]:
        key = str(item.get("key", "coder"))
        delegations.append({
            "label": key.split(":")[-1][:28],
            "type": "coder",
            "progress": 55,
            "status": "running",
        })

    return {
        "active_delegations_total": len(subagents) + len(coders),
        "active_subagents": len(subagents),
        "active_coders": len(coders),
        "delegations": delegations,
        "source_mode": "live",
    }


def _build_dashboard_v1_payload(root: Path) -> dict[str, object]:
    default_payload: dict[str, object] = {
        "topbar": {
            "otto_status": "available",
            "active_delegations_total": 0,
            "active_subagents": 0,
            "active_coders": 0,
            "delegations": [],
        },
        "sg": {
            "cash_receivable_7d": 0,
            "overdue_count": 0,
            "cash_status": "green",
            "hot_pipeline_value": 0,
            "hot_opportunities_count": 0,
            "pipeline_status": "green",
            "ops_risk_count": 0,
            "top_risk_label": "Sin riesgo crítico",
            "risk_status": "green",
            "next_best_decision": "Sin recomendación",
            "next_best_decision_impact": "-",
        },
        "personal": {
            "top3": [],
            "critical_count": 0,
            "due_today_count": 0,
            "critical_status": "green",
            "next_decision": "",
            "next_decision_eta": "",
            "next_action": "",
            "next_action_impact": "-",
        },
        "activity": [],
        "meta": {
            "mode": "fallback",
            "last_updated": "-",
        },
    }

    raw_payload = _safe_json_load(root / "state" / "dashboard_v1.json", default_payload)
    payload = _deep_merge_defaults(raw_payload, default_payload)
    if not isinstance(payload, dict):
        payload = default_payload

    # Light auto-fallback from heartbeat status when present.
    heartbeat = _safe_json_load(root / "docs" / "_inbox" / "heartbeat_latest.json", {})
    if isinstance(heartbeat, dict):
        status = str(heartbeat.get("status", "")).strip().lower()
        topbar = payload.get("topbar") if isinstance(payload.get("topbar"), dict) else {}
        if not topbar.get("otto_status"):
            topbar["otto_status"] = "busy" if status in {"success", "running"} else "available"
            payload["topbar"] = topbar

    runtime_topbar = _runtime_topbar_snapshot()
    topbar = payload.get("topbar") if isinstance(payload.get("topbar"), dict) else {}
    topbar.update({k: v for k, v in runtime_topbar.items() if k in {"active_delegations_total", "active_subagents", "active_coders", "delegations"}})

    # If runtime sees no active sessions, infer lightweight live activity from dashboard events.
    activity_for_infer = payload.get("activity") if isinstance(payload.get("activity"), list) else []
    running_items = [a for a in activity_for_infer[-5:] if isinstance(a, dict) and str(a.get("status", "")).lower() == "running"]
    if int(topbar.get("active_delegations_total", 0) or 0) == 0 and running_items:
        topbar["active_delegations_total"] = len(running_items)
        topbar["active_subagents"] = len([x for x in running_items if str(x.get("type", "")).lower() == "subagent"])
        topbar["active_coders"] = len([x for x in running_items if str(x.get("type", "")).lower() == "coder"])
        topbar["delegations"] = [
            {
                "label": str(x.get("label", "Ejecución"))[:28],
                "type": "subagent" if str(x.get("type", "")).lower() == "subagent" else "coder" if str(x.get("type", "")).lower() == "coder" else "subagent",
                "progress": 40,
                "status": "running",
            }
            for x in running_items[:3]
        ]

    topbar["otto_status"] = "busy" if int(topbar.get("active_delegations_total", 0) or 0) > 0 else "available"
    payload["topbar"] = topbar

    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    meta["mode"] = runtime_topbar.get("source_mode", "fallback")
    meta["last_updated"] = datetime.now().strftime("%H:%M:%S")
    payload["meta"] = meta

    # Recent activity fallback.
    activity = payload.get("activity")
    if not isinstance(activity, list) or not activity:
        events = _tail_ndjson(root / "logs" / "activity.ndjson", 5)
        normalized: list[dict[str, object]] = []
        for item in events[-5:]:
            normalized.append(
                {
                    "time": item.get("ts", "-"),
                    "label": item.get("event", "evento"),
                    "status": "done",
                    "type": "system",
                }
            )
        payload["activity"] = normalized

    return payload


def _append_dashboard_event(root: Path, *, label: str, status: str = "done", kind: str = "system") -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    entry = {"time": ts, "label": label, "status": status, "type": kind}

    dashboard_state_path = root / "state" / "dashboard_v1.json"
    payload = _safe_json_load(dashboard_state_path, {})
    if not isinstance(payload, dict):
        payload = {}
    current = payload.get("activity") if isinstance(payload.get("activity"), list) else []
    current = [item for item in current if isinstance(item, dict)]
    current.append(entry)
    payload["activity"] = current[-5:]
    dashboard_state_path.parent.mkdir(parents=True, exist_ok=True)
    dashboard_state_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: object) -> None:
    body = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _text_response(handler: BaseHTTPRequestHandler, status: int, text: str, content_type: str) -> None:
    body = text.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def make_handler(root: Path) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        project_root = root.resolve()

        def _authorized(self) -> bool:
            token = os.getenv("DASHBOARD_BRIDGE_TOKEN", "").strip()
            if not token:
                return True
            auth = self.headers.get("Authorization", "")
            return auth == f"Bearer {token}"

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)

            if parsed.path == "/":
                html_path = self.project_root / "dashboard" / "index.html"
                if not html_path.exists():
                    _text_response(self, HTTPStatus.NOT_FOUND, "Missing dashboard/index.html", "text/plain")
                    return
                _text_response(
                    self,
                    HTTPStatus.OK,
                    html_path.read_text(encoding="utf-8"),
                    "text/html; charset=utf-8",
                )
                return

            if parsed.path == "/app.js":
                js_path = self.project_root / "dashboard" / "app.js"
                if not js_path.exists():
                    _text_response(self, HTTPStatus.NOT_FOUND, "Missing dashboard/app.js", "text/plain")
                    return
                _text_response(
                    self,
                    HTTPStatus.OK,
                    js_path.read_text(encoding="utf-8"),
                    "application/javascript; charset=utf-8",
                )
                return

            if parsed.path == "/style.css":
                css_path = self.project_root / "dashboard" / "style.css"
                if not css_path.exists():
                    _text_response(self, HTTPStatus.NOT_FOUND, "Missing dashboard/style.css", "text/plain")
                    return
                _text_response(
                    self,
                    HTTPStatus.OK,
                    css_path.read_text(encoding="utf-8"),
                    "text/css; charset=utf-8",
                )
                return

            if parsed.path == "/api/dashboard-v1":
                if not self._authorized():
                    _json_response(self, HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
                    return
                payload = _build_dashboard_v1_payload(self.project_root)
                _json_response(self, HTTPStatus.OK, payload)
                return

            if parsed.path == "/api/status":
                payload = _safe_json_load(
                    self.project_root / "state" / "status.json",
                    {"status": "idle", "task": "", "updated_at": ""},
                )
                _json_response(self, HTTPStatus.OK, payload)
                return

            if parsed.path == "/api/kanban":
                payload = _safe_json_load(
                    self.project_root / "state" / "kanban.json",
                    {"archive": [], "done": [], "in_progress": [], "todo": []},
                )
                _json_response(self, HTTPStatus.OK, payload)
                return

            if parsed.path == "/api/activity":
                query = parse_qs(parsed.query)
                raw_tail = query.get("tail", ["50"])[0]
                try:
                    tail = max(1, min(500, int(raw_tail)))
                except ValueError:
                    tail = 50

                payload = _tail_ndjson(self.project_root / "logs" / "activity.ndjson", tail)
                _json_response(self, HTTPStatus.OK, payload)
                return

            if parsed.path == "/api/docs":
                query = parse_qs(parsed.query)
                docs_path = query.get("path", ["docs/empresa"])[0]
                try:
                    files = _list_docs(self.project_root, docs_path)
                except ValueError:
                    _json_response(
                        self,
                        HTTPStatus.BAD_REQUEST,
                        {"error": "invalid_path", "path": docs_path},
                    )
                    return

                _json_response(self, HTTPStatus.OK, files)
                return

            if parsed.path == "/api/ledger":
                query = parse_qs(parsed.query)
                raw_limit = query.get("limit", ["20"])[0]
                try:
                    limit = max(1, min(200, int(raw_limit)))
                except ValueError:
                    limit = 20
                payload = _load_ledger(self.project_root, limit)
                _json_response(self, HTTPStatus.OK, payload)
                return

            _json_response(self, HTTPStatus.NOT_FOUND, {"error": "not_found", "path": parsed.path})

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)

            actions = {
                "/api/actions/refresh": {"label": "Dashboard refrescado", "kind": "system"},
                "/api/actions/pause-delegation": {"label": "Delegación pausada", "kind": "system"},
                "/api/actions/execute-sg": {"label": "Ejecución decisión SG solicitada", "kind": "subagent"},
                "/api/actions/sg-alternative": {"label": "Alternativa SG solicitada", "kind": "system"},
                "/api/actions/execute-personal": {"label": "Acción personal ejecutada", "kind": "subagent"},
            }

            if parsed.path not in actions:
                _json_response(self, HTTPStatus.NOT_FOUND, {"error": "not_found", "path": parsed.path})
                return
            if not self._authorized():
                _json_response(self, HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
                return

            action_label = actions[parsed.path]["label"]
            action_kind = actions[parsed.path]["kind"]

            _append_dashboard_event(
                self.project_root,
                label=f"{action_label} (iniciada)",
                status="running",
                kind=action_kind,
            )
            _append_dashboard_event(
                self.project_root,
                label=f"{action_label} (ack)",
                status="done",
                kind=action_kind,
            )
            _json_response(self, HTTPStatus.OK, {"ok": True, "action": parsed.path})

        def log_message(self, format: str, *args: object) -> None:  # noqa: A003
            return

    return Handler


def build_server(port: int, root: Path, host: str = "127.0.0.1") -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), make_handler(root=root.resolve()))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OTTO HQ dashboard server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18999)
    parser.add_argument("--root", default=str(ROOT), help="project root")
    args = parser.parse_args(argv)

    server = build_server(port=args.port, root=Path(args.root), host=args.host)
    print(f"Dashboard on http://{args.host}:{args.port}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
