# 🚀 Despliegue en Render (opcional)

Guía para desplegar tu propia instancia en [Render](https://render.com) usando Groq como LLM y Chroma Cloud como base de datos vectorial, en vez de Ollama nativo + ChromaDB local. Ver [ADR-007](adr/007-cloud-deployment-groq-chroma.md) para el razonamiento completo detrás de esta elección.

**Esto NO reemplaza el desarrollo local.** `docker-compose up -d` con `LLM_PROVIDER=ollama` (el default) sigue funcionando exactamente igual que siempre — esta guía es solo para quien quiera tener una instancia propia accesible fuera de `localhost`, sin depender de hardware local (GPU Metal) ni de tener Ollama corriendo.

---

## Prerrequisitos

1. **Cuenta en Render** — [render.com](https://render.com), free tier, no requiere tarjeta para servicios `plan: free`.
2. **API key de Groq** — [console.groq.com/keys](https://console.groq.com/keys), gratuita, sin tarjeta.
3. **Base de datos en Chroma Cloud** — [trychroma.com](https://www.trychroma.com), free tier hasta 1M embeddings, no pidió tarjeta al crear la cuenta (verificado). Al crear la base de datos obtienes `api_key` (y opcionalmente `tenant`/`database`, aunque se pueden dejar vacíos si la key está ligada a una sola BD).
4. **Base de datos Postgres** (para autenticación) — [neon.tech](https://neon.tech), free tier, no requiere tarjeta. Copia el connection string desde el dashboard tras crear el proyecto.

## Pasos

### 1. Desplegar el blueprint

El repo incluye [`render.yaml`](../render.yaml) en la raíz. En el dashboard de Render:

1. **New → Blueprint**
2. Conecta este repositorio de GitHub
3. Render detecta `render.yaml` y propone crear **dos servicios**: `bibliotecario-ia-api` (Docker, `plan: free`, build desde `api/Dockerfile`) y `bibliotecario-ia-frontend` (Static Site, build desde `frontend/`)
4. Confirma la creación

### 2. Crear el primer usuario (antes de rellenar las variables del paso siguiente)

No hay registro público — el login se crea por CLI, apuntando directamente a tu base de datos de Neon (sin necesidad de que la API esté desplegada todavía):

```bash
source api/venv/bin/activate
DATABASE_URL="<tu connection string de Neon>" python scripts/create_user.py --email tu@email.com
```

Hacerlo antes del primer deploy evita que la API arranque sin ningún usuario con el que entrar.

### 3. Rellenar las variables marcadas como `sync: false`

`render.yaml` define qué variables necesita cada servicio, pero las que son secretas (`sync: false`) **no se versionan** — Render te las pide al confirmar el blueprint, o las rellenas después en cada servicio → **Environment**:

**Servicio `bibliotecario-ia-api`:**

| Variable | Valor |
|---|---|
| `GROQ_API_KEY` | Tu key de console.groq.com |
| `CHROMA_CLOUD_API_KEY` | Tu key de Chroma Cloud |
| `CHROMA_CLOUD_TENANT` | Tenant de tu BD (opcional, ver más abajo) |
| `CHROMA_CLOUD_DATABASE` | Nombre de tu BD (opcional, ver más abajo) |
| `NOTION_API_KEY` | Solo si vas a sincronizar Notion |
| `DATABASE_URL` | Connection string de Neon (el mismo del paso 2) |
| `JWT_SECRET_KEY` | Genera uno: `python -c "import secrets; print(secrets.token_hex(32))"` |
| `FRONTEND_URL` | URL pública que Render asignó a `bibliotecario-ia-frontend` (la ves en su dashboard tras crearlo) — necesaria para CORS y para que la cookie de sesión funcione |

`tenant`/`database` de Chroma Cloud pueden dejarse vacíos: `chromadb.CloudClient` los resuelve automáticamente a partir de la API key si esta está ligada a una única base de datos.

El resto de variables del servicio API (`LLM_PROVIDER=groq`, `VECTOR_DB_PROVIDER=chroma_cloud`, `GROQ_MODEL`, `EMBEDDING_MODEL_NAME`, `JWT_EXPIRATION_MINUTES`) ya vienen fijadas en `render.yaml` — no hace falta tocarlas salvo que quieras otro modelo de Groq u otra duración de sesión.

**Servicio `bibliotecario-ia-frontend`:**

| Variable | Valor |
|---|---|
| `VITE_API_URL` | URL pública que Render asignó a `bibliotecario-ia-api` |

Esta variable se hornea en el build (Vite la sustituye en tiempo de build, no de arranque) — si la cambias más tarde, hace falta un redeploy manual del frontend para que surta efecto.

### 4. Primer arranque e ingesta

La base de datos de Chroma Cloud empieza vacía — es una BD nueva, no una copia de tu ChromaDB local (los embeddings tampoco son compatibles: 384 dims con el backend ONNX vs 768 con `nomic-embed-text`, ver ADR-007). Indexa documentos contra la API ya desplegada, iniciando sesión primero:

```bash
# 1. Login (guarda la cookie de sesión para las siguientes peticiones)
curl -c cookies.txt -X POST "https://<tu-api>.onrender.com/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email": "tu@email.com", "password": "..."}'

# 2. Subir un PDF
curl -b cookies.txt -X POST "https://<tu-api>.onrender.com/sync/upload" \
  -F "file=@documento.pdf"

# 3. O una página de Notion
curl -b cookies.txt -X POST "https://<tu-api>.onrender.com/sync/notion" \
  -H "Content-Type: application/json" \
  -d '{"page_id": "..."}'
```

O más simple: entra desde el navegador en la URL de `bibliotecario-ia-frontend`, inicia sesión y usa el panel de sincronización.

### 5. Verificar

```bash
# Público, sin login (usado también como healthcheck de Render):
curl https://<tu-api>.onrender.com/health

# Protegido — debe dar 401 sin cookie:
curl https://<tu-api>.onrender.com/stats
```

`services.ollama` en la respuesta de `/health` refleja la disponibilidad de Groq (la clave del JSON no cambió por compatibilidad con el frontend, ver ADR-007), y `config.llm_provider` debería mostrar `"groq"`.

---

## Limitaciones a tener en cuenta

- **Cold starts**: los servicios `plan: free` de Render se duermen tras ~15 min sin tráfico; la primera petición tras dormir puede tardar decenas de segundos en responder.
- **Cookies de sesión en Safari y navegadores con bloqueo de cookies de terceros**: si frontend y API quedan en subdominios `.onrender.com` distintos (lo normal si no configuras un dominio propio), Safari y otros navegadores descartan la cookie de sesión — el login "parece" funcionar pero las peticiones protegidas posteriores dan 401. Se soluciona sirviendo frontend y API bajo el mismo dominio raíz (ver "Trabajo Futuro" en el README).
- **RAM del build**: por defecto se usa `EMBEDDING_BACKEND=onnx` (`chromadb.utils.embedding_functions.ONNXMiniLM_L6_V2`), pensado específicamente para el free tier de Render (512MB RAM) — no arrastra `torch`. Si cambias a `EMBEDDING_BACKEND=sentence_transformers` (más preciso, pero ~650MB extra en disco por `torch`), es probable que el servicio no arranque por falta de memoria en el free tier.
