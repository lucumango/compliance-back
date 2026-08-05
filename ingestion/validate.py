"""Quality checks over the parsed JSON corpus.

These are the failure modes that actually bit during development: page
furniture bleeding into article bodies, an article swallowing the next one's
header, empty units, and gaps in the article numbering. A compliance answer is
only as trustworthy as the chunk it cites, so these run over the whole corpus
rather than a sample.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

PARSED_DIR = Path(__file__).resolve().parent.parent / "data" / "parsed"

# Anchored to whole lines: running heads occupy a line of their own, whereas
# "Los cambios en las normas legales." is genuine statutory text.
_FURNITURE_SIGNS = [
    re.compile(r"^[ \t]*NORMAS LEGALES.*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^.*El Peruano\s*/.*$", re.MULTILINE),
    re.compile(r"^[ \t]*Licensed to .*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^[ \t]*ISO Store Order.*$", re.IGNORECASE | re.MULTILINE),
]
# An article body should not begin the *next* article.
_TRAILING_HEADER = re.compile(r"\n\s*(?:Art[íi]culo\s+\d+\s*[°ºª\*]?\s*[.\-–])\s*$")
_MIN_TEXT_CHARS = 25


def _is_container(unit: dict, unidades: list[dict], idx: int) -> bool:
    """An ISO clause like "7 Apoyo" holds no prose of its own. All its
    content lives in 7.1, 7.2, ... A short body is correct there, so only
    flag it when no child clause follows."""
    if unit["tipo_unidad"] != "clausula" or idx + 1 >= len(unidades):
        return False
    return str(unidades[idx + 1]["numero"]).startswith(f"{unit['numero']}.")


def check_file(path: Path) -> list[str]:
    data = json.loads(path.read_text())
    problems: list[str] = []
    norma = data["norma_id"]

    unidades = data["unidades"]
    for idx, u in enumerate(unidades):
        texto = u["texto"]
        uid = u["id"]

        if len(texto.strip()) < _MIN_TEXT_CHARS and not _is_container(u, unidades, idx):
            problems.append(f"{uid}: texto sospechosamente corto ({len(texto)} chars)")

        for pattern in _FURNITURE_SIGNS:
            if pattern.search(texto):
                snippet = pattern.search(texto).group(0)
                problems.append(f"{uid}: contiene texto de página repetido ({snippet!r})")
                break

        if _TRAILING_HEADER.search(texto):
            problems.append(f"{uid}: termina con el encabezado del artículo siguiente")

        if not u["cita"]:
            problems.append(f"{uid}: sin cita")

    # article numbering must be gapless within each documento
    by_doc: dict[str, list[int]] = {}
    for u in data["unidades"]:
        if u["tipo_unidad"] != "articulo":
            continue
        m = re.match(r"^\d+", str(u["numero"]))
        if m:
            by_doc.setdefault(u["documento"], []).append(int(m.group()))

    for doc, nums in by_doc.items():
        expected = list(range(1, max(nums) + 1))
        missing = sorted(set(expected) - set(nums))
        if missing:
            problems.append(f"{norma}/{doc}: artículos faltantes {missing}")
        dupes = sorted({n for n in nums if nums.count(n) > 1})
        if dupes:
            problems.append(f"{norma}/{doc}: artículos duplicados {dupes}")

    return problems


def main() -> int:
    files = sorted(PARSED_DIR.glob("*.json"))
    if not files:
        print("No hay archivos parseados. Corre: python -m ingestion.ingest")
        return 1

    total_units = 0
    total_problems = 0
    for path in files:
        data = json.loads(path.read_text())
        total_units += len(data["unidades"])
        problems = check_file(path)
        total_problems += len(problems)
        status = "OK" if not problems else f"{len(problems)} PROBLEMAS"
        print(f"{path.stem}: {len(data['unidades'])} unidades — {status}")
        for p in problems[:15]:
            print(f"    - {p}")
        if len(problems) > 15:
            print(f"    ... y {len(problems) - 15} más")

    print(f"\nTotal: {total_units} unidades, {total_problems} problemas")
    return 0 if total_problems == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
