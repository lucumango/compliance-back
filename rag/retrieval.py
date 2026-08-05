"""Recuperación sobre el índice vectorial."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .gemini import embed_query
from .index import Unidad, cargar


@dataclass
class Resultado:
    unidad: Unidad
    score: float


class Buscador:
    def __init__(self) -> None:
        self.matriz, self.unidades = cargar()

    def buscar(
        self,
        consulta: str,
        k: int = 8,
        materias: list[str] | None = None,
        score_minimo: float = 0.0,
    ) -> list[Resultado]:
        vector = np.array(embed_query(consulta), dtype=np.float32)
        vector /= np.linalg.norm(vector)

        # La matriz ya está normalizada al indexar, así que el producto punto
        # es directamente la similitud coseno.
        scores = self.matriz @ vector

        if materias:
            permitidas = set(materias)
            mascara = np.array(
                [u.materia in permitidas for u in self.unidades], dtype=bool
            )
            scores = np.where(mascara, scores, -np.inf)

        # argpartition evita ordenar los 701 scores para quedarnos con k.
        n = min(k, int(np.isfinite(scores).sum()))
        if n == 0:
            return []
        candidatos = np.argpartition(-scores, n - 1)[:n]
        candidatos = candidatos[np.argsort(-scores[candidatos])]

        return [
            Resultado(unidad=self.unidades[i], score=float(scores[i]))
            for i in candidatos
            if scores[i] >= score_minimo
        ]
