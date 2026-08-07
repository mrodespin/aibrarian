# 📚 API & Services Documentation (AIbrarian)

This documentation covers every service, port, and endpoint of AIbrarian's API.

> **Authentication:** since login was added, every endpoint except `/`, `/health` and `/metrics` requires a valid session (a JWT issued by `POST /auth/login`, sent as `Authorization: Bearer <token>` on the rest of the requests — not as a cookie, to avoid Safari ITP blocking cross-site cookies when the frontend and API are on different domains). The cURL examples in this guide assume you've already logged in and are reusing the token. See the [Authentication](#-authentication) section below.

---

## 🌐 Project Services

When you run the system, these are the services involved:

| Service | Local URL | Internal URL (Docker) | Purpose |
| :--- | :--- | :--- | :--- |
| **FastAPI API** | `http://localhost:8000` | `http://api:8000` | The project's main API (ingestion and queries) |
| **ChromaDB** | `http://localhost:8001` | `http://chromadb:8000` | Vector database for embeddings |
| **Ollama** | `http://localhost:11434` | `http://ollama:11434` | Local LLM (text generation and embeddings) |
| **Postgres** | `localhost:5432` | `postgres:5432` | Users/authentication |

**Note on ports:** ChromaDB exposes port 8001 on the host to avoid clashing with the API (which uses 8000). Internally in Docker, ChromaDB uses port 8000.

---

## 🤖 FastAPI Endpoints

The project's main API, running on `http://localhost:8000`. Endpoints marked with 🔒 require a session (a token from `/auth/login`, sent as an `Authorization: Bearer <token>` header).

### 🔐 Authentication

There's no public signup — users are created with `scripts/create_user.py` (see [CLI Scripts](#-cli-scripts)).

#### `POST /auth/login` - Log In

Verifies credentials and, if correct, returns a session JWT (24h by default) in the response body. The client must store it and resend it as the `Authorization: Bearer <access_token>` header on the rest of the requests.

**Request Body:**
```json
{
  "email": "you@email.com",
  "password": "..."
}
```

**Response (200 OK):**
```json
{
  "id": 1,
  "email": "you@email.com",
  "access_token": "eyJhbGciOi...",
  "token_type": "bearer"
}
```

**Response (401):** incorrect credentials.

**cURL example:**
```bash
TOKEN=$(curl -s -X POST "http://localhost:8000/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email": "you@email.com", "password": "..."}' | jq -r .access_token)
```

---

#### `POST /auth/logout` - Log Out

The JWT is stateless (no server-side blocklist): this endpoint doesn't invalidate anything — it's the client's job to discard the stored token.

**Response (200 OK):**
```json
{"status": "success"}
```

---

#### `GET /auth/me` - Current User 🔒

Returns the active session's user. Useful for checking whether a token is still valid.

**Response (200 OK):**
```json
{
  "id": 1,
  "email": "you@email.com"
}
```

**Response (401):** no token, or an invalid/expired token.

**cURL example** (reuses the `access_token` obtained at login):
```bash
curl -H "Authorization: Bearer $TOKEN" "http://localhost:8000/auth/me"
```

---

### 📊 Utility Endpoints

#### `GET /` - Basic Health Check

Verifies the API is running. **No authentication** — this is the endpoint Render uses as the service's healthcheck.

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

#### `GET /health` - Detailed Health Check

Verifies the status of every service and the configuration. **No authentication.**

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
    "collection": "aibrarian_docs",
    "data_directory": "./data"
  }
}
```

> The `services.ollama` key reflects the active LLM's availability even when it's Groq (the name is kept for frontend compatibility, see ADR-007).

---

#### `GET /stats` - Collection Statistics 🔒

Retrieves information about the knowledge base. **Requires a session.**

**Response (200 OK):**
```json
{
  "collection": "aibrarian_docs",
  "stats": {
    "count": 42,
    "dimensions": 768,
    "collection_name": "aibrarian_docs"
  },
  "model_info": {
    "llm_model": "llama3.2",
    "embedding_model": "nomic-embed-text"
  }
}
```

---

## 📥 Ingestion Endpoints (MVP)

### `POST /sync` - Sync a Single PDF 🔒

Processes a PDF file and indexes it in the vector database.

**Request Body:**
```json
{
  "file_path": "./data/document.pdf",
  "collection_name": "aibrarian_docs"  // Optional
}
```

**Response (200 OK):**
```json
{
  "document_id": "pdf_a1b2c3d4",
  "chunks_created": 15,
  "success": true,
  "message": "Document synced successfully to collection 'aibrarian_docs'",
  "processing_time": 8.42
}
```

**cURL example:**
```bash
curl -H "Authorization: Bearer $TOKEN" -X POST "http://localhost:8000/sync" \
  -H "Content-Type: application/json" \
  -d '{
    "file_path": "./data/manual.pdf"
  }'
```

---

### `POST /sync/upload` - Upload and Sync a PDF 🔒

Like `/sync`, but accepts the file itself (`multipart/form-data`) instead of a local path — this is what the frontend's sync panel uses, and the only one that works in production (where the server has no access to the client's filesystem).

**cURL example:**
```bash
curl -H "Authorization: Bearer $TOKEN" -X POST "http://localhost:8000/sync/upload" \
  -F "file=@document.pdf"
```

---

### `POST /sync/directory` - Sync a Directory of PDFs 🔒

Processes every PDF file in a directory.

**Query Parameters:**
- `directory_path` (optional): the directory's path. Defaults to `./data`

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

**cURL example:**
```bash
# Use the default directory (./data)
curl -H "Authorization: Bearer $TOKEN" -X POST "http://localhost:8000/sync/directory"

# Specify a directory
curl -H "Authorization: Bearer $TOKEN" -X POST "http://localhost:8000/sync/directory?directory_path=/path/to/pdfs"
```

---

## 🔗 Notion Integration Endpoints

### `POST /sync/notion` - Sync a Notion Page 🔒

Processes a Notion page and indexes it in the vector database.

**Prerequisites:**
- The `NOTION_API_KEY` environment variable set
- The page shared with your Notion integration

**Request Body:**
```json
{
  "page_id": "a1b2c3d4e5f6",  // Page ID or URL
  "collection_name": "aibrarian_docs"  // Optional
}
```

**Response (200 OK):**
```json
{
  "document_id": "notion_a1b2c3d4e5f6",
  "chunks_created": 12,
  "success": true,
  "message": "Document synced successfully to collection 'aibrarian_docs'",
  "processing_time": 6.18
}
```

**cURL example:**
```bash
curl -H "Authorization: Bearer $TOKEN" -X POST "http://localhost:8000/sync/notion" \
  -H "Content-Type: application/json" \
  -d '{
    "page_id": "https://www.notion.so/My-Page-abc123..."
  }'
```

---

### `POST /sync/notion/database` - Sync a Notion Database 🔒

Processes every page in a Notion database.

**Request Body:**
```json
{
  "database_id": "a1b2c3d4e5f6",  // Optional, uses the env var if not provided
  "max_pages": 10,  // Optional, caps the number of pages
  "collection_name": "aibrarian_docs"  // Optional
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
      "message": "Synced 'Page Title'"
    }
  ]
}
```

**cURL example:**
```bash
curl -H "Authorization: Bearer $TOKEN" -X POST "http://localhost:8000/sync/notion/database" \
  -H "Content-Type: application/json" \
  -d '{
    "database_id": "abc123...",
    "max_pages": 5
  }'
```

---

## 💬 Query Endpoint

### `POST /ask` - Ask the RAG System a Question 🔒

Asks a question about the indexed documents and gets an AI-generated answer.

**Request Body:**
```json
{
  "question": "What is the document's main topic?",
  "session_id": "user_session_123",  // Optional
  "max_results": 4  // Optional, number of context chunks (1-10)
}
```

**Response (200 OK):**
```json
{
  "question": "What is the document's main topic?",
  "answer": "The document's main topic is the implementation of RAG systems...",
  "source_documents": [
    {
      "document_id": "pdf_a1b2c3d4",
      "chunk_content": "RAG systems combine information retrieval...",
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

**cURL example:**
```bash
curl -H "Authorization: Bearer $TOKEN" -X POST "http://localhost:8000/ask" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What is RAG?"
  }'
```

---

## 🗑️ Deletion Endpoint

### `DELETE /documents/{document_id}` - Delete a Document 🔒

Deletes every chunk of a document from the vector database.

**Path Parameters:**
- `document_id`: the ID of the document to delete

**Response (200 OK):**
```json
{
  "status": "success",
  "message": "Document pdf_a1b2c3d4 deleted"
}
```

**cURL example:**
```bash
curl -H "Authorization: Bearer $TOKEN" -X DELETE "http://localhost:8000/documents/pdf_a1b2c3d4"
```

---

## 🛠️ CLI Scripts

Besides the API, the project includes automation scripts in the `scripts/` directory:

### 1. `setup.py` - Automated Installation

Installs and configures the whole development environment interactively.

```bash
python3 scripts/setup.py
```

**What it does:** checks the OS, installs Homebrew/Ollama/Docker, sets up Python/venv, creates `.env` (with a generated `JWT_SECRET_KEY`), brings up ChromaDB + Postgres + API in Docker, runs `verify_setup.py`, and finally offers to create your user (`create_user.py`) — there's no signup UI, so without this you can't log in.

---

### 2. `verify_setup.py` - Environment Verification

Verifies that every service is correctly installed (11 checks: Python, dependencies, Ollama, Docker, ChromaDB, Postgres/auth, project structure, data, API, Node.js, frontend).

```bash
python scripts/verify_setup.py
```

**Output:** a colored report with ✅ success, ❌ error, ⚠️ warning.

---

### 3. `ingest_pdfs.py` - PDF Ingestion

Processes PDFs and ingests them into ChromaDB. CLI alternative to the API's `/sync` endpoints.

```bash
# Process every PDF in /data
python scripts/ingest_pdfs.py

# Process a specific directory
python scripts/ingest_pdfs.py /path/to/pdfs

# Process a specific file
python scripts/ingest_pdfs.py --file document.pdf

# Use a different collection
python scripts/ingest_pdfs.py --collection my_collection
```

**Prerequisite:** `source api/venv/bin/activate` (needs the FastAPI/LangChain dependencies)

---

### 4. `ingest_notion.py` - Notion Ingestion

Ingests Notion content. CLI alternative to `/sync/notion`.

```bash
# A single page
python scripts/ingest_notion.py --page PAGE_ID

# A whole database
python scripts/ingest_notion.py --database DATABASE_ID

# Cap the number of pages
python scripts/ingest_notion.py --database DATABASE_ID --max 10
```

**Prerequisite:**
- `NOTION_API_KEY` in `api/.env`
- `source api/venv/bin/activate`

---

### 5. `generate_test_pdf.py` - Generate a Test PDF

Generates `data/test_document.pdf` with content about the project, for testing.

```bash
python scripts/generate_test_pdf.py
```

**Output:** `data/test_document.pdf` (~2 pages)

---

### 6. `create_user.py` - Create a Login User

There's no signup UI — this is the only way to create a user. Asks for the password interactively (`getpass`, twice to confirm) instead of as an argument, so it never lands in the shell history.

```bash
python scripts/create_user.py --email you@email.com
```

**Prerequisite:**
- `DATABASE_URL` set in `api/.env` (local) or as an environment variable (e.g. to create the first user against Neon in production)
- `source api/venv/bin/activate`

**Output:** `✅ User created: you@email.com (id=1)`. Also creates the `users` table if it doesn't exist yet (idempotent).

---

## 🔐 Notion Setup

To use the Notion endpoints:

1. **Create a Notion integration:**
   - Go to https://www.notion.so/my-integrations
   - Create a new integration
   - Copy the "Internal Integration Token"

2. **Set the environment variable:**
   ```bash
   export NOTION_API_KEY=secret_xxxxxxxxxxxxx
   ```

3. **Share pages:**
   - Open the page in Notion
   - Click "..." → "Add connections"
   - Select your integration

---

## 📖 Interactive Documentation

FastAPI automatically generates interactive documentation:

- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

From these interfaces you can:
- See every available endpoint
- Try API calls directly
- View request/response schemas
- Generate example code

---

## 🚀 Typical Workflow

### 1. Create a user and log in (once)

```bash
python scripts/create_user.py --email you@email.com

TOKEN=$(curl -s -X POST "http://localhost:8000/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email": "you@email.com", "password": "..."}' | jq -r .access_token)
```

### 2. Index Documents

```bash
# Option A: local PDFs
curl -H "Authorization: Bearer $TOKEN" -X POST "http://localhost:8000/sync/directory"

# Option B: a Notion page
curl -H "Authorization: Bearer $TOKEN" -X POST "http://localhost:8000/sync/notion" \
  -H "Content-Type: application/json" \
  -d '{"page_id": "abc123..."}'
```

### 3. Verify Ingestion

```bash
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/stats
```

### 4. Ask Questions

```bash
curl -H "Authorization: Bearer $TOKEN" -X POST "http://localhost:8000/ask" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What are the indexed documents about?"
  }'
```

---

## 🐛 Troubleshooting

### `401 Not authenticated`

```json
{
  "detail": "Not authenticated"
}
```

**Fix:** the token is missing (or expired — 24h by default). Log in again and reuse the returned `access_token`:
```bash
TOKEN=$(curl -s -X POST "http://localhost:8000/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email": "you@email.com", "password": "..."}' | jq -r .access_token)
# ...then use -H "Authorization: Bearer $TOKEN" on the following requests
```

If you don't have a user yet: `python scripts/create_user.py --email you@email.com`.

### Ollama unavailable

```json
{
  "ollama_available": false
}
```

**Fix:**
```bash
# Start Ollama
ollama serve

# Check installed models
ollama list

# Pull the required models
ollama pull llama3.2
ollama pull nomic-embed-text
```

### ChromaDB unavailable

```json
{
  "chromadb_available": false
}
```

**Fix:**
```bash
# Start ChromaDB with Docker
docker-compose up -d chromadb
```

### Error syncing Notion

```json
{
  "detail": "Notion API key not configured"
}
```

**Fix:**
```bash
# Set the API key
export NOTION_API_KEY=secret_xxxxxxxxxxxxx

# Or add it to the .env file
echo "NOTION_API_KEY=secret_xxxxxxxxxxxxx" >> api/.env
```

---

## 🖥️ Frontend (React + Vite)

The project includes a web frontend for interacting with the RAG system.

### Requirements

- **Node.js 18+** (recommended: use `nvm` or `fnm`)
- **npm** (included with Node.js)

### Installation

```bash
# 1. Go to the frontend directory
cd frontend

# 2. Install dependencies
npm install

# 3. Configure environment variables (optional)
cp .env.example .env
# Edit .env if the API isn't on localhost:8000
```

### Running It

```bash
# Development mode (with hot-reload)
cd frontend
npm run dev
```

The frontend will be available at: **http://localhost:5173**

### Production Build

```bash
# Generate an optimized build
npm run build

# Files are generated under frontend/dist/
```

### Configuration

The frontend is configured via environment variables in `frontend/.env`:

| Variable | Default | Description |
|----------|-------------------|-------------|
| `VITE_API_URL` | `http://localhost:8000` | The FastAPI API's URL |

---
