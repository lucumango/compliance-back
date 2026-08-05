# Asistente de Normativa y Compliance (Perú) — Backend

Implementación del MVP descrito en el
[plan de producto](https://claude.ai/code/artifact/b117cebd-7470-43d6-97ee-7f14b7a4c3d7).

**Estado actual: Fase 1 del plan completa.** Ingesta, índice vectorial,
recuperación con citas, diagramas Mermaid, calculadora de multas, API HTTP y
frontend React. Falta la Fase 2 (grafo, gap analysis, jurisprudencia).

Frontend: [compliance-agent](https://github.com/lucumango/compliance-agent).
Despliegue: ver [DEPLOY.md](DEPLOY.md).

## Qué hace hoy

Convierte 5 PDFs normativos en un corpus estructurado de **701 unidades
citables** (artículos, disposiciones complementarias y cláusulas ISO) y responde
consultas ancladas a ese corpus, citando artículo por artículo.

```
$ python -m rag.cli "¿Cuál es la multa máxima por una infracción muy grave?"

1. Monto máximo en UIT: ... hasta cien unidades impositivas tributarias [F1].
2. Límite según ingresos: no puede exceder del diez por ciento de los
   ingresos brutos anuales ... [F1].
3. Referencia temporal: la UIT vigente a la fecha en que se cometió la
   infracción ... [F6].

Fuentes:
  [F1] Ley 29733, Artículo 39  (similitud 0.757)
  [F6] Reglamento de la Ley 29733, Artículo 124  (similitud 0.677)
```

| Norma | Unidades | Notas |
|---|---|---|
| Ley 29733 — Protección de Datos Personales | 194 | Ley (40 art.) + DS aprobatorio + Reglamento (133 art.) |
| Ley 29783 — Seguridad y Salud en el Trabajo | 252 | Ley (103 art.) + Reglamento (123 art.) |
| Ley 30424 — Responsabilidad admin. de PJ | 30 | Escaneo con OCR |
| Ley 27693 — Crea la UIF-Perú | 21 | Escaneo con OCR |
| ISO 37001:2016 — Antisoborno | 204 | Cláusulas 1–10 + Anexo A |

## Uso

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
brew install tesseract tesseract-lang   # OCR en español, para los escaneos

cp .env.example .env                    # y coloca tu clave de Google AI Studio

python -m ingestion.ingest      # PDFs -> data/parsed/*.json
python -m ingestion.validate    # controles de calidad sobre el corpus
python -m rag.index             # embeddings -> data/index/  (~6 min)

python -m rag.cli "tu consulta"  # o sin argumentos, modo interactivo
python -m rag.eval               # evaluación de recuperación
```

## Arquitectura de la ingesta

```
data/raw/normativas/*.pdf
   │
   ├─ extract.py    texto nativo (PyMuPDF); OCR (Tesseract) si la página es imagen
   ├─ parser.py     leyes: Título → Capítulo/Sección → Artículo + disposiciones
   ├─ iso_parser.py ISO: cláusulas decimales + Anexo A
   ├─ registry.py   metadatos por norma
   └─ ingest.py     → data/parsed/<norma>.json
```

### Decisiones que importan

**OCR sobre escaneos dañados.** `ley_27693` y `ley_30424` no tienen capa de
texto. Los encabezados de artículo van subrayados, y esa línea horizontal
arruina el reconocimiento: `Artículo 3º.-` se leía como `lo 39.-`, perdiendo el
límite del artículo. `extract.py` detecta las líneas horizontales por morfología
y las borra por inpainting antes de pasar a Tesseract.

**Desambiguación por monotonicidad.** La numeración de artículos siempre crece.
Cuando una coincidencia rompe esa secuencia — una referencia cruzada partida por
un salto de línea, o un artículo de otro código citado dentro de una disposición
modificatoria — se pliega al artículo anterior en vez de crear uno falso. El
mismo criterio recupera el ordinal `º` mal leído como dígito (`Artículo 9º` →
`92` → `9`).

**Metadatos conservadores.** `fecha_publicacion` y `url_fuente` quedan en `null`
salvo cuando se leen del propio documento, y `metadata_verificada` lo registra.
En un producto de compliance una fecha inventada es peor que una ausente, así
que nada aquí se afirma de memoria: hay que cotejar contra SPIJ / El Peruano.

**Texto para recuperación.** Cada unidad lleva un `texto_para_embedding` que
antepone el nombre de la norma y su ubicación jerárquica:

```
Ley de Protección de Datos Personales (Ley 29733) · Título VII —
INFRACCIONES Y SANCIONES ADMINISTRATIVAS · Artículo 39

Sanciones administrativas...
```

Repetir ese contexto permite recuperar el artículo con preguntas formuladas en
términos de la ley, no solo con las palabras del articulado.

## Capa RAG

```
rag/config.py       claves y modelos (clave desde .env, nunca en código)
rag/gemini.py       cliente de la API: embeddings y generación, con reintentos
rag/anonimizar.py   enmascara PII antes de llamar al modelo
rag/index.py        construye y carga el índice vectorial
rag/retrieval.py    búsqueda por similitud coseno
rag/answer.py       arma el prompt anclado y exige cita por afirmación
rag/cli.py          interfaz de terminal
rag/eval.py         evaluación de recuperación
```

Modelos: `gemini-3.5-flash` para síntesis y `gemini-embedding-2` (3072 dims)
para el índice. Los `pro-preview` devuelven 429 en el plan gratuito.

**El caso negativo es el que importa.** Ante "¿en cuántas horas debo notificar
una brecha a la ANPD?", el sistema responde que el corpus no lo contiene y
remite al reglamento y a las directivas de la ANPD. Un RAG sin esa restricción
contesta "72 horas" copiando el GDPR, que no es derecho peruano.

**Las advertencias viajan con la respuesta.** Si las fuentes provienen de un
escaneo con OCR, o de un texto sin modificatorias posteriores, la respuesta lo
declara:

```
Advertencias:
  ! Ley 30424: Texto ORIGINAL publicado el 21/04/2016, sin las modificatorias
    posteriores (p. ej. Ley 30835, Ley 31740). No usar como texto vigente.
```

## Streaming

La respuesta se emite por SSE (`/api/consultar/stream`), lo que cambia por
completo la percepción de espera:

| | antes | ahora |
|---|---|---|
| citas visibles | 30 s | **0.9 s** |
| primer texto | 30 s | **2.1 s** |

El diagrama se pide aparte (`/api/diagrama`) porque necesita la respuesta
completa; generarlo dentro del stream duplicaba el tiempo total.

**Cadena de modelos con respaldo.** La cuota gratuita se agota *por modelo*,
así que un 429 degrada al siguiente de la lista en vez de dejar el asistente
inservible. El modelo agotado queda en enfriamiento 15 min: sin eso, cada
petición volvía a gastar sus reintentos contra el modelo caído y añadía ~9 s
al primer fragmento.

## API y frontend

```
backend/api.py           FastAPI: /api/consultar, /api/multa, /api/normas, /api/salud
frontend/src/App.jsx     chat, panel de fuentes desplegable, filtro por materia
frontend/src/Mermaid.jsx render del diagrama (securityLevel strict: el código
                         lo genera un modelo, no es contenido de confianza)
frontend/src/Calculadora Multas.jsx  estimador por gravedad
```

La calculadora de multas obedece los dos principios del plan: la **UIT es
configuración** (`data/uit.json`, con la norma que fija cada valor —
DS 301-2025-EF para 2026) y los **rangos salen del corpus**, apuntando al
artículo que los establece. La salida se rotula como estimación de impacto, no
como determinación de sanción.

El diagrama solo se genera cuando la consulta es procedimental ("¿qué hago
si…?", "¿cómo se tramita…?"). Para una consulta de definición sería ruido.

## Verificación

- `python -m ingestion.validate` — numeración sin huecos ni duplicados,
  ausencia de encabezados de página filtrados, unidades vacías, citas
  presentes. Actualmente: **0 problemas sobre 701 unidades**.
- `python -m rag.eval` — 8 consultas de referencia contra el artículo que
  deben recuperar, cubriendo los cinco documentos. Actualmente: **8/8**.

Un control cruzado útil: el DS 003-2013-JUS declara en su preámbulo que el
reglamento tiene 3 disposiciones complementarias finales y 3 transitorias, y el
parser extrae exactamente 3 y 3.

## Limitaciones conocidas

- **No es asesoría legal.** El corpus informa; un abogado debe validar.
- **La anonimización es por patrones, no por NER.** Reconoce DNI, RUC, correos,
  teléfonos, montos y tarjetas. **No reconoce nombres de personas**: "Juan
  Pérez" viaja al modelo tal cual. Si eso importa para tu caso de uso, hace
  falta un reconocedor de entidades.
- **Los textos OCR requieren cotejo.** `extraccion.requiere_cotejo` lo marca por
  norma. `ley_30424` es además el texto **original de 2016**, sin modificatorias.
- **Fechas y URLs sin verificar.** `metadata_verificada: false` en casi todo el
  corpus; hay que cotejar contra SPIJ / El Peruano.
- **ISO 37001 tiene copyright.** Uso interno del proyecto; no redistribuir el
  texto íntegro.
- **El corpus no cubre el reglamento de la Ley 30424** (DS 002-2019-JUS) ni las
  resoluciones SBS de gestión de riesgos LA/FT, ambos en el plan original.

- **La UI no se verificó en navegador.** El build de producción pasa y todos
  los módulos transpilan, pero no se abrió Chrome para comprobar el render.
- **Un solo régimen en la calculadora.** Solo protección de datos (Ley 29733,
  Art. 39). Los rangos de SST y LA/FT están en normas que no se cargaron.

## Siguiente paso

Fase 2 del plan: migración a grafo para trazar qué norma modifica a cuál — el
campo `modificatorias` de cada unidad ya guarda ese insumo —, carga de políticas
internas con gap analysis, y buscador de resoluciones sancionadoras.
