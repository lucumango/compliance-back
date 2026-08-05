"""Cliente mínimo de la API de Gemini: embeddings y generación.

Sin SDK a propósito: la superficie que usamos son dos endpoints, y evitar la
dependencia mantiene el proyecto instalable con solo la librería estándar más
numpy. El manejo de 429 sí es necesario, porque el plan gratuito los devuelve al
indexar el corpus completo.
"""

from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.request
from typing import Iterator

from .config import (
    API_BASE,
    MODEL_EMBEDDING,
    MODEL_GENERACION,
    MODELOS_GENERACION,
    get_api_key,
)

_MAX_REINTENTOS = 6
_BASE_ESPERA = 2.0
# La API rechaza lotes grandes; 100 es el máximo documentado por llamada.
BATCH_MAX = 100

# El streaming es interactivo: alguien está esperando delante de la pantalla.
# Con los reintentos del indexado (6 intentos x 180 s) un modelo saturado deja
# la petición colgada 19 minutos, que es peor que fallar pronto. El timeout se
# aplica por operación de socket, no al total, así que 60 s significa "60 s sin
# recibir nada", de sobra cuando los fragmentos llegan cada pocos cientos de
# milisegundos.
_STREAM_MAX_REINTENTOS = 3
_STREAM_TIMEOUT = 60


class GeminiError(RuntimeError):
    pass


def _post(path: str, payload: dict, timeout: int = 180) -> dict:
    url = f"{API_BASE}/{path}?key={get_api_key()}"
    data = json.dumps(payload).encode()

    for intento in range(_MAX_REINTENTOS):
        req = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            cuerpo = e.read().decode(errors="replace")[:400]
            # 429 = cuota; 5xx = fallo transitorio. Ambos se reintentan con
            # espera exponencial y jitter para no sincronizar los reintentos.
            if e.code in (429, 500, 503) and intento < _MAX_REINTENTOS - 1:
                espera = _BASE_ESPERA * (2**intento) + random.uniform(0, 1)
                time.sleep(espera)
                continue
            raise GeminiError(f"HTTP {e.code} en {path}: {cuerpo}") from e
        except (TimeoutError, OSError) as e:
            # OSError cubre URLError y también socket.timeout, que no hereda de
            # URLError y por tanto escapaba de un manejador más específico.
            if intento < _MAX_REINTENTOS - 1:
                time.sleep(_BASE_ESPERA * (2**intento))
                continue
            raise GeminiError(f"Error de red en {path}: {e}") from e

    raise GeminiError(f"Se agotaron los reintentos en {path}")


def embed_batch(textos: list[str], task_type: str = "RETRIEVAL_DOCUMENT") -> list[list[float]]:
    """Vectoriza hasta BATCH_MAX textos en una sola llamada.

    task_type distingue el lado del índice (RETRIEVAL_DOCUMENT) del lado de la
    consulta (RETRIEVAL_QUERY); el modelo los proyecta distinto y usar el
    equivocado degrada la recuperación.
    """
    if not textos:
        return []
    if len(textos) > BATCH_MAX:
        raise ValueError(f"Lote de {len(textos)} excede el máximo de {BATCH_MAX}")

    payload = {
        "requests": [
            {
                "model": f"models/{MODEL_EMBEDDING}",
                "content": {"parts": [{"text": t}]},
                "taskType": task_type,
            }
            for t in textos
        ]
    }
    data = _post(f"models/{MODEL_EMBEDDING}:batchEmbedContents", payload)
    return [e["values"] for e in data["embeddings"]]


def embed_query(texto: str) -> list[float]:
    return embed_batch([texto], task_type="RETRIEVAL_QUERY")[0]


# Cuota agotada = agotada durante un buen rato. Sin recordarlo, cada petición
# vuelve a gastar sus reintentos contra el modelo caído antes de degradar, lo
# que añadía ~9 s al primer fragmento. El olvido es deliberado: al reiniciar el
# proceso se vuelve a intentar el modelo bueno.
_ENFRIAMIENTO_SEG = 15 * 60
_modelos_en_espera: dict[str, float] = {}


def _marcar_agotado(modelo: str) -> None:
    _modelos_en_espera[modelo] = time.time() + _ENFRIAMIENTO_SEG


def _disponible(modelo: str) -> bool:
    hasta = _modelos_en_espera.get(modelo)
    if hasta is None:
        return True
    if time.time() >= hasta:
        del _modelos_en_espera[modelo]
        return True
    return False


def _cadena_modelos(modelo: str | None) -> list[str]:
    """Un modelo explícito se respeta tal cual; si no, se usa la cadena de
    respaldo para sobrevivir al agotamiento de cuota por modelo."""
    if modelo:
        return [modelo]
    disponibles = [m for m in MODELOS_GENERACION if _disponible(m)]
    # Si todos están en enfriamiento, más vale reintentar que no responder.
    return disponibles or MODELOS_GENERACION


def generar(prompt: str, temperatura: float = 0.2, modelo: str | None = None) -> str:
    """Genera una respuesta. Temperatura baja por defecto: en compliance
    interesa la fidelidad al texto recuperado, no la variedad."""
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperatura},
    }

    cadena = _cadena_modelos(modelo)
    ultimo_error: GeminiError | None = None

    for candidato_modelo in cadena:
        try:
            data = _post(f"models/{candidato_modelo}:generateContent", payload)
        except GeminiError as e:
            ultimo_error = e
            continue

        candidatos = data.get("candidates") or []
        if not candidatos:
            ultimo_error = GeminiError(
                f"Respuesta sin candidatos: {json.dumps(data)[:300]}"
            )
            continue

        partes = candidatos[0].get("content", {}).get("parts") or []
        texto = "".join(p.get("text", "") for p in partes).strip()
        if texto:
            return texto
        ultimo_error = GeminiError(
            f"Respuesta vacía (finishReason={candidatos[0].get('finishReason', 'desconocido')})"
        )

    raise ultimo_error or GeminiError("No se pudo generar la respuesta")


def generar_stream(
    prompt: str, temperatura: float = 0.2, modelo: str | None = None
) -> Iterator[str]:
    """Emite el texto por fragmentos según el modelo lo produce.

    La respuesta completa tarda ~12 s; el primer fragmento llega en ~1 s, así
    que el usuario empieza a leer de inmediato en lugar de mirar un spinner.

    A diferencia de `generar`, aquí no se puede reintentar a mitad de camino:
    una vez emitido un fragmento, el cliente ya lo pintó. Los fallos de red
    posteriores al primer byte se propagan.
    """
    payload = json.dumps(
        {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": temperatura},
        }
    ).encode()

    # Reintentar es seguro mientras no se haya emitido ningún fragmento: el
    # cliente todavía no ha pintado nada. Por eso esto rodea solo la apertura
    # de la conexión, no la lectura. Si un modelo agota su cuota se pasa al
    # siguiente de la cadena en vez de rendirse.
    respuesta = None
    ultimo_error: GeminiError | None = None

    for candidato_modelo in _cadena_modelos(modelo):
        url = (
            f"{API_BASE}/models/{candidato_modelo}:streamGenerateContent"
            f"?alt=sse&key={get_api_key()}"
        )
        for intento in range(_STREAM_MAX_REINTENTOS):
            ultimo = intento == _STREAM_MAX_REINTENTOS - 1
            req = urllib.request.Request(
                url, data=payload, headers={"Content-Type": "application/json"}
            )
            try:
                respuesta = urllib.request.urlopen(req, timeout=_STREAM_TIMEOUT)
                break
            except urllib.error.HTTPError as e:
                cuerpo = e.read().decode(errors="replace")[:300]
                ultimo_error = GeminiError(
                    f"HTTP {e.code} al abrir el stream ({candidato_modelo}): {cuerpo}"
                )
                if e.code == 429:
                    # Cuota agotada: degradar ya, sin gastar más reintentos.
                    _marcar_agotado(candidato_modelo)
                    break
                if e.code in (500, 503) and not ultimo:
                    time.sleep(_BASE_ESPERA * (2**intento) + random.uniform(0, 1))
                    continue
                break
            except (TimeoutError, OSError) as e:
                ultimo_error = GeminiError(
                    f"Error de red al abrir el stream ({candidato_modelo}): {e}"
                )
                if not ultimo:
                    time.sleep(_BASE_ESPERA * (2**intento))
                    continue
                break
        if respuesta is not None:
            break

    if respuesta is None:
        raise ultimo_error or GeminiError("Se agotaron los reintentos al abrir el stream")

    with respuesta:
        for linea_bruta in respuesta:
            linea = linea_bruta.decode("utf-8").strip()
            if not linea.startswith("data:"):
                continue
            cuerpo = linea[len("data:") :].strip()
            if not cuerpo or cuerpo == "[DONE]":
                continue
            try:
                dato = json.loads(cuerpo)
            except json.JSONDecodeError:
                continue

            for candidato in dato.get("candidates", []):
                for parte in candidato.get("content", {}).get("parts", []):
                    texto = parte.get("text")
                    if texto:
                        yield texto
