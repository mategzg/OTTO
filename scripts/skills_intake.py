#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from scripts.repo_root import get_canonical_root

INTAKE_ROOT = Path("skills/_intake")
PROD_ROOT = Path("skills/production")
CATALOG_PATH = Path("state/skills_catalog.json")
DECISIONS_PATH = Path("audit/M6/intake_decisions.ndjson")
SNAPSHOT_PATH = Path("audit/M6/catalog_snapshot.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        x = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return x if isinstance(x, dict) else {}


def _save_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def _append_ndjson(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _risk_score(files: List[Path], text_blob: str) -> int:
    score = 0
    names = "\n".join(p.name.lower() for p in files)
    if any(n in names for n in [".env", "id_rsa", "secret", "token"]):
        score += 7
    if any(x in text_blob.lower() for x in ["subprocess", "os.system", "eval(", "exec("]):
        score += 4
    return min(10, score)


def _relevance_score(text_blob: str) -> int:
    keys = ["skill", "openclaw", "automation", "workflow", "odoo", "ingest", "memory"]
    hits = sum(1 for k in keys if k in text_blob.lower())
    return min(10, hits + 2)


def run_intake(root: str | Path, *, pack_path: str, rollback: bool = False) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    if rollback:
        catalog = _load_json(canonical_root / CATALOG_PATH)
        last = str(catalog.get("last_promoted", "")).strip()
        if last:
            p = canonical_root / last
            if p.exists():
                shutil.rmtree(p)
            catalog["last_promoted"] = ""
            _save_json(canonical_root / CATALOG_PATH, catalog)
        out = {"status": "rolled_back", "removed": last}
        _append_ndjson(canonical_root / DECISIONS_PATH, {"ts": _utc_now(), **out})
        return out

    src = Path(pack_path).expanduser().resolve()
    if not src.is_file() or src.suffix.lower() != ".zip":
        out = {"status": "rejected", "reason": "unsupported_pack"}
        _append_ndjson(canonical_root / DECISIONS_PATH, {"ts": _utc_now(), **out})
        return out

    pack_id = hashlib.sha256(src.read_bytes()).hexdigest()[:12]
    intake_dir = canonical_root / INTAKE_ROOT / pack_id
    if intake_dir.exists():
        shutil.rmtree(intake_dir)
    intake_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(src, "r") as zf:
        zf.extractall(intake_dir)

    files = [p for p in intake_dir.rglob("*") if p.is_file()]
    text_blob = "\n".join((p.read_text(encoding="utf-8", errors="ignore")[:2000] for p in files[:20]))

    has_skill = any(p.name == "SKILL.md" for p in files)
    risk = _risk_score(files, text_blob)
    relevance = _relevance_score(text_blob)

    status = "rejected"
    reason = "missing_skill_md" if not has_skill else "risk_or_relevance_gate"
    promoted_rel = ""

    if has_skill and risk <= 5 and relevance >= 4:
        skill_key = src.stem.replace(" ", "_").lower()
        prod_dir = canonical_root / PROD_ROOT / skill_key
        if prod_dir.exists():
            shutil.rmtree(prod_dir)
        shutil.copytree(intake_dir, prod_dir)
        status = "promoted"
        reason = "passed"
        promoted_rel = prod_dir.resolve().relative_to(canonical_root.resolve()).as_posix()

    decision = {
        "ts": _utc_now(),
        "pack": src.as_posix(),
        "pack_id": pack_id,
        "status": status,
        "reason": reason,
        "risk_score": risk,
        "relevance_score": relevance,
        "has_skill_md": has_skill,
        "promoted_path": promoted_rel,
    }
    _append_ndjson(canonical_root / DECISIONS_PATH, decision)

    catalog = _load_json(canonical_root / CATALOG_PATH)
    if "skills" not in catalog or not isinstance(catalog.get("skills"), list):
        catalog["skills"] = []
    if promoted_rel:
        card = {
            "skill_key": Path(promoted_rel).name,
            "path": promoted_rel,
            "when_to_use": "See SKILL.md",
            "when_not_to_use": "If outside declared scope",
            "promoted_at": _utc_now(),
        }
        catalog["skills"] = [s for s in catalog["skills"] if s.get("skill_key") != card["skill_key"]] + [card]
        catalog["last_promoted"] = promoted_rel
    _save_json(canonical_root / CATALOG_PATH, catalog)
    _save_json(canonical_root / SNAPSHOT_PATH, {"generated_at": _utc_now(), "catalog": catalog})
    return decision


def main() -> int:
    p = argparse.ArgumentParser(description="Skills marketplace intake")
    p.add_argument("--root", default=".")
    p.add_argument("--pack", default="")
    p.add_argument("--rollback", action="store_true")
    args = p.parse_args()
    out = run_intake(args.root, pack_path=args.pack, rollback=args.rollback)
    print(json.dumps(out, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
