"""Configuración central: claves, modelos y rutas.

La clave nunca vive en el código. Se lee de la variable de entorno
GOOGLE_API_KEY, y como conveniencia local se carga desde el archivo .env de la
raíz del proyecto (que está en .gitignore).
"""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BASE_DIR.parent
PARSED_DIR = BASE_DIR / "data" / "parsed"
INDEX_DIR = BASE_DIR / "data" / "index"

# Modelo de síntesis. Gemini 3.5 Flash responde bien con contexto largo.
MODEL_GENERACION = os.getenv("MODEL_GENERACION", "gemini-3.5-flash")
# Tareas baratas: clasificación de intención y ruteo por dominio.
MODEL_RAPIDO = os.getenv("MODEL_RAPIDO", "gemini-3.5-flash-lite")

# La cuota del plan gratuito se agota POR MODELO. Cuando el principal devuelve
# 429 durante todo un día, el asistente queda inservible aunque otros modelos
# sigan disponibles, así que se degrada al siguiente de la lista en vez de
# fallar. El orden va de más capaz a más disponible.
MODELOS_GENERACION = [
    m
    for m in [MODEL_GENERACION, MODEL_RAPIDO, "gemini-2.0-flash"]
    # dict.fromkeys no sirve aquí porque hay que preservar el orden y quitar
    # duplicados si alguien configura el mismo modelo en ambas variables.
    if m
]
MODELOS_GENERACION = list(dict.fromkeys(MODELOS_GENERACION))
MODEL_EMBEDDING = os.getenv("MODEL_EMBEDDING", "gemini-embedding-2")
EMBEDDING_DIM = 3072

API_BASE = "https://generativelanguage.googleapis.com/v1beta"


def _load_dotenv() -> None:
    # backend/.env cuando el backend es su propio repositorio, y ../.env
    # cuando se trabaja con frontend y backend juntos en una sola carpeta.
    for env_path in (BASE_DIR / ".env", PROJECT_DIR / ".env"):
        if not env_path.exists():
            continue
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())
        return


def get_api_key() -> str:
    _load_dotenv()
    key = os.getenv("GOOGLE_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "Falta GOOGLE_API_KEY. Copia .env.example a .env y coloca tu clave "
            "de Google AI Studio."
        )
    return key
