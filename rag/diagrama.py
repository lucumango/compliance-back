"""Generación de diagramas Mermaid a partir de la respuesta.

Solo tiene sentido cuando la consulta es procedimental ("¿qué hago si...?",
"¿cómo se tramita...?"), donde un árbol de decisión comunica mejor que un
párrafo. Para una consulta de definición un diagrama es ruido, así que primero
se decide si corresponde.

El diagrama se deriva del texto ya recuperado y respondido: no introduce pasos
nuevos, solo estructura los que la respuesta ya sostiene con citas.
"""

from __future__ import annotations

import re

from .gemini import generar

_PROMPT = """A partir de la respuesta normativa siguiente, genera UN diagrama \
Mermaid que estructure el procedimiento o el árbol de decisión que describe.

Reglas:
- Usa `flowchart TD`.
- No inventes pasos que la respuesta no mencione.
- Etiquetas cortas, en español, sin comillas dobles dentro del texto del nodo.
- Máximo 12 nodos.
- Si la respuesta NO describe un procedimiento ni una decisión, responde \
exactamente: NO_APLICA
- Devuelve solo el código Mermaid, sin explicación ni cercos de markdown.

RESPUESTA:
{respuesta}"""

# Consultas procedimentales: las que preguntan por un curso de acción.
# Los verbos van por raíz seguida de \w*, porque conjugan ("tramita",
# "reportar", "notifico"); cerrar con \b tras la raíz nunca casaría.
_SENALES = re.compile(
    r"\b(?:qu[ée]\s+hago|qu[ée]\s+debo"
    r"|c[óo]mo\s+(?:se\s+)?(?:hag\w*|hac\w*|tramit\w*|proced\w*|report\w*|notific\w*|denunci\w*|solicit\w*)"
    r"|pasos|procedimiento|proceso|flujo|tr[áa]mite|cu[áa]ndo\s+debo"
    r"|qu[ée]\s+pasa\s+si|en\s+caso\s+de|si\s+ocurre)",
    re.IGNORECASE,
)


def amerita_diagrama(consulta: str) -> bool:
    return bool(_SENALES.search(consulta))


def _limpiar(salida: str) -> str | None:
    texto = salida.strip()
    if "NO_APLICA" in texto.upper():
        return None
    # El modelo a veces devuelve el código dentro de cercos de markdown.
    texto = re.sub(r"^```(?:mermaid)?\s*", "", texto)
    texto = re.sub(r"\s*```$", "", texto).strip()
    if not texto.lower().startswith(("flowchart", "graph")):
        return None
    return texto


def generar_diagrama(respuesta: str) -> str | None:
    try:
        return _limpiar(generar(_PROMPT.format(respuesta=respuesta[:4000])))
    except Exception:
        # Un diagrama es un extra; si falla, la respuesta con citas sigue
        # siendo el producto y no debe caerse por esto.
        return None
