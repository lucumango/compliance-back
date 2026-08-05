# Despliegue

## Por qué NO todo en Vercel/Netlify

Una consulta tarda **12 s** sin diagrama y **30 s** con diagrama (medido). Las
funciones serverless de Vercel Hobby y de Netlify cortan alrededor de los 10 s,
así que la mayoría de las consultas devolvería un timeout. Además el índice son
9 MB que hay que cargar en memoria: en un proceso largo se lee una vez al
arrancar, mientras que en serverless se recarga en cada arranque en frío.

El backend quiere ser un **proceso largo**, no una función.

## Arquitectura recomendada

```
Frontend (estático)  ->  Vercel        gratis, ideal para Vite/React
Backend  (contenedor) ->  Render/Railway/Fly  proceso largo, sin timeouts
```

### 1. Backend

El `Dockerfile` incluido solo empaqueta la capa de runtime: la ingesta de PDFs
(PyMuPDF, OpenCV, Tesseract) se queda fuera, porque el corpus se procesa en
local y se despliega ya indexado. La imagen lleva ~9 MB de datos y cuatro
dependencias de Python.

En Render:

1. New → Web Service → conecta el repo, raíz `backend/`, runtime Docker.
2. Variable de entorno: `GOOGLE_API_KEY` (y `ALLOWED_ORIGINS`, ver abajo).
3. Deploy. El plan gratuito duerme tras inactividad: el primer request tras la
   siesta tarda ~1 min.

Railway y Fly.io funcionan igual con el mismo Dockerfile.

### 2. Frontend

```bash
cd frontend
npx vercel --prod
```

Configura `VITE_API_URL` en Vercel apuntando a la URL pública del backend.
Sin esa variable el frontend llama a `127.0.0.1:8000` y en producción falla.

## Antes de exponerlo al público

Dos cosas que hoy **bloquean** un despliegue abierto:

### La API no tiene autenticación

Cualquiera con la URL puede lanzar consultas contra tu cuota de Gemini. Como
mínimo, una clave compartida por cabecera y un límite por IP. Para un demo
privado basta con no publicar la URL, pero no es una protección real.

### ISO 37001 tiene copyright

El corpus incluye la traducción oficial completa, y la API devuelve el texto
íntegro de la cláusula en `fuentes[].texto`. Publicarlo es redistribución, y la
licencia del PDF es de usuario único. Opciones antes de exponerlo:

- excluir `iso_37001` del índice desplegado, o
- devolver solo la cita y un extracto corto, no la cláusula completa.

Sería irónico que una herramienta de compliance infringiera una licencia.

## Mejora de UX pendiente

30 s sin feedback es mucho. Lo que realmente lo arregla es **streaming**: emitir
la respuesta token a token con SSE y generar el diagrama después, en una segunda
petición. El usuario empieza a leer a los ~2 s en vez de esperar 30.
