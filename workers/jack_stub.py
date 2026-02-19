from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from hq_logging import append_activity, utc_now_iso

ROOT = Path(__file__).resolve().parents[1]

SG_HINTS = (
    "sg",
    "precio",
    "precios",
    "proveedor",
    "proveedores",
    "cotizacion",
    "cotización",
    "cotizaciones",
    "producto",
    "productos",
    "acabados",
    "politica",
    "política",
)
NON_SG_HINTS = (
    "depa",
    "departamento",
    "vuelo",
    "vuelos",
    "hotel",
    "vacaciones",
    "netflix",
    "personal",
    "pareja",
)


def _is_sg_query(prompt: str) -> bool:
    text = prompt.lower()
    if any(hint in text for hint in NON_SG_HINTS):
        return False
    return any(hint in text for hint in SG_HINTS)


def _read_jack_url(root: Path) -> str:
    jack_path = root / "docs" / "empresa" / "JACK_URL.txt"
    if not jack_path.exists():
        return "(missing)"
    return jack_path.read_text(encoding="utf-8").strip() or "(missing)"


def request(
    prompt: str,
    root: Path | None = None,
    task_id: str | None = None,
    channel: str = "manual",
) -> dict[str, str]:
    base_root = (root or ROOT).resolve()
    if not task_id:
        task_id = f"jack-{utc_now_iso().replace(':', '').replace('-', '').replace('T', '').replace('Z', '')}-{uuid4().hex[:8]}"

    if not _is_sg_query(prompt):
        append_activity(
            root=base_root,
            event="jack_rejected_non_sg",
            detail="consulta fuera de dominio SG",
            task_id=task_id,
            channel=channel,
            level="warning",
        )
        return {
            "reason": "non_sg_query",
            "status": "rejected",
            "task_id": task_id,
        }

    request_dir = base_root / "docs" / "_inbox" / "jack_requests"
    request_dir.mkdir(parents=True, exist_ok=True)

    jack_url = _read_jack_url(base_root)
    created_at = utc_now_iso()
    request_file = request_dir / f"{task_id}.md"
    content = (
        "---\n"
        f"task_id: {task_id}\n"
        f"created_at: {created_at}\n"
        "kind: jack\n"
        "status: needs_browser\n"
        "---\n\n"
        "# JACK Request\n\n"
        f"jack_url: {jack_url}\n\n"
        "## Prompt\n\n"
        f"{prompt.strip()}\n"
    )
    request_file.write_text(content, encoding="utf-8")

    append_activity(
        root=base_root,
        event="jack_request_created",
        detail=f"request_file={request_file.as_posix()}",
        task_id=task_id,
        channel=channel,
        level="info",
    )

    return {
        "instructions": "Abrir JACK en browser relay, pegar prompt SG y guardar respuesta en docs/empresa/cotizaciones/",
        "request_file": request_file.as_posix(),
        "status": "needs_browser",
        "task_id": task_id,
    }
