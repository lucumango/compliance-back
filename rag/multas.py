"""Calculadora de multas parametrizada por UIT.

Dos principios que vienen del plan de producto:

1. **La UIT es configuración, no constante.** Cambia cada año por decreto
   supremo, y una multa calculada con la UIT equivocada está mal. Se lee de
   `data/uit.json`, donde cada valor lleva la norma que lo fijó.

2. **Los rangos salen del corpus, no de la memoria.** Cada régimen apunta al
   artículo que establece la escala, de modo que la estimación siempre puede
   rastrearse hasta su fuente.

La salida es una *estimación de impacto*, nunca una determinación de sanción:
la autoridad gradúa el monto dentro del rango según criterios propios.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .config import BASE_DIR

UIT_PATH = BASE_DIR / "data" / "uit.json"


@dataclass
class Rango:
    gravedad: str
    min_uit: float
    max_uit: float


@dataclass
class Regimen:
    id: str
    nombre: str
    norma_id: str
    articulo_cita: str
    rangos: dict[str, Rango]
    tope_adicional: str | None = None


@dataclass
class Estimacion:
    regimen: str
    gravedad: str
    anio_uit: int
    valor_uit: float
    fuente_uit: str
    min_soles: float
    max_soles: float
    rango_uit: tuple[float, float]
    fuente_rango: str
    tope_adicional: str | None
    advertencia: str


# Escalas transcritas del artículo que las fija. Al ampliar el corpus, cada
# régimen nuevo debe declarar el artículo del que sale su escala.
REGIMENES: dict[str, Regimen] = {
    "proteccion_datos": Regimen(
        id="proteccion_datos",
        nombre="Protección de datos personales",
        norma_id="ley_29733",
        articulo_cita="Ley 29733, Artículo 39",
        rangos={
            "leve": Rango("leve", 0.5, 5),
            "grave": Rango("grave", 5, 50),
            "muy_grave": Rango("muy_grave", 50, 100),
        },
        tope_adicional=(
            "La multa no puede exceder del 10% de los ingresos brutos anuales "
            "percibidos por el infractor durante el ejercicio anterior "
            "(Ley 29733, Artículo 39)."
        ),
    ),
}


def cargar_uit() -> dict:
    if not UIT_PATH.exists():
        raise FileNotFoundError(
            f"Falta {UIT_PATH}. Debe listar la UIT por año con la norma que la fija."
        )
    return json.loads(UIT_PATH.read_text())


def uit_vigente(anio: int | None = None) -> tuple[int, float, str]:
    """Devuelve (año, valor, fuente). Sin año, usa el más reciente cargado."""
    data = cargar_uit()
    valores = data["valores"]
    if anio is None:
        anio = max(int(a) for a in valores)
    clave = str(anio)
    if clave not in valores:
        disponibles = ", ".join(sorted(valores))
        raise KeyError(f"No hay UIT cargada para {anio}. Disponibles: {disponibles}")
    entrada = valores[clave]
    return anio, float(entrada["valor"]), entrada["fuente"]


def estimar(
    regimen_id: str, gravedad: str, anio: int | None = None
) -> Estimacion:
    if regimen_id not in REGIMENES:
        disponibles = ", ".join(REGIMENES)
        raise KeyError(f"Régimen '{regimen_id}' no cargado. Disponibles: {disponibles}")

    regimen = REGIMENES[regimen_id]
    clave = gravedad.lower().replace(" ", "_")
    if clave not in regimen.rangos:
        disponibles = ", ".join(regimen.rangos)
        raise KeyError(f"Gravedad '{gravedad}' no válida. Disponibles: {disponibles}")

    rango = regimen.rangos[clave]
    anio_uit, valor_uit, fuente_uit = uit_vigente(anio)

    return Estimacion(
        regimen=regimen.nombre,
        gravedad=clave,
        anio_uit=anio_uit,
        valor_uit=valor_uit,
        fuente_uit=fuente_uit,
        min_soles=round(rango.min_uit * valor_uit, 2),
        max_soles=round(rango.max_uit * valor_uit, 2),
        rango_uit=(rango.min_uit, rango.max_uit),
        fuente_rango=regimen.articulo_cita,
        tope_adicional=regimen.tope_adicional,
        advertencia=(
            "Estimación de impacto, no una determinación de sanción. La "
            "autoridad gradúa el monto dentro del rango según los criterios "
            "del artículo 230 de la Ley 27444."
        ),
    )
