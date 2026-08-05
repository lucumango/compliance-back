"""Registry of the corpus documents.

Deliberately conservative: only fields that can be read off the source PDF are
filled in. `fecha_publicacion` and `url_fuente` stay None until verified
against SPIJ / El Peruano, and `metadata_verificada` records that state. In a
compliance product an invented date is worse than a missing one, so nothing
here is asserted from memory.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class NormaMeta:
    norma_id: str
    archivo: str
    tipo: str  # "ley" | "norma_tecnica"
    numero: str
    nombre: str
    materia: str
    entidad_reguladora: list[str]
    parser: str  # "ley" | "iso"
    fecha_publicacion: str | None = None
    url_fuente: str | None = None
    metadata_verificada: bool = False
    notas: str = ""


REGISTRY: list[NormaMeta] = [
    NormaMeta(
        norma_id="ley_29733",
        archivo="ley_29733.pdf",
        tipo="ley",
        numero="29733",
        nombre="Ley de Protección de Datos Personales",
        materia="proteccion_datos",
        entidad_reguladora=["ANPD", "MINJUSDH"],
        parser="ley",
        notas=(
            "Texto consolidado (Editora Perú). Incluye el Reglamento aprobado "
            "por DS 003-2013-JUS como documento anexo."
        ),
    ),
    NormaMeta(
        norma_id="ley_29783",
        archivo="ley_29783.pdf",
        tipo="ley",
        numero="29783",
        nombre="Ley de Seguridad y Salud en el Trabajo",
        materia="sst_laboral",
        entidad_reguladora=["SUNAFIL", "MTPE"],
        parser="ley",
        notas=(
            "Texto consolidado actualizado al 28/04/2022 según portada. "
            "Incluye el Reglamento aprobado por DS 005-2012-TR."
        ),
    ),
    NormaMeta(
        norma_id="ley_27693",
        archivo="ley_27693.pdf",
        tipo="ley",
        numero="27693",
        nombre="Ley que crea la Unidad de Inteligencia Financiera - Perú",
        materia="laft",
        entidad_reguladora=["SBS", "UIF-Perú"],
        parser="ley",
        notas=(
            "Escaneo de El Peruano procesado por OCR; el texto puede contener "
            "errores de reconocimiento y requiere cotejo con SPIJ."
        ),
    ),
    NormaMeta(
        norma_id="ley_30424",
        archivo="ley_30424.pdf",
        tipo="ley",
        numero="30424",
        nombre=(
            "Ley que regula la responsabilidad administrativa de las personas "
            "jurídicas por el delito de cohecho activo transnacional"
        ),
        materia="anticorrupcion",
        entidad_reguladora=["MINJUSDH", "Ministerio Público"],
        parser="ley",
        fecha_publicacion="2016-04-21",  # leído de la cabecera del escaneo
        notas=(
            "Texto ORIGINAL publicado el 21/04/2016, sin las modificatorias "
            "posteriores (p. ej. Ley 30835, Ley 31740). No usar como texto "
            "vigente sin actualizar."
        ),
    ),
    NormaMeta(
        norma_id="iso_37001",
        archivo="iso_37001.pdf",
        tipo="norma_tecnica",
        numero="37001:2016",
        nombre="Sistemas de gestión antisoborno — Requisitos con orientación para su uso",
        materia="antisoborno",
        entidad_reguladora=[],
        parser="iso",
        fecha_publicacion="2016-10-15",  # leído de la portada
        notas=(
            "Traducción oficial al español. Documento con copyright ISO: uso "
            "interno del proyecto; no redistribuir el texto íntegro."
        ),
    ),
]
