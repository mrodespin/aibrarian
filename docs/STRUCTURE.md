# 🗂️ Repository Structure

This project is organized as a **monorepo** implementing a **Hexagonal Architecture**. All services (backend, frontend, data) live in this single repository, which simplifies development, deployment and version control.

---

## 🌳 Full Project Structure

```text
/aibrarian
│
├── /api/                           # Python backend (FastAPI)
│   ├── /app/                       # Application code
│   │   ├── main.py                 # FastAPI entry point (manual DI + endpoints)
│   │   │
│   │   ├── /core/                  # Hexagonal core (business logic)
│   │   │   ├── /domain/
│   │   │   │   └── models.py       # Domain entities (Document, Chunk, Query, User...)
│   │   │   ├── /ports/             # Interfaces (contracts)
│   │   │   │   ├── vector_db_port.py
│   │   │   │   ├── llm_port.py
│   │   │   │   ├── document_processor_port.py
│   │   │   │   └── user_repository_port.py
│   │   │   ├── /services/          # Business logic services
│   │   │   │   ├── sync_service.py      # Ingestion pipeline
│   │   │   │   ├── rag_service.py       # RAG system (queries)
│   │   │   │   └── auth_service.py      # Login + JWT issuance/validation
│   │   │   │
│   │   │   └── observability.py    # Structlog + Prometheus metrics + MetricsMiddleware (a single file)
│   │   │
│   │   ├── /adapters/              # Adapters (implementations)
│   │   │   └── /outbound/          # Outbound adapters
│   │   │       ├── chromadb_adapter.py        # VectorDBPort — local ChromaDB (Docker)
│   │   │       ├── chromadb_cloud_adapter.py  # VectorDBPort — Chroma Cloud (inherits from the previous one)
│   │   │       ├── ollama_adapter.py          # LLMPort — local Ollama
│   │   │       ├── groq_adapter.py            # LLMPort — Groq (cloud)
│   │   │       ├── pdf_processor_adapter.py
│   │   │       ├── notion_processor_adapter.py
│   │   │       └── postgres_user_adapter.py   # UserRepositoryPort — Postgres/Neon
│   │   │
│   │   └── /config/
│   │       └── settings.py         # Configuration via Pydantic Settings
│   │
│   ├── requirements.txt            # Python dependencies
│   ├── .env.example                # Environment variable template
│   └── Dockerfile                  # Docker image for the API
│
├── /scripts/                       # Automation Scripts
│   ├── setup.py                    # Automated, interactive installation
│   ├── verify_setup.py             # Environment verification (11 checks)
│   ├── ingest_pdfs.py              # PDF ingestion (CLI alternative to the API)
│   ├── ingest_notion.py            # Notion ingestion (CLI alternative to the API)
│   ├── create_user.py              # Create login users (no signup UI)
│   └── generate_test_pdf.py        # Generates a test PDF in /data
│
├── /data/                          # Directory for local PDFs (MVP)
│   ├── README.md                   # Usage instructions
│   ├── test_document.pdf           # Sample PDF for testing
│   ├── test_document.txt           # Sample PDF's source text
│   └── .gitkeep                    # Keeps the directory in Git
│
├── /frontend/                      # React frontend
│   ├── /src/                       # Source code
│   │   ├── main.jsx                # Entry point
│   │   ├── App.jsx                 # Root component
│   │   ├── index.css               # Global styles + Tailwind @theme (Dark Mode)
│   │   ├── /api/                   # API client layer (incl. auth.js)
│   │   ├── /hooks/                 # Custom React hooks
│   │   ├── /context/               # React context providers (App, Auth)
│   │   ├── /components/            # React components
│   │   │   ├── /layout/            # Layout components
│   │   │   ├── /chat/              # Chat interface
│   │   │   ├── /documents/         # Document management
│   │   │   ├── /stats/             # Statistics panel
│   │   │   ├── /auth/              # LoginPage
│   │   │   └── /common/            # Reusable components
│   │   └── /utils/                 # Utilities (markdown, etc.)
│   ├── package.json                # Dependencies
│   ├── vite.config.js              # Vite configuration
│   ├── postcss.config.js           # PostCSS configuration
│   └── README.md                   # Frontend documentation
│
├── /docs/                          # Technical documentation
│   ├── STRUCTURE.md                # This file - structure and architecture
│   ├── USAGE.md                    # API and usage documentation
│   ├── USAGE_TESTING.md            # Test suite and testing guide
│   ├── DEPLOYMENT.md               # Optional deployment on Render (Groq + Chroma Cloud)
│   └── /adr/                       # Architecture Decision Records
│       ├── INDEX.md                # Decision index
│       ├── 001-hexagonal-architecture.md
│       ├── 002-native-ollama-macos.md
│       ├── 003-chromadb-vector-store.md
│       ├── 004-query-expansion-rag.md
│       ├── 005-react-vite-frontend.md
│       ├── 006-docker-services-native-ollama.md
│       └── 007-cloud-deployment-groq-chroma.md
│
├── docker-compose.yml              # Service orchestration (ChromaDB + Postgres + API)
├── render.yaml                     # Render deployment blueprint (API + frontend)
├── .gitignore                      # Files ignored by Git
├── LICENSE                         # MIT License
│
└── README.md                       # Main project documentation
```

---

## 📂 Component Overview

### `/api` - FastAPI Backend

**Language:** Python
**Framework:** FastAPI + LangChain
**Architecture:** Hexagonal (Ports and Adapters)

#### **Internal Structure:**

**🔷 Core (the hexagon)**
- `domain/models.py`: infrastructure-independent domain entities
  - `Document`, `Chunk`, `Query`, `QueryResult`, `SyncResult`, `User`
- `ports/`: abstract interfaces (contracts)
  - Defines HOW to talk to external services without implementing the HOW
- `services/`: pure business logic
  - `sync_service.py`: orchestrates ingestion (load → split → embed → store)
  - `rag_service.py`: orchestrates queries (embed query → search → generate)
  - `auth_service.py`: verifies credentials, issues/validates session JWTs

**🔌 Adapters**
- `outbound/`: concrete implementations of the ports. The concrete LLM/VectorDB class is chosen via configuration (`LLM_PROVIDER`/`VECTOR_DB_PROVIDER`), not in code:
  - `chromadb_adapter.py` / `chromadb_cloud_adapter.py`: VectorDBPort (local ChromaDB vs. Chroma Cloud)
  - `ollama_adapter.py` / `groq_adapter.py`: LLMPort (local Ollama vs. cloud Groq)
  - `pdf_processor_adapter.py`: DocumentProcessorPort for PDFs
  - `notion_processor_adapter.py`: DocumentProcessorPort for Notion
  - `postgres_user_adapter.py`: UserRepositoryPort (Postgres/Neon)

**⚙️ Config**
- `settings.py`: centralized configuration via Pydantic Settings
  - Loads environment variables
  - Default values
  - Type validation

**📊 Observability**
- `observability.py`: a single file — structured logging (Structlog) configuration, Prometheus metrics, and `MetricsMiddleware`. No distributed tracing (OpenTelemetry) implemented.

**Available metrics:**
- `vector_search_latency_seconds`: vector search latency
- `llm_generation_time_seconds`: LLM generation time
- `documents_synced_total`: synced-documents counter
- `/metrics` endpoint for Prometheus scraping

#### **Main Endpoints:**

🔒 = requires a session (token from `POST /auth/login`, sent as the `Authorization: Bearer` header)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Basic health check (public, used by Render) |
| `/health` | GET | Detailed health check (public) |
| `/metrics` | GET | Prometheus metrics (public) |
| `/auth/login` | POST | Log in |
| `/auth/logout` | POST | Log out |
| `/auth/me` | GET | Current session's user 🔒 |
| `/stats` | GET | Collection statistics 🔒 |
| `/sync` | POST | Sync a single PDF (local path) 🔒 |
| `/sync/upload` | POST | Upload and sync a PDF (multipart) 🔒 |
| `/sync/directory` | POST | Sync a directory of PDFs 🔒 |
| `/sync/notion` | POST | Sync a Notion page 🔒 |
| `/sync/notion/database` | POST | Sync a Notion database 🔒 |
| `/ask` | POST | Ask the RAG system a question 🔒 |
| `/documents/{id}` | DELETE | Delete a document 🔒 |

#### **CLI Scripts:**

- `ingest_pdfs.py`: standalone script for processing PDFs
  - Processes individual files or directories
  - Checks service availability
  - Shows progress statistics

- `ingest_notion.py`: standalone script for processing Notion
  - Processes individual pages or databases
  - Requires NOTION_API_KEY to be configured
  - Robust error handling

- `create_user.py`: creates login users (no signup UI)
  - Interactive password via `getpass` (doesn't end up in the shell history)
  - Creates the `users` table if it doesn't exist (idempotent)

- `verify_setup.py`: development environment verification script
  - Checks the Python version (3.11+)
  - Validates installed Python dependencies
  - Verifies Ollama is running with the required models
  - Checks Docker and ChromaDB availability
  - Validates the project structure and data directory
  - Tests the API's health check (if it's running)

---

### `/data` - Document Directory

**Purpose:** stores local PDFs for ingestion

This directory is the MVP's data source. PDFs here are processed by:
1. The CLI script: `python scripts/ingest_pdfs.py`
2. The API: `POST /sync/directory`

**Structure:**
```
/data/
├── README.md              # Usage instructions
├── test_document.pdf      # Sample PDF (generated by scripts/generate_test_pdf.py)
├── test_document.txt      # Sample PDF's source text
├── .gitkeep               # Keeps the directory in Git
└── *.pdf                  # Your PDF documents
```

The `test_document.*` files and `generate_test_pdf.py` exist to test the ingestion pipeline without needing to supply external PDFs.

---

### `/frontend` - Web Interface

**Language:** JavaScript (React 19)
**Framework:** React + Vite 7 + Tailwind CSS v4
**Status:** **Fully functional**, with Dark Mode

**Structure:**
```
frontend/src/
├── main.jsx                    # Entry point
├── App.jsx                     # Root component
├── index.css                   # Global styles + Tailwind @theme
│
├── /api/                       # API Client Layer
│   ├── client.js               # Base fetch wrapper (attaches the JWT as an Authorization header, see tokenStorage.js)
│   ├── tokenStorage.js         # Reads/writes the JWT in localStorage
│   ├── auth.js                 # POST /auth/login, /auth/logout, GET /auth/me
│   ├── health.js               # GET /health, /stats
│   ├── chat.js                 # POST /ask, /ask/stream
│   ├── sync.js                 # POST /sync/*
│   └── documents.js            # GET/DELETE /documents/{id}
│
├── /hooks/
│   ├── useChat.js              # Chat state management
│   ├── useApp.js               # Consumes AppContext (health/stats)
│   ├── useAuth.js              # Consumes AuthContext (session)
│   └── useViewportHeight.js    # iOS keyboard/viewport workaround
│
├── /context/
│   ├── AppContext.jsx          # Global app state (health, stats)
│   └── AuthContext.jsx         # Current session (login/logout/isAuthenticated)
│
├── /components/
│   ├── /layout/
│   │   ├── Header.jsx          # Top bar + service status + user/logout
│   │   ├── Sidebar.jsx         # Stats + Documents panel
│   │   └── Layout.jsx          # Main layout grid
│   │
│   ├── /chat/
│   │   ├── ChatContainer.jsx   # Chat orchestrator
│   │   ├── MessageList.jsx     # Scrollable messages
│   │   ├── MessageItem.jsx     # Single message bubble
│   │   ├── ChatInput.jsx       # Textarea + send button
│   │   └── SourceCard.jsx      # Document source with relevance
│   │
│   ├── /documents/
│   │   ├── DocumentPanel.jsx   # Document management container
│   │   ├── DocumentList.jsx    # Indexed document browser (GET /documents)
│   │   └── SyncForm.jsx        # PDF/Notion sync interface
│   │
│   ├── /stats/
│   │   └── StatsPanel.jsx      # Service stats + collection info
│   │
│   ├── /auth/
│   │   └── LoginPage.jsx       # Login screen (no active session)
│   │
│   └── /common/
│       ├── Button.jsx          # Reusable button component
│       ├── Input.jsx           # Reusable input component
│       ├── Badge.jsx           # Status badges
│       ├── Card.jsx            # Card container
│       ├── Spinner.jsx         # Loading spinner
│       └── Alert.jsx           # Alert/notification
│
└── /utils/
    ├── markdown.jsx            # MarkdownContent component
    ├── renderMarkdown.js       # Markdown → HTML conversion logic
    └── providerLabels.js       # Human-readable labels for llm_provider/vector_db_provider
```

**Integration:**
- Consumes every API endpoint (`/auth/*`, `/health`, `/stats`, `/ask`, `/sync/*`)
- `App.jsx` gates the authenticated tree: with no valid session it shows `LoginPage` and doesn't mount `AppProvider` (avoids polling `/stats` before login)
- Automatic polling for real-time statistics
- Error handling and loading states

---

## 🔗 Root Configuration Files

### `docker-compose.yml`

Contains **3 services**:
- **ChromaDB**: vector database on port 8001
- **Postgres**: users/authentication on port 5432
- **API**: FastAPI backend on port 8000

**Ollama** runs **natively** on macOS to take advantage of the Metal GPU (~10x faster):
- Installation: `brew install ollama && ollama serve`

**Network architecture:**
- The API in Docker connects to Ollama on the host via `host.docker.internal`
- The API connects to ChromaDB over Docker's internal network (`chromadb:8000`)
- The API connects to Postgres over Docker's internal network (`postgres:5432`)

### `render.yaml`

Render deployment blueprint (optional, doesn't replace local development): creates `aibrarian-api` (Docker) and `aibrarian-frontend` (Static Site). The API uses Groq + Chroma Cloud instead of Ollama + local ChromaDB — see [ADR-007](adr/007-cloud-deployment-groq-chroma.md) and [docs/DEPLOYMENT.md](DEPLOYMENT.md).

---

## 📦 Main Dependencies

**Backend (Python):**
- FastAPI + Uvicorn + Pydantic Settings
- LangChain (only `PyPDFLoader`, `NotionDBLoader`, `RecursiveCharacterTextSplitter` — it doesn't orchestrate the RAG pipeline itself, that's custom code) + LangChain-Ollama
- ChromaDB, PyPDF, Notion-Client
- Groq (official client, when `LLM_PROVIDER=groq`)
- asyncpg, PyJWT, bcrypt (authentication)
- Structlog, Prometheus-Client (no distributed tracing / OpenTelemetry)

**Frontend (JavaScript):**
- React 19 + Vite 7
- Tailwind CSS v4 + @tailwindcss/postcss
- See `frontend/package.json` for the full list

See `api/requirements.txt` for exact versions

---
