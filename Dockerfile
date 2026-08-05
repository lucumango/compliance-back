# Imagen de runtime: solo sirve la API. La ingesta de PDFs (PyMuPDF, OpenCV,
# Tesseract) se hace en local y aquí solo viaja el corpus ya indexado, lo que
# evita arrastrar ~400 MB de dependencias y un binario de sistema.
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY api.py .
COPY rag/ rag/
# El índice (9 MB) y el corpus parseado se copian ya construidos.
COPY data/index/ data/index/
COPY data/uit.json data/

EXPOSE 8000

# El host debe ser 0.0.0.0 para aceptar tráfico fuera del contenedor, y el
# puerto lo asigna la plataforma (Render, Railway y Fly inyectan $PORT).
CMD ["sh", "-c", "uvicorn api:app --host 0.0.0.0 --port ${PORT:-8000}"]
