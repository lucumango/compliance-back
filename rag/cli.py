"""Consulta el asistente desde la terminal.

    python -m rag.cli "¿Cuál es la multa por una infracción muy grave?"
    python -m rag.cli            # modo interactivo
"""

from __future__ import annotations

import sys

from .answer import responder
from .retrieval import Buscador

_DESCARGO = (
    "Este asistente informa sobre normativa; no constituye asesoría legal. "
    "Verifica siempre contra la fuente oficial."
)


def _mostrar(resp) -> None:
    print()
    print(resp.texto)
    print()
    if resp.diagrama:
        print("Diagrama (Mermaid):")
        print(resp.diagrama)
        print()
    if resp.fuentes:
        print("Fuentes:")
        for i, r in enumerate(resp.fuentes, 1):
            print(f"  [F{i}] {r.unidad.cita}  (similitud {r.score:.3f})")
    if resp.advertencias:
        print("\nAdvertencias:")
        for a in resp.advertencias:
            print(f"  ! {a}")
    print(f"\n{_DESCARGO}")


def main() -> int:
    buscador = Buscador()

    if len(sys.argv) > 1:
        _mostrar(responder(" ".join(sys.argv[1:]), buscador))
        return 0

    print(f"Asistente de compliance. Ctrl-C para salir.\n{_DESCARGO}")
    while True:
        try:
            consulta = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if consulta:
            _mostrar(responder(consulta, buscador))


if __name__ == "__main__":
    sys.exit(main())
