"""Composición de la respuesta: recuperar, anclar y responder con citas.

La regla central del producto es que ninguna afirmación normativa puede salir
sin estar anclada a un artículo recuperado. Cuando el corpus no cubre la
consulta, la respuesta correcta es decirlo -- no completar con conocimiento
general del modelo, que es exactamente donde un asistente de compliance se
vuelve peligroso.
"""

from __future__ import annotations

from dataclasses import dataclass

from typing import Iterator

from .anonimizar import anonimizar
from .diagrama import amerita_diagrama, generar_diagrama
from .gemini import generar, generar_stream
from .retrieval import Buscador, Resultado

_SISTEMA = """Eres un asistente de normativa y compliance del Perú. Respondes \
únicamente a partir de las FUENTES entregadas.

Reglas estrictas:
1. Cada afirmación normativa debe citar su fuente con la etiqueta exacta entre \
corchetes, por ejemplo [F1] o [F3]. No inventes etiquetas.
2. Si las fuentes no responden la consulta, dilo explícitamente: "El corpus \
cargado no contiene una respuesta a esto" e indica qué norma habría que revisar. \
No completes con conocimiento propio.
3. No des asesoría legal. Informas y remites a la fuente para que un \
profesional valide.
4. Si citas un plazo, un monto o un porcentaje, transcríbelo tal como aparece \
en la fuente. Nunca lo estimes ni lo redondees.
5. Responde en español, de forma concreta y estructurada. Si la consulta implica \
pasos, enuméralos.

FUENTES:
{fuentes}

CONSULTA: {consulta}"""


@dataclass
class Respuesta:
    texto: str
    fuentes: list[Resultado]
    advertencias: list[str]
    diagrama: str | None = None


def _formatear_fuentes(resultados: list[Resultado]) -> str:
    bloques = []
    for i, r in enumerate(resultados, 1):
        u = r.unidad
        estado = "" if u.vigente else " [MARCADA COMO NO VIGENTE]"
        bloques.append(f"[F{i}] {u.cita}{estado}\n{u.texto}")
    return "\n\n---\n\n".join(bloques)


def _advertencias(resultados: list[Resultado]) -> list[str]:
    avisos: list[str] = []
    normas_vistas: set[str] = set()

    for r in resultados:
        u = r.unidad
        if u.norma_id in normas_vistas:
            continue
        normas_vistas.add(u.norma_id)

        if u.requiere_cotejo:
            avisos.append(
                f"{u.norma_nombre}: el texto proviene de un escaneo procesado con "
                f"OCR y debe cotejarse con la fuente oficial (SPIJ / El Peruano)."
            )
        if "original" in u.notas_norma.lower():
            avisos.append(f"{u.norma_nombre}: {u.notas_norma}")

    return avisos


def responder(
    consulta: str,
    buscador: Buscador,
    k: int = 6,
    materias: list[str] | None = None,
    con_diagrama: bool = True,
) -> Respuesta:
    # La consulta puede traer datos reales del caso; se enmascaran antes de
    # salir del entorno y se restauran al devolver la respuesta.
    anon = anonimizar(consulta)

    resultados = buscador.buscar(anon.texto, k=k, materias=materias)
    if not resultados:
        return Respuesta(
            texto="El corpus cargado no contiene información sobre esta consulta.",
            fuentes=[],
            advertencias=[],
        )

    prompt = _SISTEMA.format(
        fuentes=_formatear_fuentes(resultados), consulta=anon.texto
    )
    texto = anon.restaurar(generar(prompt))

    diagrama = None
    if con_diagrama and amerita_diagrama(consulta):
        diagrama = generar_diagrama(texto)

    return Respuesta(
        texto=texto,
        fuentes=resultados,
        advertencias=_advertencias(resultados),
        diagrama=diagrama,
    )


@dataclass
class Preparacion:
    """Todo lo que se sabe antes de empezar a generar: las fuentes ya
    recuperadas y los avisos que las acompañan. Se envía al cliente de
    inmediato, para que el panel de citas se pinte mientras se redacta."""

    prompt: str
    fuentes: list[Resultado]
    advertencias: list[str]
    anonimizacion: object
    lleva_diagrama: bool


def preparar(
    consulta: str,
    buscador: Buscador,
    k: int = 6,
    materias: list[str] | None = None,
    con_diagrama: bool = True,
) -> Preparacion:
    anon = anonimizar(consulta)
    resultados = buscador.buscar(anon.texto, k=k, materias=materias)

    return Preparacion(
        prompt=_SISTEMA.format(
            fuentes=_formatear_fuentes(resultados), consulta=anon.texto
        )
        if resultados
        else "",
        fuentes=resultados,
        advertencias=_advertencias(resultados),
        anonimizacion=anon,
        lleva_diagrama=con_diagrama and amerita_diagrama(consulta),
    )


def responder_stream(prep: Preparacion) -> Iterator[str]:
    """Emite la respuesta por fragmentos.

    La restauración de PII se aplica a cada fragmento. Un marcador podría
    quedar partido entre dos fragmentos y no restaurarse; se acepta porque
    romper un marcador solo deja visible el texto enmascarado, nunca revela
    el dato original.
    """
    if not prep.fuentes:
        yield "El corpus cargado no contiene información sobre esta consulta."
        return

    for fragmento in generar_stream(prep.prompt):
        yield prep.anonimizacion.restaurar(fragmento)
