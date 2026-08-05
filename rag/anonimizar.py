"""Anonimización de PII antes de enviar la consulta al LLM.

El usuario típico redacta consultas con datos reales ("el trabajador Juan Pérez,
DNI 45678912, denunció..."). Esos datos no necesitan salir del entorno para que
el modelo responda una pregunta normativa, así que se enmascaran antes de la
llamada y se restauran en la respuesta.

Es una defensa de superficie, no una garantía: reconoce patrones estructurados
(DNI, RUC, correos, teléfonos, montos, tarjetas), no nombres arbitrarios.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# El orden importa: RUC (11 dígitos) debe intentarse antes que DNI (8), y el
# correo antes que cualquier patrón numérico que pudiera partirlo.
_PATRONES: list[tuple[str, re.Pattern]] = [
    ("CORREO", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("RUC", re.compile(r"\b(?:10|15|16|17|20)\d{9}\b")),
    ("TARJETA", re.compile(r"\b(?:\d{4}[ -]?){3}\d{4}\b")),
    ("DNI", re.compile(r"\b\d{8}\b")),
    ("TELEFONO", re.compile(r"\b(?:\+51[ -]?)?9\d{8}\b")),
    ("CUENTA", re.compile(r"\b\d{13,20}\b")),
    ("MONTO", re.compile(r"(?:S/\.?|USD|\$)\s?\d[\d,.]*")),
]


@dataclass
class Anonimizacion:
    texto: str
    reemplazos: dict[str, str] = field(default_factory=dict)

    def restaurar(self, texto: str) -> str:
        """Devuelve los valores originales a la respuesta del modelo."""
        for marcador, original in self.reemplazos.items():
            texto = texto.replace(marcador, original)
        return texto


def anonimizar(texto: str) -> Anonimizacion:
    reemplazos: dict[str, str] = {}
    contadores: dict[str, int] = {}

    def sustituir(match: re.Match, etiqueta: str) -> str:
        original = match.group(0)
        # El mismo valor repetido recibe el mismo marcador, para que el modelo
        # pueda razonar sobre que se trata de la misma persona o entidad.
        for marcador, valor in reemplazos.items():
            if valor == original:
                return marcador
        contadores[etiqueta] = contadores.get(etiqueta, 0) + 1
        marcador = f"[{etiqueta}_{contadores[etiqueta]}]"
        reemplazos[marcador] = original
        return marcador

    resultado = texto
    for etiqueta, patron in _PATRONES:
        resultado = patron.sub(lambda m, e=etiqueta: sustituir(m, e), resultado)

    return Anonimizacion(texto=resultado, reemplazos=reemplazos)
