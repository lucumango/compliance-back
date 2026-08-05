"""Evaluación de recuperación sobre consultas de referencia.

Comprueba que la unidad correcta aparece entre las recuperadas. Es barato
(solo embeddings, sin generación) y por eso puede correrse en cada cambio del
parser, del texto indexado o del modelo de embeddings, que es justo cuando la
recuperación se degrada sin que nadie lo note.

El caso `esperado=None` es tan importante como los demás: verifica que el
corpus NO contenga una respuesta y que el sistema deba admitirlo.
"""

from __future__ import annotations

import sys

from .retrieval import Buscador

# (consulta, id de unidad que debe aparecer, k)
CASOS: list[tuple[str, str | None, int]] = [
    (
        "¿Cuál es la multa máxima por una infracción muy grave en protección de datos?",
        "ley_29733::ley::art_39",
        3,
    ),
    (
        "¿Qué derechos puede ejercer el titular sobre sus datos personales?",
        "ley_29733::ley::art_19",
        8,
    ),
    (
        "¿Cada cuánto deben hacerse las auditorías del sistema de gestión de SST?",
        "ley_29783::ley::art_43",
        3,
    ),
    (
        "¿Quiénes integran el comité de seguridad y salud en el trabajo?",
        "ley_29783::ley::art_29",
        8,
    ),
    (
        "¿Qué medidas administrativas se aplican a la persona jurídica por cohecho?",
        "ley_30424::ley::art_5",
        3,
    ),
    (
        "¿Cuándo debe comunicarse una transacción sospechosa a la UIF?",
        "ley_27693::ley::art_11",
        5,
    ),
    (
        "¿Qué exige la norma sobre debida diligencia de socios de negocios?",
        "iso_37001::clausula_8.2",
        5,
    ),
    (
        "¿Qué debe incluir la política antisoborno de la organización?",
        "iso_37001::clausula_5.2",
        5,
    ),
]


def main() -> int:
    buscador = Buscador()
    fallos = 0

    for consulta, esperado, k in CASOS:
        resultados = buscador.buscar(consulta, k=k)
        ids = [r.unidad.id for r in resultados]
        ok = esperado in ids

        estado = "OK  " if ok else "FALLA"
        print(f"[{estado}] {consulta}")
        if not ok:
            fallos += 1
            print(f"         esperado: {esperado}")
            print(f"         obtenido: {ids[:k]}")
        else:
            pos = ids.index(esperado) + 1
            print(f"         {esperado} en posición {pos}/{k}")

    print(f"\n{len(CASOS) - fallos}/{len(CASOS)} casos correctos")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
