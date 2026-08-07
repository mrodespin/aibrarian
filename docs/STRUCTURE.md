# 🗂️ Repository Structure

Este proyecto está organizado como un **monorepo** que implementa una **Arquitectura Hexagonal**. Todos los servicios (backend, frontend, datos) están contenidos en este repositorio único, lo que simplifica el desarrollo, deployment y control de versiones.

---

## 🌳 Estructura Completa del Proyecto

```text
/tfm-bibliotecario-ia
│
├── /api/                           # Backend Python (FastAPI)
│   ├── /app/                       # Código de aplicación
│   │   ├── main.py                 # Entry point de FastAPI (DI manual + endpoints)
│   │   │
│   │   ├── /core/                  # Núcleo Hexagonal (Lógica de Negocio)
│   │   │   ├── /domain/
│   │   │   │   └── models.py       # Entidades de dominio (Document, Chunk, Query, User...)
│   │   │   ├── /ports/             # Interfaces (contratos)
│   │   │   │   ├── vector_db_port.py
│   │   │   │   ├── llm_port.py
│   │   │   │   ├── document_processor_port.py
│   │   │   │   └── user_repository_port.py
│   │   │   ├── /services/          # Servicios de lógica de negocio
│   │   │   │   ├── sync_service.py      # Pipeline de ingesta
│   │   │   │   ├── rag_service.py       # Sistema RAG (consultas)
│   │   │   │   └── auth_service.py      # Login + emisión/validación de JWT
│   │   │   │
│   │   │   └── observability.py    # Structlog + métricas Prometheus + MetricsMiddleware (un solo fichero)
│   │   │
│   │   ├── /adapters/              # Adaptadores (implementaciones)
│   │   │   └── /outbound/          # Adaptadores de salida
│   │   │       ├── chromadb_adapter.py        # VectorDBPort — ChromaDB local (Docker)
│   │   │       ├── chromadb_cloud_adapter.py  # VectorDBPort — Chroma Cloud (hereda del anterior)
│   │   │       ├── ollama_adapter.py          # LLMPort — Ollama local
│   │   │       ├── groq_adapter.py            # LLMPort — Groq (cloud)
│   │   │       ├── pdf_processor_adapter.py
│   │   │       ├── notion_processor_adapter.py
│   │   │       └── postgres_user_adapter.py   # UserRepositoryPort — Postgres/Neon
│   │   │
│   │   └── /config/
│   │       └── settings.py         # Configuración con Pydantic Settings
│   │
│   ├── requirements.txt            # Dependencias Python
│   ├── .env.example                # Template de variables de entorno
│   └── Dockerfile                  # Imagen Docker para la API
│
├── /scripts/                       # Scripts de Automatización
│   ├── setup.py                    # Instalación automática e interactiva
│   ├── verify_setup.py             # Verificación del entorno (11 checks)
│   ├── ingest_pdfs.py              # Ingesta de PDFs (CLI alternativa a API)
│   ├── ingest_notion.py            # Ingesta de Notion (CLI alternativa a API)
│   ├── create_user.py              # Alta de usuarios de login (sin UI de registro)
│   └── generate_test_pdf.py        # Genera PDF de prueba en /data
│
├── /data/                          # Directorio para PDFs locales (MVP)
│   ├── README.md                   # Instrucciones de uso
│   ├── test_document.pdf           # PDF de ejemplo para testing
│   ├── test_document.txt           # Texto fuente del PDF de ejemplo
│   └── .gitkeep                    # Mantiene el directorio en Git
│
├── /frontend/                      # Frontend React
│   ├── /src/                       # Código fuente
│   │   ├── main.jsx                # Entry point
│   │   ├── App.jsx                 # Root component
│   │   ├── index.css               # Global styles + Tailwind @theme (Dark Mode)
│   │   ├── /api/                   # API client layer (incl. auth.js)
│   │   ├── /hooks/                 # Custom React hooks
│   │   ├── /context/               # React context providers (App, Auth)
│   │   ├── /components/            # Componentes React
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
├── /docs/                          # Documentación Técnica (Humanos)
│   ├── STRUCTURE.md                # Este archivo - estructura y arquitectura
│   ├── USAGE.md                    # Documentación de API y uso
│   ├── USAGE_TESTING.md            # Suite de tests y guía de testing
│   ├── DEPLOYMENT.md               # Despliegue opcional en Render (Groq + Chroma Cloud)
│   └── /adr/                       # Architecture Decision Records
│       ├── INDEX.md                # Índice de decisiones
│       ├── 001-hexagonal-architecture.md
│       ├── 002-native-ollama-macos.md
│       ├── 003-chromadb-vector-store.md
│       ├── 004-query-expansion-rag.md
│       ├── 005-react-vite-frontend.md
│       ├── 006-docker-services-native-ollama.md
│       └── 007-cloud-deployment-groq-chroma.md
│
├── docker-compose.yml              # Orquestación de servicios (ChromaDB + Postgres + API)
├── render.yaml                     # Blueprint de despliegue en Render (API + frontend)
├── .gitignore                      # Archivos ignorados por Git
├── LICENSE                         # Licencia MIT
│
└── README.md                       # Documentación principal del proyecto
```

---

## 📂 Descripción de Componentes

### `/api` - Backend FastAPI

**Lenguaje:** Python
**Framework:** FastAPI + LangChain
**Arquitectura:** Hexagonal (Puertos y Adaptadores)

#### **Estructura Interna:**

**🔷 Core (Núcleo Hexagonal)**
- `domain/models.py`: Entidades de dominio independientes de infraestructura
  - `Document`, `Chunk`, `Query`, `QueryResult`, `SyncResult`, `User`
- `ports/`: Interfaces abstractas (contratos)
  - Define CÓMO interactuar con servicios externos sin implementar el CÓMO
- `services/`: Lógica de negocio pura
  - `sync_service.py`: Orquesta la ingesta (load → split → embed → store)
  - `rag_service.py`: Orquesta las consultas (embed query → search → generate)
  - `auth_service.py`: Verifica credenciales, emite/valida JWT de sesión

**🔌 Adapters (Adaptadores)**
- `outbound/`: Implementaciones concretas de los puertos. La clase concreta de LLM/VectorDB se elige por configuración (`LLM_PROVIDER`/`VECTOR_DB_PROVIDER`), no por código:
  - `chromadb_adapter.py` / `chromadb_cloud_adapter.py`: VectorDBPort (ChromaDB local vs Chroma Cloud)
  - `ollama_adapter.py` / `groq_adapter.py`: LLMPort (Ollama local vs Groq cloud)
  - `pdf_processor_adapter.py`: DocumentProcessorPort para PDFs
  - `notion_processor_adapter.py`: DocumentProcessorPort para Notion
  - `postgres_user_adapter.py`: UserRepositoryPort (Postgres/Neon)

**⚙️ Config**
- `settings.py`: Configuración centralizada usando Pydantic Settings
  - Carga variables de entorno
  - Valores por defecto
  - Validación de tipos

**📊 Observability (Observabilidad)**
- `observability.py`: un único fichero — configuración de logging estructurado (Structlog), métricas Prometheus y `MetricsMiddleware`. No hay tracing distribuido (OpenTelemetry) implementado.

**Métricas disponibles:**
- `vector_search_latency_seconds`: Latencia de búsquedas vectoriales
- `llm_generation_time_seconds`: Tiempo de generación del LLM
- `documents_synced_total`: Contador de documentos sincronizados
- Endpoint `/metrics` para Prometheus scraping

#### **Endpoints Principales:**

🔒 = requiere sesión (token de `POST /auth/login`, enviado como header `Authorization: Bearer`)

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/` | GET | Health check básico (público, usado por Render) |
| `/health` | GET | Health check detallado (público) |
| `/metrics` | GET | Métricas Prometheus (público) |
| `/auth/login` | POST | Iniciar sesión |
| `/auth/logout` | POST | Cerrar sesión |
| `/auth/me` | GET | Usuario de la sesión actual 🔒 |
| `/stats` | GET | Estadísticas de la colección 🔒 |
| `/sync` | POST | Sincronizar PDF individual (ruta local) 🔒 |
| `/sync/upload` | POST | Subir y sincronizar PDF (multipart) 🔒 |
| `/sync/directory` | POST | Sincronizar directorio de PDFs 🔒 |
| `/sync/notion` | POST | Sincronizar página de Notion 🔒 |
| `/sync/notion/database` | POST | Sincronizar base de datos Notion 🔒 |
| `/ask` | POST | Hacer pregunta al sistema RAG 🔒 |
| `/documents/{id}` | DELETE | Eliminar documento 🔒 |

#### **Scripts CLI:**

- `ingest_pdfs.py`: Script independiente para procesar PDFs
  - Procesa archivos individuales o directorios
  - Verifica disponibilidad de servicios
  - Muestra estadísticas de progreso

- `ingest_notion.py`: Script independiente para procesar Notion
  - Procesa páginas individuales o bases de datos
  - Requiere NOTION_API_KEY configurado
  - Manejo de errores robusto

- `create_user.py`: Alta de usuarios de login (sin UI de registro)
  - Contraseña interactiva vía `getpass` (no queda en el historial de la shell)
  - Crea la tabla `users` si no existe (idempotente)

- `verify_setup.py`: Script de verificación del entorno de desarrollo
  - Comprueba versión de Python (3.11+)
  - Valida dependencias Python instaladas
  - Verifica que Ollama está corriendo y tiene los modelos necesarios
  - Comprueba disponibilidad de Docker y ChromaDB
  - Valida estructura del proyecto y directorio de datos
  - Testea el health check de la API (si está activa)

---

### `/data` - Directorio de Documentos

**Propósito:** Almacena PDFs locales para ingesta

Este directorio es la fuente de datos del MVP. Los PDFs aquí son procesados por:
1. Script CLI: `python scripts/ingest_pdfs.py`
2. API: `POST /sync/directory`

**Estructura:**
```
/data/
├── README.md              # Instrucciones de uso
├── test_document.pdf      # PDF de ejemplo (generado por scripts/generate_test_pdf.py)
├── test_document.txt      # Texto fuente del PDF de ejemplo
├── .gitkeep               # Mantiene directorio en Git
└── *.pdf                  # Tus documentos PDF
```

Los archivos `test_document.*` y `create_test_pdf.py` están destinados a testing del pipeline de ingesta sin necesidad de aportar PDFs externos.

---

### `/frontend` - Interfaz Web

**Lenguaje:** JavaScript (React 19)
**Framework:** React + Vite 7 + Tailwind CSS v4
**Estado:** **Completamente funcional** con Dark Mode

**Estructura:**
```
frontend/src/
├── main.jsx                    # Entry point
├── App.jsx                     # Root component
├── index.css                   # Global styles + Tailwind @theme
│
├── /api/                       # API Client Layer
│   ├── client.js               # Base fetch wrapper (adjunta el JWT como header Authorization, ver tokenStorage.js)
│   ├── tokenStorage.js         # Guarda/lee el JWT en localStorage
│   ├── auth.js                 # POST /auth/login, /auth/logout, GET /auth/me
│   ├── health.js               # GET /health, /stats
│   ├── chat.js                 # POST /ask
│   ├── sync.js                 # POST /sync/*
│   └── documents.js            # DELETE /documents/{id}
│
├── /hooks/
│   └── useChat.js              # Chat state management
│
├── /context/
│   ├── AppContext.jsx          # Global app state (health, stats)
│   └── AuthContext.jsx         # Sesión actual (login/logout/isAuthenticated)
│
├── /components/
│   ├── /layout/
│   │   ├── Header.jsx          # Top bar + service status + usuario/logout
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
│   │   └── SyncForm.jsx        # PDF/Notion sync interface
│   │
│   ├── /stats/
│   │   └── StatsPanel.jsx      # Service stats + collection info
│   │
│   ├── /auth/
│   │   └── LoginPage.jsx       # Pantalla de login (sin sesión activa)
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
    ├── markdown.jsx            # Markdown rendering
    └── providerLabels.js       # Etiquetas legibles para llm_provider/vector_db_provider
```

**Integración:**
- Consume todos los endpoints de la API (`/auth/*`, `/health`, `/stats`, `/ask`, `/sync/*`)
- `App.jsx` gatea el árbol autenticado: sin sesión válida muestra `LoginPage`, no monta `AppProvider` (evita pollear `/stats` sin login)
- Polling automático para estadísticas en tiempo real
- Manejo de errores y estados de carga

---

## 🔗 Archivos de Configuración Raíz

### `docker-compose.yml`

Contiene **3 servicios**:
- **ChromaDB**: Base de datos vectorial en puerto 8001
- **Postgres**: Usuarios/autenticación en puerto 5432
- **API**: Backend FastAPI en puerto 8000

**Ollama** corre **nativo** en macOS para aprovechar GPU Metal (~10x más rápido):
- Instalación: `brew install ollama && ollama serve`

**Arquitectura de red:**
- La API en Docker se conecta a Ollama en el host via `host.docker.internal`
- La API se conecta a ChromaDB via red interna de Docker (`chromadb:8000`)
- La API se conecta a Postgres via red interna de Docker (`postgres:5432`)

### `render.yaml`

Blueprint de despliegue en Render (opcional, no reemplaza el desarrollo local): crea `bibliotecario-ia-api` (Docker) y `bibliotecario-ia-frontend` (Static Site). La API usa Groq + Chroma Cloud en vez de Ollama + ChromaDB local — ver [ADR-007](adr/007-cloud-deployment-groq-chroma.md) y [docs/DEPLOYMENT.md](DEPLOYMENT.md).

---

## 📦 Dependencias Principales

**Backend (Python):**
- FastAPI + Uvicorn + Pydantic Settings
- LangChain (solo `PyPDFLoader`, `NotionDBLoader`, `RecursiveCharacterTextSplitter` — no orquesta el pipeline RAG, eso es código propio) + LangChain-Ollama
- ChromaDB, PyPDF, Notion-Client
- Groq (cliente oficial, cuando `LLM_PROVIDER=groq`)
- asyncpg, PyJWT, bcrypt (autenticación)
- Structlog, Prometheus-Client (sin tracing distribuido / OpenTelemetry)

**Frontend (JavaScript):**
- React 19 + Vite 7
- Tailwind CSS v4 + @tailwindcss/postcss
- Ver `frontend/package.json` para lista completa

Ver `api/requirements.txt` para versiones exactas

---