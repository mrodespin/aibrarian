# 🚀 Despliegue en Render (demo pública gratuita)

Guía para desplegar la API en [Render](https://render.com) usando Groq como LLM y Chroma Cloud como base de datos vectorial, en vez de Ollama nativo + ChromaDB local. Ver [ADR-007](adr/007-despliegue-cloud-groq-chroma.md) para el razonamiento completo detrás de esta elección.

**Esto NO reemplaza el desarrollo local.** `docker-compose up -d` con `LLM_PROVIDER=ollama` (el default) sigue funcionando exactamente igual que siempre — esta guía es solo para tener una instancia pública además del setup local.

---

## Prerrequisitos

1. **Cuenta en Render** — [render.com](https://render.com), free tier, no requiere tarjeta para servicios `plan: free`.
2. **API key de Groq** — [console.groq.com/keys](https://console.groq.com/keys), gratuita, sin tarjeta.
3. **Base de datos en Chroma Cloud** — [trychroma.com](https://www.trychroma.com), free tier hasta 1M embeddings, no pidió tarjeta al crear la cuenta (verificado). Al crear la base de datos obtienes `api_key` (y opcionalmente `tenant`/`database`, aunque se pueden dejar vacíos si la key está ligada a una sola BD).

## Pasos

### 1. Desplegar el blueprint

El repo incluye [`render.yaml`](../render.yaml) en la raíz. En el dashboard de Render:

1. **New → Blueprint**
2. Conecta este repositorio de GitHub
3. Render detecta `render.yaml` y propone crear el servicio `bibliotecario-ia-api` (Docker, `plan: free`, build desde `api/Dockerfile`)
4. Confirma la creación

### 2. Rellenar las variables marcadas como `sync: false`

`render.yaml` define qué variables necesita el servicio, pero las que son secretas (`sync: false`) **no se versionan** — Render te las pide al confirmar el blueprint, o las rellenas después en el servicio → **Environment**:

| Variable | Valor |
|---|---|
| `GROQ_API_KEY` | Tu key de console.groq.com |
| `CHROMA_CLOUD_API_KEY` | Tu key de Chroma Cloud |
| `CHROMA_CLOUD_TENANT` | Tenant de tu BD (opcional, ver más abajo) |
| `CHROMA_CLOUD_DATABASE` | Nombre de tu BD (opcional, ver más abajo) |
| `NOTION_API_KEY` | Solo si vas a sincronizar Notion en la demo |

`tenant`/`database` pueden dejarse vacíos: `chromadb.CloudClient` los resuelve automáticamente a partir de la API key si esta está ligada a una única base de datos.

El resto de variables (`LLM_PROVIDER=groq`, `VECTOR_DB_PROVIDER=chroma_cloud`, `GROQ_MODEL`, `EMBEDDING_MODEL_NAME`) ya vienen fijadas en `render.yaml` — no hace falta tocarlas salvo que quieras otro modelo de Groq.

### 3. Primer arranque e ingesta

La base de datos de Chroma Cloud empieza vacía — es una BD nueva, no una copia de tu ChromaDB local (los embeddings tampoco son compatibles: 384 dims con `sentence-transformers` vs 768 con `nomic-embed-text`, ver ADR-007). Indexa documentos contra la API ya desplegada:

```bash
# Vía navegador: usa el panel de sincronización del frontend apuntando a la API de Render
# Vía curl, subiendo un PDF:
curl -X POST "https://<tu-servicio>.onrender.com/sync/upload" \
  -F "file=@documento.pdf"

# O una página de Notion:
curl -X POST "https://<tu-servicio>.onrender.com/sync/notion" \
  -H "Content-Type: application/json" \
  -d '{"page_id": "..."}'
```

### 4. Verificar

```bash
curl https://<tu-servicio>.onrender.com/health
```

`services.ollama` en la respuesta refleja la disponibilidad de Groq (la clave del JSON no cambió por compatibilidad con el frontend, ver ADR-007), y `config.llm_provider` debería mostrar `"groq"`.

---

## Limitaciones a tener en cuenta

- **Cold starts**: los servicios `plan: free` de Render se duermen tras ~15 min sin tráfico; la primera petición tras dormir puede tardar decenas de segundos en responder.
- **RAM del build**: `sentence-transformers` arrastra `torch` como dependencia — la imagen es notablemente más pesada que la versión solo-Ollama, y el consumo de RAM en arranque (carga del modelo de embeddings en memoria) puede ser ajustado en el free tier (recursos limitados, ver ADR-007). Si el servicio no arranca por falta de memoria, es el primer sospechoso.
- **Frontend**: esta guía solo cubre la API. Para servir el frontend también gratis, despliégalo aparte (Render Static Site, Vercel, Netlify...) apuntando `VITE_API_URL` a la URL de este servicio.
