# 📚 API & Services Documentation (tfm-bibliotecario-ia)

Esta documentación detalla todos los servicios, puertos y endpoints de la API del proyecto Bibliotecario-IA.

---

## 🌐 Servicios del Proyecto

Cuando ejecutas el sistema, estos son los servicios que necesitas:

| Servicio | URL Local | URL Interna (Docker) | Propósito |
| :--- | :--- | :--- | :--- |
| **FastAPI API** | `http://localhost:8000` | `http://api:8000` | API principal del proyecto (ingesta y consultas) |
| **ChromaDB** | `http://localhost:8001` | `http://chromadb:8000` | Base de datos vectorial para embeddings |
| **Ollama** | `http://localhost:11434` | `http://ollama:11434` | LLM local (generación de texto y embeddings) |

**Nota sobre puertos:** ChromaDB expone el puerto 8001 en el host para evitar conflicto con la API (que usa 8000). Internamente en Docker, ChromaDB usa el puerto 8000.

---

## 🤖 Endpoints de la API FastAPI

API principal del proyecto ejecutándose en `http://localhost:8000`.

### 📊 Endpoints de Utilidad

#### `GET /` - Health Check Básico

Verifica que la API esté ejecutándose.

**Response (200 OK):**
```json
{
  "status": "running",
  "version": "0.1.0",
  "ollama_available": true,
  "chromadb_available": true
}
```

---

#### `GET /health` - Health Check Detallado

Verifica el estado de todos los servicios y configuración.

**Response (200 OK):**
```json
{
  "status": "healthy",
  "services": {
    "ollama": true,
    "chromadb": true
  },
  "config": {
    "ollama_model": "llama3.2",
    "embedding_model": "nomic-embed-text",
    "collection": "bibliotecario_docs",
    "data_directory": "./data"
  }
}
```

---

#### `GET /stats` - Estadísticas de la Colección

Obtiene información sobre la base de conocimientos.

**Response (200 OK):**
```json
{
  "collection": "bibliotecario_docs",
  "stats": {
    "document_count": 42,
    "status": "active"
  },
  "model_info": {
    "llm_model": "llama3.2",
    "embedding_model": "nomic-embed-text"
  }
}
```

---

## 📥 Endpoints de Ingesta (MVP)

### `POST /sync` - Sincronizar PDF Individual

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
curl -X POST "http://localhost:8000/sync" \
  -H "Content-Type: application/json" \
  -d '{
    "file_path": "./data/manual.pdf"
  }'
```

---

### `POST /sync/directory` - Sincronizar Directorio de PDFs

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
curl -X POST "http://localhost:8000/sync/directory"

# Especificar directorio
curl -X POST "http://localhost:8000/sync/directory?directory_path=/ruta/a/pdfs"
```

---

## 🔗 Endpoints de Integración con Notion

### `POST /sync/notion` - Sincronizar Página de Notion

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
curl -X POST "http://localhost:8000/sync/notion" \
  -H "Content-Type: application/json" \
  -d '{
    "page_id": "https://www.notion.so/Mi-Pagina-abc123..."
  }'
```

---

### `POST /sync/notion/database` - Sincronizar Base de Datos de Notion

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
curl -X POST "http://localhost:8000/sync/notion/database" \
  -H "Content-Type: application/json" \
  -d '{
    "database_id": "abc123...",
    "max_pages": 5
  }'
```

---

## 💬 Endpoint de Consultas (Fase 1: Chatbot RAG)

### `POST /ask` - Hacer Pregunta al Sistema RAG

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
curl -X POST "http://localhost:8000/ask" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "¿Qué es RAG?"
  }'
```

---

## 🗑️ Endpoint de Eliminación

### `DELETE /documents/{document_id}` - Eliminar Documento

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
curl -X DELETE "http://localhost:8000/documents/pdf_a1b2c3d4"
```

---

## 🛠️ Scripts CLI

Además de la API, el proyecto incluye scripts de automatización en el directorio `scripts/`:

### 1. `setup.py` - Instalación Automática

Instala y configura todo el entorno de desarrollo interactivamente.

```bash
python3 setup.py
```

**Qué hace:** Verifica OS, instala Homebrew/Ollama/Docker, configura Python/venv, crea .env, ejecuta verify_setup.py.

---

### 2. `verify_setup.py` - Verificación del Entorno

Verifica que todos los servicios estén correctamente instalados (8 checks: Python, dependencias, Ollama, Docker, ChromaDB, estructura, data, API).

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

### 1. Indexar Documentos

```bash
# Opción A: PDFs locales
curl -X POST "http://localhost:8000/sync/directory"

# Opción B: Página de Notion
curl -X POST "http://localhost:8000/sync/notion" \
  -H "Content-Type: application/json" \
  -d '{"page_id": "abc123..."}'
```

### 2. Verificar Ingesta

```bash
curl http://localhost:8000/stats
```

### 3. Hacer Preguntas

```bash
curl -X POST "http://localhost:8000/ask" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "¿De qué tratan los documentos indexados?"
  }'
```

---

## 🐛 Solución de Problemas

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

**Parte del proyecto:** TFM Bibliotecario-IA
**Versión API:** 0.1.0
**Stack:** FastAPI + LangChain + Ollama + ChromaDB
