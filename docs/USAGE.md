# 📚 API & Services Documentation (tfm-bibliotecario-ia)

Esta documentación detalla todos los servicios, puertos y endpoints de la API del proyecto Bibliotecario-IA.

> **Autenticación:** desde que se añadió login, todos los endpoints salvo `/`, `/health` y `/metrics` requieren una sesión válida (JWT emitido por `POST /auth/login`, enviado como `Authorization: Bearer <token>` en el resto de peticiones — no como cookie, para evitar el bloqueo de cookies cross-site del ITP de Safari cuando frontend y API están en dominios distintos). Los ejemplos cURL de esta guía asumen que ya has hecho login y estás reutilizando el token. Ver la sección [Autenticación](#-autenticación) más abajo.

---

## 🌐 Servicios del Proyecto

Cuando ejecutas el sistema, estos son los servicios que necesitas:

| Servicio | URL Local | URL Interna (Docker) | Propósito |
| :--- | :--- | :--- | :--- |
| **FastAPI API** | `http://localhost:8000` | `http://api:8000` | API principal del proyecto (ingesta y consultas) |
| **ChromaDB** | `http://localhost:8001` | `http://chromadb:8000` | Base de datos vectorial para embeddings |
| **Ollama** | `http://localhost:11434` | `http://ollama:11434` | LLM local (generación de texto y embeddings) |
| **Postgres** | `localhost:5432` | `postgres:5432` | Usuarios/autenticación |

**Nota sobre puertos:** ChromaDB expone el puerto 8001 en el host para evitar conflicto con la API (que usa 8000). Internamente en Docker, ChromaDB usa el puerto 8000.

---

## 🤖 Endpoints de la API FastAPI

API principal del proyecto ejecutándose en `http://localhost:8000`. Los endpoints marcados con 🔒 requieren sesión (token de `/auth/login` enviado como header `Authorization: Bearer <token>`).

### 🔐 Autenticación

No hay registro público — los usuarios se crean con `scripts/create_user.py` (ver [Scripts CLI](#-scripts-cli)).

#### `POST /auth/login` - Iniciar Sesión

Verifica credenciales y, si son correctas, devuelve un JWT de sesión (24h por defecto) en el cuerpo de la respuesta. El cliente debe guardarlo y reenviarlo como header `Authorization: Bearer <access_token>` en el resto de peticiones.

**Request Body:**
```json
{
  "email": "tu@email.com",
  "password": "..."
}
```

**Response (200 OK):**
```json
{
  "id": 1,
  "email": "tu@email.com",
  "access_token": "eyJhbGciOi...",
  "token_type": "bearer"
}
```

**Response (401):** credenciales incorrectas.

**Ejemplo cURL:**
```bash
TOKEN=$(curl -s -X POST "http://localhost:8000/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email": "tu@email.com", "password": "..."}' | jq -r .access_token)
```

---

#### `POST /auth/logout` - Cerrar Sesión

El JWT es stateless (sin blocklist server-side): este endpoint no invalida nada, es el cliente quien debe descartar el token guardado.

**Response (200 OK):**
```json
{"status": "success"}
```

---

#### `GET /auth/me` - Usuario Actual 🔒

Devuelve el usuario de la sesión activa. Útil para comprobar si un token sigue siendo válido.

**Response (200 OK):**
```json
{
  "id": 1,
  "email": "tu@email.com"
}
```

**Response (401):** sin token o token inválido/expirado.

**Ejemplo cURL** (reutiliza el `access_token` obtenido en el login):
```bash
curl -H "Authorization: Bearer $TOKEN" "http://localhost:8000/auth/me"
```

---

### 📊 Endpoints de Utilidad

#### `GET /` - Health Check Básico

Verifica que la API esté ejecutándose. **Sin autenticación** — es el endpoint que usa Render como healthcheck del servicio.

**Response (200 OK):**
```json
{
  "status": "running",
  "version": "0.1.0",
  "llm_provider": "ollama",
  "llm_available": true,
  "vector_db_provider": "chromadb_local",
  "vector_db_available": true
}
```

---

#### `GET /health` - Health Check Detallado

Verifica el estado de todos los servicios y configuración. **Sin autenticación.**

**Response (200 OK):**
```json
{
  "status": "healthy",
  "services": {
    "ollama": true,
    "chromadb": true
  },
  "config": {
    "llm_provider": "ollama",
    "vector_db_provider": "chromadb_local",
    "ollama_model": "llama3.2",
    "embedding_model": "nomic-embed-text",
    "collection": "bibliotecario_docs",
    "data_directory": "./data"
  }
}
```

> La clave `services.ollama` refleja la disponibilidad del LLM activo aunque sea Groq (se mantiene el nombre por compatibilidad con el frontend, ver ADR-007).

---

#### `GET /stats` - Estadísticas de la Colección 🔒

Obtiene información sobre la base de conocimientos. **Requiere sesión.**

**Response (200 OK):**
```json
{
  "collection": "bibliotecario_docs",
  "stats": {
    "count": 42,
    "dimensions": 768,
    "collection_name": "bibliotecario_docs"
  },
  "model_info": {
    "llm_model": "llama3.2",
    "embedding_model": "nomic-embed-text"
  }
}
```

---

## 📥 Endpoints de Ingesta (MVP)

### `POST /sync` - Sincronizar PDF Individual 🔒

Procesa un archivo PDF y lo indexa en la base de datos vectorial.

**Request Body:**
```json
{
  "file_path": "./data/documento.pdf",
  "collection_name": "bibliotecario_docs"  // Opcional
}
```

**Response (200 OK):**
```json
{
  "document_id": "pdf_a1b2c3d4",
  "chunks_created": 15,
  "success": true,
  "message": "Document synced successfully to collection 'bibliotecario_docs'",
  "processing_time": 8.42
}
```

**Ejemplo cURL:**
```bash
curl -H "Authorization: Bearer $TOKEN" -X POST "http://localhost:8000/sync" \
  -H "Content-Type: application/json" \
  -d '{
    "file_path": "./data/manual.pdf"
  }'
```

---

### `POST /sync/upload` - Subir y Sincronizar PDF 🔒

Como `/sync`, pero acepta el archivo directamente (`multipart/form-data`) en vez de una ruta local — es lo que usa el panel de sincronización del frontend, y el único que funciona en producción (donde el servidor no tiene acceso al filesystem del cliente).

**Ejemplo cURL:**
```bash
curl -H "Authorization: Bearer $TOKEN" -X POST "http://localhost:8000/sync/upload" \
  -F "file=@documento.pdf"
```

---

### `POST /sync/directory` - Sincronizar Directorio de PDFs 🔒

Procesa todos los archivos PDF de un directorio.

**Query Parameters:**
- `directory_path` (opcional): Ruta del directorio. Por defecto usa `./data`

**Response (200 OK):**
```json
{
  "total": 5,
  "successful": 4,
  "failed": 1,
  "results": [
    {
      "document_id": "pdf_a1b2c3d4",
      "chunks_created": 15,
      "success": true,
      "message": "Document synced successfully",
      "processing_time": 8.42
    }
  ]
}
```

**Ejemplo cURL:**
```bash
# Usar directorio por defecto (./data)
curl -H "Authorization: Bearer $TOKEN" -X POST "http://localhost:8000/sync/directory"

# Especificar directorio
curl -H "Authorization: Bearer $TOKEN" -X POST "http://localhost:8000/sync/directory?directory_path=/ruta/a/pdfs"
```

---

## 🔗 Endpoints de Integración con Notion

### `POST /sync/notion` - Sincronizar Página de Notion 🔒

Procesa una página de Notion y la indexa en la base de datos vectorial.

**Prerrequisitos:**
- Variable de entorno `NOTION_API_KEY` configurada
- Página compartida con tu integración de Notion

**Request Body:**
```json
{
  "page_id": "a1b2c3d4e5f6",  // ID o URL de la página
  "collection_name": "bibliotecario_docs"  // Opcional
}
```

**Response (200 OK):**
```json
{
  "document_id": "notion_a1b2c3d4e5f6",
  "chunks_created": 12,
  "success": true,
  "message": "Document synced successfully to collection 'bibliotecario_docs'",
  "processing_time": 6.18
}
```

**Ejemplo cURL:**
```bash
curl -H "Authorization: Bearer $TOKEN" -X POST "http://localhost:8000/sync/notion" \
  -H "Content-Type: application/json" \
  -d '{
    "page_id": "https://www.notion.so/Mi-Pagina-abc123..."
  }'
```

---

### `POST /sync/notion/database` - Sincronizar Base de Datos de Notion 🔒

Procesa todas las páginas de una base de datos de Notion.

**Request Body:**
```json
{
  "database_id": "a1b2c3d4e5f6",  // Opcional, usa env var si no se proporciona
  "max_pages": 10,  // Opcional, limita el número de páginas
  "collection_name": "bibliotecario_docs"  // Opcional
}
```

**Response (200 OK):**
```json
{
  "total": 8,
  "successful": 7,
  "failed": 1,
  "results": [
    {
      "document_id": "notion_page1",
      "chunks_created": 10,
      "success": true,
      "message": "Synced 'Título de la Página'"
    }
  ]
}
```

**Ejemplo cURL:**
```bash
curl -H "Authorization: Bearer $TOKEN" -X POST "http://localhost:8000/sync/notion/database" \
  -H "Content-Type: application/json" \
  -d '{
    "database_id": "abc123...",
    "max_pages": 5
  }'
```

---

## 💬 Endpoint de Consultas

### `POST /ask` - Hacer Pregunta al Sistema RAG 🔒

Realiza una pregunta sobre los documentos indexados y obtiene una respuesta generada por IA.

**Request Body:**
```json
{
  "question": "¿Cuál es el tema principal del documento?",
  "session_id": "user_session_123",  // Opcional
  "max_results": 4  // Opcional, número de chunks de contexto (1-10)
}
```

**Response (200 OK):**
```json
{
  "question": "¿Cuál es el tema principal del documento?",
  "answer": "El tema principal del documento es la implementación de sistemas RAG...",
  "source_documents": [
    {
      "document_id": "pdf_a1b2c3d4",
      "chunk_content": "Los sistemas RAG combinan recuperación de información...",
      "metadata": {
        "filename": "manual.pdf",
        "page": 1,
        "chunk_index": 0
      },
      "relevance_score": 0.95
    }
  ],
  "session_id": "user_session_123",
  "processing_time": 3.24
}
```

**Ejemplo cURL:**
```bash
curl -H "Authorization: Bearer $TOKEN" -X POST "http://localhost:8000/ask" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "¿Qué es RAG?"
  }'
```

---

## 🗑️ Endpoint de Eliminación

### `DELETE /documents/{document_id}` - Eliminar Documento 🔒

Elimina todos los chunks de un documento de la base de datos vectorial.

**Path Parameters:**
- `document_id`: ID del documento a eliminar

**Response (200 OK):**
```json
{
  "status": "success",
  "message": "Document pdf_a1b2c3d4 deleted"
}
```

**Ejemplo cURL:**
```bash
curl -H "Authorization: Bearer $TOKEN" -X DELETE "http://localhost:8000/documents/pdf_a1b2c3d4"
```

---

## 🛠️ Scripts CLI

Además de la API, el proyecto incluye scripts de automatización en el directorio `scripts/`:

### 1. `setup.py` - Instalación Automática

Instala y configura todo el entorno de desarrollo interactivamente.

```bash
python3 scripts/setup.py
```

**Qué hace:** Verifica OS, instala Homebrew/Ollama/Docker, configura Python/venv, crea .env (con un `JWT_SECRET_KEY` generado), levanta ChromaDB + Postgres + API en Docker, ejecuta `verify_setup.py` y, al final, ofrece crear tu usuario (`create_user.py`) — no hay UI de registro, así que sin esto no puedes hacer login.

---

### 2. `verify_setup.py` - Verificación del Entorno

Verifica que todos los servicios estén correctamente instalados (11 checks: Python, dependencias, Ollama, Docker, ChromaDB, Postgres/auth, estructura, data, API, Node.js, frontend).

```bash
python scripts/verify_setup.py
```

**Salida:** Reporte coloreado con ✅ éxito, ❌ error, ⚠️ advertencia.

---

### 3. `ingest_pdfs.py` - Ingesta de PDFs

Procesa PDFs y los ingesta en ChromaDB. Alternativa CLI a los endpoints `/sync` de la API.

```bash
# Procesar todos los PDFs en /data
python scripts/ingest_pdfs.py

# Procesar un directorio específico
python scripts/ingest_pdfs.py /ruta/a/pdfs

# Procesar un archivo específico
python scripts/ingest_pdfs.py --file documento.pdf

# Usar colección diferente
python scripts/ingest_pdfs.py --collection mi_coleccion
```

**Prerequisito:** `source api/venv/bin/activate` (necesita dependencias de FastAPI/LangChain)

---

### 4. `ingest_notion.py` - Ingesta de Notion

Ingesta contenido de Notion. Alternativa CLI a `/sync/notion`.

```bash
# Página individual
python scripts/ingest_notion.py --page PAGE_ID

# Base de datos completa
python scripts/ingest_notion.py --database DATABASE_ID

# Limitar páginas
python scripts/ingest_notion.py --database DATABASE_ID --max 10
```

**Prerequisito:**
- `NOTION_API_KEY` en `api/.env`
- `source api/venv/bin/activate`

---

### 5. `generate_test_pdf.py` - Genera PDF de Prueba

Genera `data/test_document.pdf` con contenido sobre el proyecto para testing.

```bash
python scripts/generate_test_pdf.py
```

**Output:** `data/test_document.pdf` (~2 páginas)

---

### 6. `create_user.py` - Crear Usuario de Login

No hay UI de registro — es la única forma de dar de alta un usuario. Pide la contraseña de forma interactiva (`getpass`, dos veces para confirmar) en vez de como argumento, para que no quede en el historial de la shell.

```bash
python scripts/create_user.py --email tu@email.com
```

**Prerequisito:**
- `DATABASE_URL` configurada en `api/.env` (local) o como variable de entorno (p. ej. para crear el primer usuario contra Neon en producción)
- `source api/venv/bin/activate`

**Salida:** `✅ User created: tu@email.com (id=1)`. Crea también la tabla `users` si no existe todavía (idempotente).

---

## 🔐 Configuración de Notion

Para usar los endpoints de Notion:

1. **Crear integración en Notion:**
   - Ve a https://www.notion.so/my-integrations
   - Crea una nueva integración
   - Copia el "Internal Integration Token"

2. **Configurar variable de entorno:**
   ```bash
   export NOTION_API_KEY=secret_xxxxxxxxxxxxx
   ```

3. **Compartir páginas:**
   - Abre la página en Notion
   - Click en "..." → "Add connections"
   - Selecciona tu integración

---

## 📖 Documentación Interactiva

FastAPI genera documentación interactiva automáticamente:

- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

Desde estas interfaces puedes:
- Ver todos los endpoints disponibles
- Probar las llamadas a la API directamente
- Ver los esquemas de request/response
- Generar código de ejemplo

---

## 🚀 Flujo de Trabajo Típico

### 1. Crear usuario e iniciar sesión (una vez)

```bash
python scripts/create_user.py --email tu@email.com

TOKEN=$(curl -s -X POST "http://localhost:8000/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email": "tu@email.com", "password": "..."}' | jq -r .access_token)
```

### 2. Indexar Documentos

```bash
# Opción A: PDFs locales
curl -H "Authorization: Bearer $TOKEN" -X POST "http://localhost:8000/sync/directory"

# Opción B: Página de Notion
curl -H "Authorization: Bearer $TOKEN" -X POST "http://localhost:8000/sync/notion" \
  -H "Content-Type: application/json" \
  -d '{"page_id": "abc123..."}'
```

### 3. Verificar Ingesta

```bash
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/stats
```

### 4. Hacer Preguntas

```bash
curl -H "Authorization: Bearer $TOKEN" -X POST "http://localhost:8000/ask" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "¿De qué tratan los documentos indexados?"
  }'
```

---

## 🐛 Solución de Problemas

### `401 Not authenticated`

```json
{
  "detail": "Not authenticated"
}
```

**Solución:** falta el token (o expiró, dura 24h por defecto). Repite el login y reutiliza el `access_token` devuelto:
```bash
TOKEN=$(curl -s -X POST "http://localhost:8000/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email": "tu@email.com", "password": "..."}' | jq -r .access_token)
# ...y usa -H "Authorization: Bearer $TOKEN" en las siguientes peticiones
```

Si no tienes usuario todavía: `python scripts/create_user.py --email tu@email.com`.

### Ollama no disponible

```json
{
  "ollama_available": false
}
```

**Solución:**
```bash
# Iniciar Ollama
ollama serve

# Verificar modelos instalados
ollama list

# Descargar modelos necesarios
ollama pull llama3.2
ollama pull nomic-embed-text
```

### ChromaDB no disponible

```json
{
  "chromadb_available": false
}
```

**Solución:**
```bash
# Iniciar ChromaDB con Docker
docker-compose up -d chromadb
```

### Error al sincronizar Notion

```json
{
  "detail": "Notion API key not configured"
}
```

**Solución:**
```bash
# Configurar API key
export NOTION_API_KEY=secret_xxxxxxxxxxxxx

# O añadirlo al archivo .env
echo "NOTION_API_KEY=secret_xxxxxxxxxxxxx" >> api/.env
```

---

## 🖥️ Frontend (React + Vite)

El proyecto incluye un frontend web para interactuar con el sistema RAG.

### Requisitos

- **Node.js 18+** (recomendado: usar `nvm` o `fnm`)
- **npm** (incluido con Node.js)

### Instalación

```bash
# 1. Ir al directorio frontend
cd frontend

# 2. Instalar dependencias
npm install

# 3. Configurar variables de entorno (opcional)
cp .env.example .env
# Editar .env si la API no está en localhost:8000
```

### Ejecución

```bash
# Modo desarrollo (con hot-reload)
cd frontend
npm run dev
```

El frontend estará disponible en: **http://localhost:5173**

### Build de Producción

```bash
# Generar build optimizado
npm run build

# Los archivos se generan en frontend/dist/
```

### Configuración

El frontend se configura mediante variables de entorno en `frontend/.env`:

| Variable | Valor por defecto | Descripción |
|----------|-------------------|-------------|
| `VITE_API_URL` | `http://localhost:8000` | URL de la API FastAPI |

---