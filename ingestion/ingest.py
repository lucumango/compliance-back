"""Run the full ingestion: PDF -> structured JSON, one file per norma.

Each output unit is an article (or ISO clause) carrying its hierarchy, a
human-readable citation, and a retrieval text that repeats the norm name and
location. Repeating that context in the embedded text is what lets a chunk be
recovered by a query phrased in terms of the law ("¿qué dice la ley de datos
personales sobre el consentimiento?") rather than the article's own wording.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from .extract import extract_pages
from .iso_parser import parse_iso
from .parser import parse_norma
from .registry import REGISTRY, NormaMeta

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "normativas"
OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "parsed"

_DOC_LABEL = {
    "ley": "Ley",
    "decreto_aprobatorio": "Decreto Supremo aprobatorio",
    "reglamento": "Reglamento",
}

# "modificado por la Ley N° 30222, publicada el 11 de julio de 2014"
_MODIFICATORIA_RE = re.compile(
    r"(?P<tipo>Ley|Decreto Legislativo|Decreto Supremo|Resolución)\s*"
    r"N[°ºo]?\s*(?P<numero>[\d\-A-Za-z]+)"
    r"(?:[^.]*?publicad[oa]\s+el\s+(?P<fecha>\d{1,2}\s+de\s+\w+\s+de\s+\d{4}))?",
    re.IGNORECASE,
)


def _parse_modificatorias(nota: str | None) -> list[dict]:
    if not nota:
        return []
    out = []
    for m in _MODIFICATORIA_RE.finditer(nota):
        out.append(
            {
                "tipo": m.group("tipo").title(),
                "numero": m.group("numero"),
                "fecha_publicacion_texto": m.group("fecha"),
            }
        )
    return out


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


# Blocks are titled in the plural ("DISPOSICIONES COMPLEMENTARIAS FINALES"),
# but a citation names one of them, so it reads in the singular:
# "Primera Disposición Complementaria Final".
_SINGULAR = {
    "disposiciones": "Disposición",
    "disposición": "Disposición",
    "disposicion": "Disposición",
    "complementarias": "Complementaria",
    "transitorias": "Transitoria",
    "modificatorias": "Modificatoria",
    "derogatorias": "Derogatoria",
    "finales": "Final",
}


def _singularizar_bloque(bloque: str) -> str:
    partes = []
    for palabra in bloque.split():
        # Some titles combine several kinds ("DISPOSICIONES COMPLEMENTARIAS,
        # TRANSITORIAS Y FINALES"); keep the punctuation that joins them.
        nucleo = palabra.rstrip(",;.")
        sufijo = palabra[len(nucleo) :]
        if nucleo.lower() == "y":
            partes.append("y" + sufijo)
        else:
            partes.append(_SINGULAR.get(nucleo.lower(), nucleo.title()) + sufijo)
    return " ".join(partes)


def _unit_from_articulo(meta: NormaMeta, doc_tipo: str, art) -> dict:
    doc_label = _DOC_LABEL.get(doc_tipo, doc_tipo)
    norma_label = (
        f"{meta.nombre} (Ley {meta.numero})"
        if doc_tipo == "ley"
        else f"{doc_label} de la Ley {meta.numero}"
    )
    base_cita = f"Ley {meta.numero}" if doc_tipo == "ley" else f"{doc_label} de la Ley {meta.numero}"

    if art.tipo == "disposicion":
        bloque = art.bloque or "Disposiciones Complementarias"
        etiqueta = f"{art.numero.title()} {_singularizar_bloque(bloque)}"
        cita = f"{base_cita}, {etiqueta}"
        unit_id = f"{meta.norma_id}::{doc_tipo}::disp_{_slug(bloque)}_{_slug(art.numero)}"
        ubicacion = [bloque.title()]
    else:
        etiqueta = f"Artículo {art.numero}"
        cita = f"{base_cita}, Artículo {art.numero}"
        unit_id = f"{meta.norma_id}::{doc_tipo}::art_{art.numero}"
        ubicacion = []
        if art.titulo_numero:
            titulo_txt = f"Título {art.titulo_numero}"
            if art.titulo_capitulo:
                titulo_txt += f" — {art.titulo_capitulo}"
            ubicacion.append(titulo_txt)
        if art.capitulo:
            ubicacion.append(f"Capítulo {art.capitulo}")
        if art.seccion:
            ubicacion.append(f"Sección {art.seccion}")

    encabezado = " · ".join([norma_label] + ubicacion + [etiqueta])

    return {
        "id": unit_id,
        "tipo_unidad": art.tipo,
        "documento": doc_tipo,
        "numero": art.numero,
        "titulo": art.titulo,
        "texto": art.texto,
        "jerarquia": {
            "titulo": art.titulo_numero,
            "titulo_nombre": art.titulo_capitulo,
            "capitulo": art.capitulo,
            "seccion": art.seccion,
            "bloque": art.bloque,
        },
        "cita": cita,
        "vigente": art.vigente,
        "modificado_por_texto": art.modificado_por,
        "modificatorias": _parse_modificatorias(art.modificado_por),
        "texto_para_embedding": f"{encabezado}\n\n{art.texto}",
    }


def _unit_from_clausula(meta: NormaMeta, cl) -> dict:
    seccion = "Anexo A (orientación)" if cl.es_anexo else "Requisitos"
    encabezado = f"ISO {meta.numero} · {seccion} · Cláusula {cl.numero} {cl.titulo}"
    return {
        "id": f"{meta.norma_id}::clausula_{cl.numero}",
        "tipo_unidad": "clausula",
        "documento": "anexo" if cl.es_anexo else "requisitos",
        "numero": cl.numero,
        "titulo": cl.titulo,
        "texto": cl.texto,
        "jerarquia": {"nivel": cl.nivel, "es_anexo": cl.es_anexo},
        "cita": f"ISO {meta.numero}, cláusula {cl.numero}",
        "vigente": True,
        "modificado_por_texto": None,
        "modificatorias": [],
        "texto_para_embedding": f"{encabezado}\n\n{cl.texto}",
    }


def ingest_norma(meta: NormaMeta) -> dict:
    pages = extract_pages(str(RAW_DIR / meta.archivo))
    full_text = "\f".join(p.text for p in pages)
    n_ocr = sum(1 for p in pages if p.source == "ocr")

    unidades: list[dict] = []
    if meta.parser == "iso":
        unidades = [_unit_from_clausula(meta, c) for c in parse_iso(full_text)]
    else:
        for doc_tipo, articulos in parse_norma(full_text).items():
            unidades += [_unit_from_articulo(meta, doc_tipo, a) for a in articulos]

    return {
        "norma_id": meta.norma_id,
        "tipo": meta.tipo,
        "numero": meta.numero,
        "nombre": meta.nombre,
        "materia": meta.materia,
        "entidad_reguladora": meta.entidad_reguladora,
        "fecha_publicacion": meta.fecha_publicacion,
        "url_fuente": meta.url_fuente,
        "metadata_verificada": meta.metadata_verificada,
        "notas": meta.notas,
        "extraccion": {
            "archivo": meta.archivo,
            "paginas": len(pages),
            "paginas_ocr": n_ocr,
            "requiere_cotejo": n_ocr > 0,
        },
        "unidades": unidades,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="norma_id to ingest (default: all)")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for meta in REGISTRY:
        if args.only and meta.norma_id != args.only:
            continue
        print(f"Ingesting {meta.norma_id} ...", flush=True)
        data = ingest_norma(meta)
        out_path = OUT_DIR / f"{meta.norma_id}.json"
        out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        by_doc: dict[str, dict[str, int]] = {}
        for u in data["unidades"]:
            counts = by_doc.setdefault(u["documento"], {})
            counts[u["tipo_unidad"]] = counts.get(u["tipo_unidad"], 0) + 1
        detail = "; ".join(
            f"{doc}: " + ", ".join(f"{n} {t}" for t, n in counts.items())
            for doc, counts in by_doc.items()
        )
        print(
            f"  -> {out_path.name}: {len(data['unidades'])} unidades ({detail})"
            f"{'  [OCR]' if data['extraccion']['paginas_ocr'] else ''}"
        )


if __name__ == "__main__":
    main()
