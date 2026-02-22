#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(date_str: str) -> Path:
    base = ROOT / "audit" / "final" / date_str
    if base.exists():
        shutil.rmtree(base)
    for d in ["snapshot","tests","security","no_leak","delegation","retrieval","ingest","sharepoint","odoo","marketplace","day2","metrics"]:
        (base / d).mkdir(parents=True, exist_ok=True)

    copy_map = {
        "M0": ["security", "no_leak"],
        "M1": ["delegation"],
        "M2": ["retrieval"],
        "M3": ["ingest"],
        "M4": ["sharepoint"],
        "M5": ["odoo"],
        "M6": ["marketplace"],
        "M7": ["day2"],
        "M8": ["tests"],
    }
    for m, targets in copy_map.items():
        src = ROOT / "audit" / m
        if not src.exists():
            continue
        for t in targets:
            for p in src.glob("*"):
                if p.is_file():
                    shutil.copy2(p, base / t / p.name)
                elif p.is_dir():
                    shutil.copytree(p, base / t / p.name, dirs_exist_ok=True)

    git_txt = (
        f"branch: {subprocess.getoutput('git -C '+str(ROOT)+' rev-parse --abbrev-ref HEAD')}\n"
        f"commit: {subprocess.getoutput('git -C '+str(ROOT)+' rev-parse HEAD')}\n"
        f"status_clean: {'true' if not subprocess.getoutput('git -C '+str(ROOT)+' status --porcelain').strip() else 'false'}\n"
        f"date_utc: {datetime.utcnow().isoformat()}Z\n"
    )
    (base / "snapshot" / "git.txt").write_text(git_txt, encoding="utf-8")

    summary = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "go_no_go": "no_go",
        "reason": "Pending full end-to-end re-run from clean main with live integrations.",
    }
    (base / "metrics" / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (base / "README_AUDIT.md").write_text(
        "Run:\npython3 scripts/run_audit.py --all --date " + date_str + "\n\n"
        "Verify:\nsha256sum -c audit/final/" + date_str + "/metrics/hashes.sha256\n",
        encoding="utf-8",
    )

    # hashes
    rows = []
    for p in sorted(base.rglob("*")):
        if p.is_file() and p.name != "hashes.sha256":
            rows.append(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(ROOT)}")
    (base / "metrics" / "hashes.sha256").write_text("\n".join(rows) + "\n", encoding="utf-8")
    return base


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--date", default=datetime.utcnow().strftime("%Y-%m-%d"))
    args = ap.parse_args()
    out = run(args.date)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
