#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, check=False)


def main() -> int:
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    run = _run(["python3", "scripts/run_audit.py", "--spec", "spec004_core", "--date", date_str])
    payload = {}
    try:
        payload = json.loads((run.stdout or "").strip().splitlines()[-1])
    except Exception:
        payload = {"go_no_go": "no_go", "error": "invalid_audit_output", "stdout": run.stdout, "stderr": run.stderr}

    src = ROOT / "audit" / "final" / f"spec004_core_{date_str}"
    dst = ROOT / "audit" / "nightly" / date_str
    if src.exists():
        if dst.exists():
            shutil.rmtree(dst)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst)

    nightly_report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "date": date_str,
        "go_no_go": payload.get("go_no_go", "no_go"),
        "source": str(src),
        "nightly_copy": str(dst),
        "zip": payload.get("zip", ""),
        "returncode": run.returncode,
    }
    report_path = ROOT / "audit" / "nightly" / date_str / "nightly_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(nightly_report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if str(payload.get("go_no_go", "")).lower() != "go":
        _run([
            "openclaw",
            "system",
            "event",
            "--mode",
            "now",
            "--text",
            f"SPEC004 CORE NIGHTLY NO-GO {date_str}. Revisar {report_path.as_posix()}",
        ])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
