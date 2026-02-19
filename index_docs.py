from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _scan_files(base: Path) -> list[Path]:
    if not base.exists():
        return []

    files = [
        path
        for path in base.rglob("*")
        if path.is_file() and path.name.lower() != "index.md"
    ]
    files.sort(key=lambda p: p.relative_to(base).as_posix().lower())
    return files


def _write_index_for_section(section_dir: Path, title: str) -> list[Path]:
    section_dir.mkdir(parents=True, exist_ok=True)
    entries = _scan_files(section_dir)

    lines = [f"# {title}", "", f"Actualizado UTC: {utc_now_iso()}", ""]
    if entries:
        for file_path in entries:
            rel = file_path.relative_to(section_dir).as_posix()
            lines.append(f"- [{rel}](./{rel})")
    else:
        lines.append("- (sin archivos)")

    (section_dir / "index.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return entries


def rebuild_indexes(root: Path) -> None:
    root = root.resolve()
    empresa = root / "docs" / "empresa"
    empresa.mkdir(parents=True, exist_ok=True)

    lic_dir = empresa / "licitaciones"
    leads_dir = empresa / "leads"
    cot_dir = empresa / "cotizaciones"

    lic_entries = _write_index_for_section(lic_dir, "Licitaciones")
    leads_entries = _write_index_for_section(leads_dir, "Leads")
    cot_entries = _write_index_for_section(cot_dir, "Cotizaciones")

    lines = [
        "# SG Empresa Index",
        "",
        f"Actualizado UTC: {utc_now_iso()}",
        "",
        "## Secciones",
        "",
        f"- [licitaciones/index.md](./licitaciones/index.md) ({len(lic_entries)} archivos)",
        f"- [leads/index.md](./leads/index.md) ({len(leads_entries)} archivos)",
        f"- [cotizaciones/index.md](./cotizaciones/index.md) ({len(cot_entries)} archivos)",
        "",
        "## Ultimos documentos (orden alfabetico)",
        "",
    ]

    combined: list[tuple[str, Path]] = []
    combined.extend(("licitaciones", item) for item in lic_entries)
    combined.extend(("leads", item) for item in leads_entries)
    combined.extend(("cotizaciones", item) for item in cot_entries)
    combined.sort(key=lambda pair: (pair[0], pair[1].name.lower(), pair[1].as_posix().lower()))

    if combined:
        for section, item in combined:
            rel = item.relative_to(empresa).as_posix()
            lines.append(f"- `{section}`: [{rel}](./{rel})")
    else:
        lines.append("- (sin documentos)")

    extras = [
        path
        for path in empresa.rglob("*")
        if path.is_file()
        and path.name.lower() != "index.md"
        and "licitaciones/" not in path.relative_to(empresa).as_posix()
        and "leads/" not in path.relative_to(empresa).as_posix()
        and "cotizaciones/" not in path.relative_to(empresa).as_posix()
    ]
    extras.sort(key=lambda p: p.relative_to(empresa).as_posix().lower())
    lines.extend(["", "## Otros documentos", ""])
    if extras:
        for item in extras:
            rel = item.relative_to(empresa).as_posix()
            lines.append(f"- [{rel}](./{rel})")
    else:
        lines.append("- (sin documentos adicionales)")

    (empresa / "index.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build deterministic indexes in docs/empresa")
    parser.add_argument("--root", default=str(ROOT), help="project root")
    args = parser.parse_args(argv)

    rebuild_indexes(root=Path(args.root))
    print("indexes updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
