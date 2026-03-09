#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

BUCKETS = [
    "professional_sg",
    "personal_development",
    "profile_owner",
    "vision_owner",
    "biography_history",
    "strategy_business",
    "philosophy",
    "psychology",
    "neuroscience_health",
    "persuasion_communication",
    "habits_execution",
    "misc_knowledge",
]

KEYWORDS = {
    "professional_sg": ["sg", "acabados", "cliente", "ventas", "odoo", "postventa", "cobranza", "factura", "operaciones", "empresa"],
    "personal_development": ["desarrollo personal", "crecimiento", "disciplina", "mejorar", "aprendizaje", "autocontrol", "mindset"],
    "profile_owner": ["prefiero", "me gusta", "mi forma", "quiero que", "mateo", "owner", "perfil", "trabajo en"],
    "vision_owner": ["mision", "north star", "autonom", "vision", "suprema", "objetivo", "largo plazo", "dominancia"],
    "biography_history": ["antes", "historia", "timeline", "pasado", "cuando tenia", "en 20", "biografia"],
    "strategy_business": ["estrategia", "go to market", "segment", "pricing", "pipeline", "margen", "growth", "competencia"],
    "philosophy": ["filosofia", "epistem", "etica", "stoic", "aristot", "nietzsche", "sentido", "virtud"],
    "psychology": ["psicolog", "sesgo", "emocion", "motivacion", "conducta", "dopamina", "trauma", "ansiedad"],
    "neuroscience_health": ["neuro", "sueño", "sleep", "salud", "cortisol", "atencion", "foco", "stress", "ejercicio", "nutric"],
    "persuasion_communication": ["persuasion", "copy", "storytelling", "comunic", "negoci", "objecion", "influencia", "pitch"],
    "habits_execution": ["habito", "rutina", "checklist", "sistema", "ejecucion", "plan diario", "consistencia", "deep work"],
}

QUERY_BANK = {
    "professional_sg": [
        "operacion SG acabados", "estandares de ventas y postventa", "flujo legal cobranza peru", "runbook operaciones odoo", "gobernanza accountability sg"
    ],
    "personal_development": [
        "stack desarrollo personal transferible", "criterios de autocontrol", "aprendizaje continuo practico", "mejorar capacidad de ejecucion", "framework crecimiento personal"
    ],
    "profile_owner": [
        "preferencias operativas de mateo", "contrato de comunicacion owner", "estilo de trabajo del owner", "limites de colaboracion", "reglas perfil actual"
    ],
    "vision_owner": [
        "mision autonomia absoluta", "north star del sistema", "vision de capacidad responsabilidad", "horizonte estrategico owner", "principios de vision"
    ],
    "biography_history": [
        "eventos historicos clave del owner", "hitos cronologicos 2026", "timeline de decisiones", "biografia operativa relevante", "historial de cambios de enfoque"
    ],
    "strategy_business": [
        "estrategia de negocio", "priorizacion de funciones business", "modelo go to market", "decision sobre margenes y pricing", "framework de crecimiento empresarial"
    ],
    "philosophy": [
        "filosofia aplicada a decisiones", "criterio epistemico de verdad", "etica de ejecucion", "virtud y disciplina", "marcos filosoficos practicos"
    ],
    "psychology": [
        "psicologia de comportamiento", "sesgos en toma de decisiones", "motivacion y autorregulacion", "gestion emocional para ejecucion", "modelos psicologicos aplicables"
    ],
    "neuroscience_health": [
        "protocolo de sueño y energia", "neurociencia de atencion", "higiene de estres", "salud para rendimiento cognitivo", "recuperacion y foco"
    ],
    "persuasion_communication": [
        "tecnicas de persuasion", "manejo de objeciones", "framework de comunicacion", "copywriting para conversion", "negociacion efectiva"
    ],
    "habits_execution": [
        "sistemas de habitos", "rutinas de ejecucion diaria", "checklist de consistencia", "disciplina operacional", "deep work aplicado"
    ],
    "misc_knowledge": [
        "conocimiento general no categorizado", "temas varios del export", "aprendizajes transversales", "insights complementarios", "notas auxiliares"
    ],
}

TARGETS = {
    "strategy_business": "brain/domains/sg_acabados/30_STRATEGY_BUSINESS_PLAYBOOK.md",
    "professional_sg": "brain/domains/sg_acabados/40_PERSUASION_AND_CLIENT_COMMUNICATION.md",
    "philosophy": "brain/domains/personal_ops/36_PHILOSOPHY_DECISION_MODELS.md",
    "psychology": "brain/domains/personal_ops/37_PSYCHOLOGY_BEHAVIOR_MODELS.md",
    "neuroscience_health": "brain/domains/personal_ops/38_NEUROSCIENCE_HEALTH_PROTOCOLS.md",
    "persuasion_communication": "brain/domains/personal_ops/39_PERSUASION_COMMUNICATION_SYSTEMS.md",
    "habits_execution": "brain/domains/personal_ops/41_HABITS_EXECUTION_SYSTEMS.md",
    "personal_development": "brain/domains/personal_ops/42_PERSONAL_DEVELOPMENT_SYNTHESIS.md",
    "vision_owner": "memory/vision/95_EXPORT_REINGEST_EVIDENCE_20260222.md",
    "profile_owner": "memory/profile/96_EXPORT_PROFILE_EVIDENCE_20260222.md",
    "biography_history": "memory/profile/97_EXPORT_BIOGRAPHY_HISTORY_20260222.md",
}


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_latest_messages() -> tuple[Path, Path]:
    rep = json.loads((ROOT / "docs/_inbox/export_reingest_v2_latest.json").read_text(encoding="utf-8"))
    msg = Path(rep["phases"]["1_normalizacion_chunked"]["outputs"]["messages_ndjson"])
    return ROOT / msg, ROOT / Path(rep["source_processed"])


def clean_text(s: str) -> str:
    s = s.replace("\u0000", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def classify(text: str) -> tuple[str, float, dict[str, int]]:
    t = text.lower()
    scores: dict[str, int] = {}
    for b in BUCKETS:
        if b == "misc_knowledge":
            continue
        k = KEYWORDS.get(b, [])
        scores[b] = sum(1 for kw in k if kw in t)
    best = max(scores.items(), key=lambda x: x[1]) if scores else ("misc_knowledge", 0)
    if best[1] <= 0:
        return "misc_knowledge", 0.2, scores
    top = sorted(scores.values(), reverse=True)
    margin = best[1] - (top[1] if len(top) > 1 else 0)
    conf = min(0.99, 0.5 + 0.08 * best[1] + 0.05 * max(0, margin))
    return best[0], round(conf, 3), scores


def main() -> int:
    messages_path, processed_root = load_latest_messages()
    out_dir = ROOT / "docs/_inbox/export_raw_buckets_latest"
    out_dir.mkdir(parents=True, exist_ok=True)

    bucket_rows: dict[str, list[dict[str, Any]]] = {b: [] for b in BUCKETS}
    bucket_terms: dict[str, Counter[str]] = {b: Counter() for b in BUCKETS}

    with messages_path.open(encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            obj = json.loads(line)
            role = str(obj.get("role", ""))
            if role not in {"user", "assistant"}:
                continue
            text = clean_text(str(obj.get("text", "")))
            if len(text) < 80:
                continue
            bucket, conf, scores = classify(text)
            excerpt = text[:500]
            row = {
                "line": i,
                "conv_id": obj.get("conv_id"),
                "msg_id": obj.get("msg_id"),
                "role": role,
                "bucket": bucket,
                "confidence": conf,
                "source_ref": obj.get("source_ref"),
                "excerpt": excerpt,
                "keyword_scores": scores,
            }
            bucket_rows[bucket].append(row)
            for w in re.findall(r"[a-záéíóúñ_]{5,}", text.lower()):
                bucket_terms[bucket][w] += 1

    bucket_manifest = {
        "created_at": now_utc(),
        "messages_path": messages_path.relative_to(ROOT).as_posix(),
        "processed_root": processed_root.relative_to(ROOT).as_posix(),
        "buckets": {},
        "version": 1,
    }

    for b in BUCKETS:
        rows = sorted(bucket_rows[b], key=lambda r: r["confidence"], reverse=True)
        top = rows[:120]
        payload = {
            "bucket": b,
            "count": len(rows),
            "top_terms": [t for t, _ in bucket_terms[b].most_common(30)],
            "items": top,
        }
        (out_dir / f"{b}.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        bucket_manifest["buckets"][b] = {
            "count": len(rows),
            "avg_confidence": round(sum(r["confidence"] for r in rows) / max(1, len(rows)), 3),
            "manifest": f"docs/_inbox/export_raw_buckets_latest/{b}.json",
            "sample_refs": [r["source_ref"] for r in rows[:5]],
        }

    (ROOT / "docs/_inbox/export_raw_bucketization_latest.json").write_text(
        json.dumps(bucket_manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    md_lines = ["# Export Raw Bucketization (Latest)", "", f"- Created at: `{bucket_manifest['created_at']}`", f"- Source: `{bucket_manifest['messages_path']}`", "", "## Buckets"]
    for b in BUCKETS:
        d = bucket_manifest["buckets"][b]
        md_lines.append(f"- `{b}`: count={d['count']} avg_conf={d['avg_confidence']} manifest=`{d['manifest']}`")
    (ROOT / "docs/_inbox/export_raw_bucketization_latest.md").write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    synthesis = {"created_at": now_utc(), "targets": {}, "source_manifest": "docs/_inbox/export_raw_bucketization_latest.json", "version": 1}

    for bucket, target_rel in TARGETS.items():
        rows = sorted(bucket_rows[bucket], key=lambda r: r["confidence"], reverse=True)[:25]
        target = ROOT / target_rel
        target.parent.mkdir(parents=True, exist_ok=True)
        lines = [f"# {bucket.replace('_', ' ').title()} — Export Synthesis 20260222", "", "Evidence-first synthesis from normalized ChatGPT export.", "", "## Extracted Insights"]
        for idx, r in enumerate(rows[:12], 1):
            lines.append(f"- Insight {idx}: {r['excerpt'][:220]}...")
            lines.append(f"  - ref: `{r['source_ref']}` msg=`{r['msg_id']}` conf={r['confidence']}")
        lines.extend(["", "## Source", f"- `{messages_path.relative_to(ROOT).as_posix()}`"])
        target.write_text("\n".join(lines) + "\n", encoding="utf-8")
        synthesis["targets"][bucket] = {
            "target": target_rel,
            "insights": min(12, len(rows)),
            "source_items_considered": len(rows),
        }

    # update key indexes with new branches
    idx_sg = ROOT / "brain/domains/sg_acabados/00_INDEX.md"
    sg_text = idx_sg.read_text(encoding="utf-8")
    for add in [
        "- `brain/domains/sg_acabados/30_STRATEGY_BUSINESS_PLAYBOOK.md`",
        "- `brain/domains/sg_acabados/40_PERSUASION_AND_CLIENT_COMMUNICATION.md`",
    ]:
        if add not in sg_text:
            sg_text += "\n" + add
    idx_sg.write_text(sg_text, encoding="utf-8")

    idx_po = ROOT / "brain/domains/personal_ops/00_INDEX.md"
    po_text = idx_po.read_text(encoding="utf-8")
    for add in [
        "- `36_PHILOSOPHY_DECISION_MODELS.md` - filosofía aplicada para criterios de decisión.",
        "- `37_PSYCHOLOGY_BEHAVIOR_MODELS.md` - psicología aplicada a conducta y autorregulación.",
        "- `38_NEUROSCIENCE_HEALTH_PROTOCOLS.md` - neurociencia/salud para rendimiento sostenido.",
        "- `39_PERSUASION_COMMUNICATION_SYSTEMS.md` - persuasión y comunicación estratégica.",
        "- `41_HABITS_EXECUTION_SYSTEMS.md` - sistemas de hábitos y ejecución diaria.",
        "- `42_PERSONAL_DEVELOPMENT_SYNTHESIS.md` - síntesis transversal de desarrollo personal.",
    ]:
        if add not in po_text:
            po_text += "\n" + add
    idx_po.write_text(po_text, encoding="utf-8")

    # touch profile + timeline
    profile_current = ROOT / "memory/01_PROFILE_CURRENT.md"
    pc = profile_current.read_text(encoding="utf-8")
    marker = "- Reprocess 2026-02-22 raw-first: `memory/profile/96_EXPORT_PROFILE_EVIDENCE_20260222.md`"
    if marker not in pc:
        pc += "\n## Reprocess updates\n" + marker + "\n"
        profile_current.write_text(pc, encoding="utf-8")

    tl_path = ROOT / "memory/06_TIMELINE.ndjson"
    tl_entry = {
        "id": "mem-export-rag-20260222-raw-synth",
        "type": "timeline",
        "key": "timeline:export_raw_first_rag_synthesis_20260222",
        "captured_at": now_utc(),
        "source_ref": messages_path.relative_to(ROOT).as_posix(),
        "confidence": "high",
        "best_known": True,
        "status": "active",
        "supersedes": [],
        "tags": ["chatgpt_reprocess", "rag", "raw_bucketization"],
        "notes": "Se ejecuta pipeline raw-first con bucketización estricta y síntesis RAG por ramas.",
        "date": "2026-02-22",
        "event": "Reprocesamiento raw-first y expansión de ramas canónicas de conocimiento.",
        "context": "Cobertura amplia en filosofía, psicología, estrategia, persuasión, hábitos y perfil/visión.",
    }
    existing = tl_path.read_text(encoding="utf-8") if tl_path.exists() else ""
    if "mem-export-rag-20260222-raw-synth" not in existing:
        with tl_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(tl_entry, ensure_ascii=False) + "\n")

    (ROOT / "docs/_inbox/export_rag_synthesis_latest.json").write_text(json.dumps(synthesis, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_syn = ["# Export RAG Synthesis (Latest)", "", f"- Created at: `{synthesis['created_at']}`", f"- Source raw manifest: `{synthesis['source_manifest']}`", "", "## Targets"]
    for b, d in synthesis["targets"].items():
        md_syn.append(f"- `{b}` -> `{d['target']}` insights={d['insights']} considered={d['source_items_considered']}")
    (ROOT / "docs/_inbox/export_rag_synthesis_latest.md").write_text("\n".join(md_syn) + "\n", encoding="utf-8")

    # QA 60 queries
    qa_rows = []
    searchable_files = [ROOT / p for p in TARGETS.values() if (ROOT / p).exists()]
    searchable_files += [ROOT / "brain/domains/sg_acabados/00_INDEX.md", ROOT / "brain/domains/personal_ops/00_INDEX.md", ROOT / "memory/01_PROFILE_CURRENT.md"]
    corpus = []
    for fp in searchable_files:
        txt = fp.read_text(encoding="utf-8", errors="replace").lower()
        corpus.append((fp.relative_to(ROOT).as_posix(), txt))

    for bucket in BUCKETS:
        for q in QUERY_BANK[bucket]:
            tokens = [t for t in re.findall(r"[a-záéíóúñ]{4,}", q.lower()) if len(t) > 3]
            hits = []
            for path, txt in corpus:
                score = sum(1 for t in tokens if t in txt)
                if score > 0:
                    hits.append((score, path))
            hits.sort(reverse=True)
            qa_rows.append({
                "bucket": bucket,
                "query": q,
                "hits": len(hits),
                "top_match": hits[0][1] if hits else "",
                "top_score": hits[0][0] if hits else 0,
                "pass": bool(hits),
            })

    by_bucket = {}
    gaps = []
    for b in BUCKETS:
        rows = [r for r in qa_rows if r["bucket"] == b]
        hit = sum(1 for r in rows if r["pass"])
        by_bucket[b] = {"queries": len(rows), "hits": hit, "hit_rate": round(hit / max(1, len(rows)), 3)}
        for r in rows:
            if not r["pass"]:
                gaps.append({"bucket": b, "query": r["query"], "gap": "no lexical hit in synthesized branches"})

    qa = {
        "created_at": now_utc(),
        "queries_total": len(qa_rows),
        "queries_with_hits": sum(1 for r in qa_rows if r["pass"]),
        "overall_hit_rate": round(sum(1 for r in qa_rows if r["pass"]) / max(1, len(qa_rows)), 3),
        "by_bucket": by_bucket,
        "gaps": gaps,
        "query_results": qa_rows,
        "version": 1,
    }
    (ROOT / "docs/_inbox/export_rag_qa_latest.json").write_text(json.dumps(qa, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    qa_md = ["# Export RAG QA (Latest)", "", f"- Queries: `{qa['queries_total']}`", f"- Hits: `{qa['queries_with_hits']}`", f"- Hit-rate: `{qa['overall_hit_rate']}`", "", "## Per bucket"]
    for b, d in by_bucket.items():
        qa_md.append(f"- `{b}`: {d['hits']}/{d['queries']} ({d['hit_rate']})")
    qa_md.extend(["", "## Explicit gaps"])
    if not gaps:
        qa_md.append("- No lexical gaps detected in 60-query pass.")
    else:
        for g in gaps[:50]:
            qa_md.append(f"- `{g['bucket']}` :: {g['query']} -> {g['gap']}")
    (ROOT / "docs/_inbox/export_rag_qa_latest.md").write_text("\n".join(qa_md) + "\n", encoding="utf-8")

    print(json.dumps({"status": "ok", "buckets": {k: len(v) for k, v in bucket_rows.items()}, "qa_hit_rate": qa["overall_hit_rate"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
