"""Parse ISO 37001 into its numbered clauses.

Unlike a Peruvian ley, an ISO standard is organised as decimal-numbered
clauses ("4.1", "5.3.2") plus a guidance annex ("A.8.4"), so it needs its own
marker grammar. Output shape mirrors ingestion.parser.Articulo closely enough
that both feed the same downstream chunker.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .parser import clean_text

# Boilerplate stamped on every page of the licensed PDF. Left in place it
# lands inside clause bodies and pollutes the embeddings.
_FURNITURE_PATTERNS = [
    r"^\s*Licensed to .*$",
    r"^\s*ISO Store Order:.*$",
    r"^\s*Single user licence only.*$",
    r"^\s*Traducci[óo]n oficial/Official translation/Traduction officielle\s*$",
    r"^\s*©\s*ISO 2016.*$",
    r"^\s*ISO 37001:2016 \(traducci[óo]n\s*oficial\)\s*$",
    r"^\s*NORMA INTERNACIONAL\s*$",
    r"^\s*ICS\s.*$",
    r"^\s*Precio basado en.*$",
    r"^\s*\d{1,3}\s*$",  # bare page numbers
]
_FURNITURE_RE = re.compile("|".join(_FURNITURE_PATTERNS), re.MULTILINE)

# "4.1 Comprensión de la organización" / "A.8.4 Soborno al personal"
_CLAUSE_RE = re.compile(
    r"^(A\.\d+(?:\.\d+)*|\d+(?:\.\d+)*)\s+(\S.{0,120})$", re.MULTILINE
)

_BODY_START_RE = re.compile(r"^1\s+Objeto y campo de aplicaci[óo]n\s*$", re.MULTILINE)
_BIBLIOGRAPHY_RE = re.compile(r"^Bibliograf[íi]a\s*$", re.MULTILINE)


@dataclass
class Clausula:
    numero: str  # "4.1", "A.8.4"
    titulo: str
    texto: str
    nivel: int  # 1 for "4", 2 for "4.1", 3 for "4.1.1"
    es_anexo: bool


def _strip_furniture(text: str) -> str:
    text = text.replace("﻿", "").replace("\xa0", " ").replace(" ", " ")
    text = _FURNITURE_RE.sub("", text)
    return re.sub(r"\n{3,}", "\n\n", text)


def _body_slice(text: str) -> str:
    """Drop the cover, table of contents, prólogo and introducción (which
    repeat the clause titles and would otherwise produce phantom clauses),
    and drop the trailing bibliography."""
    start_match = _BODY_START_RE.search(text)
    start = start_match.start() if start_match else 0

    biblio_matches = list(_BIBLIOGRAPHY_RE.finditer(text))
    end = biblio_matches[-1].start() if biblio_matches else len(text)
    return text[start:end]


def parse_iso(raw_text: str) -> list[Clausula]:
    text = _body_slice(_strip_furniture(clean_text(raw_text)))
    matches = list(_CLAUSE_RE.finditer(text))

    clausulas: list[Clausula] = []
    for i, m in enumerate(matches):
        numero = m.group(1)
        titulo = m.group(2).strip()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[m.end() : end].strip()

        es_anexo = numero.startswith("A.")
        nivel = numero.count(".") + (0 if es_anexo else 1)

        clausulas.append(
            Clausula(
                numero=numero,
                titulo=titulo,
                texto=f"{titulo}\n{body}".strip(),
                nivel=nivel,
                es_anexo=es_anexo,
            )
        )
    return clausulas
