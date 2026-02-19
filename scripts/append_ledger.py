from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER_PATH = ROOT / "docs" / "empresa" / "ledger.md"

LIC_FIELDS = ["fecha", "fuente", "keyword", "monto", "deadline", "riesgo", "archivo_doc"]
LEAD_FIELDS = ["fecha", "empresa", "contacto", "canal", "ciudad", "proyecto", "archivo_doc"]


def _default_ledger() -> str:
    return (
        "# SG Ledger\n\n"
        "## Licitaciones\n\n"
        "| fecha | fuente | keyword | monto | deadline | riesgo | archivo_doc |\n"
        "| --- | --- | --- | --- | --- | --- | --- |\n"
        "\n"
        "## Leads\n\n"
        "| fecha | empresa | contacto | canal | ciudad | proyecto | archivo_doc |\n"
        "| --- | --- | --- | --- | --- | --- | --- |\n"
    )


def _parse_table(lines: list[str], section_title: str, fields: list[str]) -> list[dict[str, str]]:
    in_section = False
    headers_seen = False
    rows: list[dict[str, str]] = []

    for line in lines:
        stripped = line.strip()
        lower = stripped.lower()
        if lower.startswith("## "):
            in_section = lower == f"## {section_title}".lower()
            headers_seen = False
            continue
        if not in_section:
            continue
        if not stripped.startswith("|") or not stripped.endswith("|"):
            continue

        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if not headers_seen:
            headers_seen = True
            continue
        if all(cell.startswith("-") for cell in cells):
            continue
        if len(cells) != len(fields):
            continue

        rows.append({fields[idx]: cells[idx] for idx in range(len(fields))})

    return rows


def _row_hash(row: dict[str, str], fields: list[str]) -> str:
    key = "|".join(row.get(field, "").strip().lower() for field in fields)
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def _render_table(title: str, fields: list[str], rows: list[dict[str, str]]) -> str:
    lines = [f"## {title}", "", f"| {' | '.join(fields)} |", f"| {' | '.join(['---'] * len(fields))} |"]

    for row in rows:
        values = [row.get(field, "").replace("|", "/") for field in fields]
        lines.append(f"| {' | '.join(values)} |")

    lines.append("")
    return "\n".join(lines)


def _sort_rows(rows: list[dict[str, str]], fields: list[str]) -> list[dict[str, str]]:
    return sorted(
        rows,
        key=lambda row: (row.get("fecha", ""), _row_hash(row, fields)),
        reverse=True,
    )


def append_row(root: Path, table: str, row: dict[str, str]) -> bool:
    root = root.resolve()
    ledger_path = root / "docs" / "empresa" / "ledger.md"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    if not ledger_path.exists():
        ledger_path.write_text(_default_ledger(), encoding="utf-8")

    text = ledger_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    lic_rows = _parse_table(lines, "Licitaciones", LIC_FIELDS)
    lead_rows = _parse_table(lines, "Leads", LEAD_FIELDS)

    if table == "licitaciones":
        fields = LIC_FIELDS
        target_rows = lic_rows
    else:
        fields = LEAD_FIELDS
        target_rows = lead_rows

    normalized = {field: row.get(field, "").strip() for field in fields}
    new_hash = _row_hash(normalized, fields)

    existing_hashes = {_row_hash(existing, fields) for existing in target_rows}
    if new_hash in existing_hashes:
        return False

    target_rows.append(normalized)
    lic_rows = _sort_rows(lic_rows, LIC_FIELDS)
    lead_rows = _sort_rows(lead_rows, LEAD_FIELDS)

    rendered = [
        "# SG Ledger",
        "",
        _render_table("Licitaciones", LIC_FIELDS, lic_rows),
        _render_table("Leads", LEAD_FIELDS, lead_rows),
    ]
    ledger_path.write_text("\n".join(rendered).strip() + "\n", encoding="utf-8")
    return True


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Append row to SG ledger")
    parser.add_argument("--root", default=str(ROOT), help="project root")

    subparsers = parser.add_subparsers(dest="table", required=True)

    lic = subparsers.add_parser("licitaciones")
    for field in LIC_FIELDS:
        lic.add_argument(f"--{field.replace('_', '-')}", required=True)

    leads = subparsers.add_parser("leads")
    for field in LEAD_FIELDS:
        leads.add_argument(f"--{field.replace('_', '-')}", required=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.table == "licitaciones":
        row = {field: getattr(args, field) for field in LIC_FIELDS}
    else:
        row = {field: getattr(args, field) for field in LEAD_FIELDS}

    inserted = append_row(root=Path(args.root), table=args.table, row=row)
    print("inserted" if inserted else "duplicate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
