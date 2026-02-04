# 🗂️ Repository Structure

Este proyecto está organizado como un **monorepo** que implementa una **Arquitectura Hexagonal**. Todos los servicios (backend, frontend, datos) están contenidos en este repositorio único, lo que simplifica el desarrollo, deployment y control de versiones.

---

## 🌳 Estructura Completa del Proyecto

```text
/tfm-bibliotecario-ia
│
├── /api/                           # Backend Python (FastAPI)
│   ├── /app/                       # Código de aplicación
│   │   ├── main.py                 # Entry point de FastAPI
│   │   │
│   │   ├── /core/                  # Núcleo Hexagonal (Lógica de Negocio)
│   │   │   ├── /domain/
│   │   │   │   └── models.py       # Entidades de dominio (Document, Chunk, Query)
│   │   │   ├── /ports/             # Interfaces (contratos)
│   │   │   │   ├── vector_db_port.py
│   │   │   │   ├── llm_port.py
│   │   │   │   └── document_processor_port.py
│   │   │   ├── /services/          # Servicios de lógica de negocio
│   │   │   │   ├── sync_service.py      # Pipeline de ingesta
│   │   │   │   └── rag_service.py       # Sistema RAG (consultas)
│   │   │   │
│   │   │   └── /observability/     # Capa de observabilidad
│   │   │       ├── __init__.py          # Configuración de logging (Structlog)
│   │   │       ├── metrics.py           # Métricas Prometheus
│   │   │       └── tracing.py           # OpenTelemetry tracing
│   │   │
│   │   ├── /adapters/              # Adaptadores (implementaciones)
│   │   │   └── /outbound/          # Adaptadores de salida
│   │   │       ├── chromadb_adapter.py
│   │   │       ├── ollama_adapter.py
│   │   │       ├── pdf_processor_adapter.py
│   │   │       └── notion_processor_adapter.py
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
│   ├── verify_setup.py             # Verificación del entorno (8 checks)
│   ├── ingest_pdfs.py              # Ingesta de PDFs (CLI alternativa a API)
│   ├── ingest_notion.py            # Ingesta de Notion (CLI alternativa a API)
│   └── generate_test_pdf.py        # Genera PDF de prueba en /data
│
├── /data/                          # Directorio para PDFs locales (MVP)
│   ├── README.md                   # Instrucciones de uso
│   ├── test_document.pdf           # PDF de ejemplo para testing
│   ├── test_document.txt           # Texto fuente del PDF de ejemplo
│   └── .gitkeep                    # Mantiene el directorio en Git
│
├── /frontend/                      # Frontend React (✅ IMPLEMENTADO)
│   ├── /src/                       # Código fuente
│   │   ├── main.jsx                # Entry point
│   │   ├── App.jsx                 # Root component
│   │   ├── index.css               # Global styles + Tailwind @theme (Dark Mode)
│   │   ├── /api/                   # API client layer
│   │   ├── /hooks/                 # Custom React hooks
│   │   ├── /context/               # React context providers
│   │   ├── /components/            # Componentes React
│   │   │   ├── /layout/            # Layout components
│   │   │   ├── /chat/              # Chat interface
│   │   │   ├── /documents/         # Document management
│   │   │   ├── /stats/             # Statistics panel
│   │   │   └── /common/            # Reusable components
│   │   └── /utils/                 # Utilities (markdown, etc.)
│   ├── package.json                # Dependencies
│   ├── vite.config.js              # Vite configuration
│   ├── tailwind.config.js          # Tailwind CSS configuration
│   ├── postcss.config.js           # PostCSS configuration
│   └── README.md                   # Frontend documentation
│
├── /.ai/                           # Contexto para Agentes IA (Universal)
│   ├── context.md                  # Contexto completo del proyecto (stack, arquitectura, comandos)
│   └── evaluation.md               # Criterios de evaluación del TFM y estado de entrega
│
├── /docs/                          # Documentación Técnica (Humanos)
│   ├── STRUCTURE.md                # Este archivo - estructura y arquitectura
│   └── USAGE.md                    # Documentación de API y uso
│
├── docker-compose.yml              # Orquestación de servicios
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
  - `Document`, `Chunk`, `Query`, `QueryResult`, `SyncResult`
- `ports/`: Interfaces abstractas (contratos)
  - Define CÓMO interactuar con servicios externos sin implementar el CÓMO
- `services/`: Lógica de negocio pura
  - `sync_service.py`: Orquesta la ingesta (load → split → embed → store)
  - `rag_service.py`: Orquesta las consultas (embed query → search → generate)

**🔌 Adapters (Adaptadores)**
- `outbound/`: Implementaciones concretas de los puertos
  - `chromadb_adapter.py`: Implementa VectorDBPort para ChromaDB
  - `ollama_adapter.py`: Implementa LLMPort para Ollama
  - `pdf_processor_adapter.py`: Implementa DocumentProcessorPort para PDFs
  - `notion_processor_adapter.py`: Implementa DocumentProcessorPort para Notion

**⚙️ Config**
- `settings.py`: Configuración centralizada usando Pydantic Settings
  - Carga variables de entorno
  - Valores por defecto
  - Validación de tipos

**📊 Observability (Observabilidad)**
- `observability/`: Capa de observabilidad completa
  - `__init__.py`: Configuración de logging (Structlog)
  - `metrics.py`: Métricas Prometheus (histogramas, contadores)
  - `tracing.py`: OpenTelemetry tracing setup

**Métricas disponibles:**
- `vector_search_latency_seconds`: Latencia de búsquedas vectoriales
- `llm_generation_time_seconds`: Tiempo de generación del LLM
- `documents_synced_total`: Contador de documentos sincronizados
- Endpoint `/metrics` para Prometheus scraping

#### **Endpoints Principales:**

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/` | GET | Health check básico |
| `/health` | GET | Health check detallado |
| `/stats` | GET | Estadísticas de la colección |
| `/sync` | POST | Sincronizar PDF individual |
| `/sync/directory` | POST | Sincronizar directorio de PDFs |
| `/sync/notion` | POST | Sincronizar página de Notion |
| `/sync/notion/database` | POST | Sincronizar base de datos Notion |
| `/ask` | POST | Hacer pregunta al sistema RAG |
| `/documents/{id}` | DELETE | Eliminar documento |

#### **Scripts CLI:**

- `ingest_pdfs.py`: Script independiente para procesar PDFs
  - Procesa archivos individuales o directorios
  - Verifica disponibilidad de servicios
  - Muestra estadísticas de progreso

- `ingest_notion.py`: Script independiente para procesar Notion
  - Procesa páginas individuales o bases de datos
  - Requiere NOTION_API_KEY configurado
  - Manejo de errores robusto

- `verify_setup.py`: Script de verificación del entorno de desarrollo
  - Comprueba versión de Python (3.11+)
  - Valida dependencias Python instaladas
  - Verifica que Ollama está corriendo y tiene los modelos necesarios
  - Comprueba disponibilidad de Docker y ChromaDB
  - Valida estructura del proyecto y directorio de datos
  - Testea el health check de la API (si está activa)

---

### `/data` - Directorio de Documentos (MVP)

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

### `/frontend` - Interfaz Web ✅ **IMPLEMENTADO**

**Lenguaje:** JavaScript (React 18)
**Framework:** React + Vite 5 + Tailwind CSS v4
**Estado:** **Completamente funcional** con Dark Mode

**Estructura:**
```
frontend/src/
├── main.jsx                    # Entry point
├── App.jsx                     # Root component
├── index.css                   # Global styles + Tailwind @theme
│
├── /api/                       # API Client Layer
│   ├── client.js               # Base fetch wrapper
│   ├── health.js               # GET /health, /stats
│   ├── chat.js                 # POST /ask
│   ├── sync.js                 # POST /sync/*
│   └── documents.js            # DELETE /documents/{id}
│
├── /hooks/
│   └── useChat.js              # Chat state management
│
├── /context/
│   └── AppContext.jsx          # Global app state (health, stats)
│
├── /components/
│   ├── /layout/
│   │   ├── Header.jsx          # Top bar + service status
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
│   └── /common/
│       ├── Button.jsx          # Reusable button component
│       ├── Input.jsx           # Reusable input component
│       ├── Badge.jsx           # Status badges
│       ├── Card.jsx            # Card container
│       ├── Spinner.jsx         # Loading spinner
│       └── Alert.jsx           # Alert/notification
│
└── /utils/
    └── markdown.jsx            # Markdown rendering
```

**Funcionalidades implementadas:**
- ✅ **Chat Interface**: Conversación completa con el RAG
- ✅ **Dark Mode**: Diseño profesional
- ✅ **Document Sync UI**: Sincronización de PDFs y Notion desde el frontend
- ✅ **Real-time Stats**: Panel de estadísticas en vivo
- ✅ **Source Visualization**: Fuentes con scores de relevancia y contenido expandible
- ✅ **Responsive Design**: Mobile-first con sidebar colapsable
- ✅ **Service Health**: Indicadores de estado de Ollama, ChromaDB y API

**Integración:**
- Consume todos los endpoints de la API (`/health`, `/stats`, `/ask`, `/sync/*`)
- Polling automático para estadísticas en tiempo real
- Manejo de errores y estados de carga

---

## 🏗️ Arquitectura Hexagonal

El proyecto sigue **Arquitectura Hexagonal (Puertos y Adaptadores)**. Ver diagrama completo en [README.md](../README.md#-arquitectura-del-sistema).

**Capas principales:**
- **Domain** (`core/domain/`): Entidades de negocio
- **Ports** (`core/ports/`): Interfaces abstractas
- **Services** (`core/services/`): Lógica de negocio
- **Adapters** (`adapters/outbound/`): Implementaciones concretas
- **Observability** (`core/observability/`): Logging, métricas y tracing

**Beneficio clave**: Cambiar un adaptador (ej: ChromaDB → Pinecone) no requiere modificar la lógica de negocio

---

## 🔗 Archivos de Configuración Raíz

### `docker-compose.yml`

Orquesta los 3 servicios del proyecto:
- **ollama**: LLM local (modelos llama3.2 y nomic-embed-text) - Puerto 11434
- **chromadb**: Base de datos vectorial - Puerto 8001 (host) → 8000 (contenedor)
- **api**: API FastAPI - Puerto 8000

**Uso:**
```bash
# Iniciar todos los servicios
docker-compose up -d

# Primera vez: descargar modelos de Ollama
docker exec ollama ollama pull llama3.2
docker exec ollama ollama pull nomic-embed-text
```

> **Nota sobre networking:** dentro de Docker los servicios se comunican por nombre de contenedor (`ollama`, `chromadb`). El `docker-compose.yml` sobreescribe automáticamente las URLs en el servicio `api` para usar estos nombres internos, así que no hace falta cambiar nada en `.env`.

### `.env` (no incluido - usar .env.example)

Variables de entorno para configuración:
```bash
# Ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2

# ChromaDB (desarrollo local: puerto mapeado por docker-compose)
CHROMADB_HOST=localhost
CHROMADB_PORT=8001

# Notion (opcional)
NOTION_API_KEY=secret_xxxxx
```

### `README.md`

Documentación principal del proyecto:
- Descripción general
- Diagramas de arquitectura (Mermaid)
- Stack tecnológico
- Instrucciones de setup

### `USAGE.md`

Documentación de API:
- Todos los endpoints con ejemplos
- Request/Response schemas
- Scripts CLI
- Troubleshooting

---

## 📦 Dependencias Principales

**Backend (Python):**
- FastAPI + Uvicorn + Pydantic Settings
- LangChain + LangChain-Ollama + LangChain-Chroma
- ChromaDB, PyPDF, Notion-Client
- Structlog, Prometheus-Client, OpenTelemetry

**Frontend (JavaScript):**
- React 18 + Vite 5
- Tailwind CSS v4 + @tailwindcss/postcss
- Ver `frontend/package.json` para lista completa

Ver `api/requirements.txt` para versiones exactas

---

## 🚀 Flujo de Uso

Ver [README.md - Quick Start](../README.md#-quick-start) para instrucciones completas de instalación y uso.

**Resumen:**
1. **Instalar**: `python3 setup.py` (automático) o manual
2. **Iniciar servicios**: Ollama + API + Frontend
3. **Usar**: Interfaz web en `http://localhost:5173` o API REST

---

## 📚 Documentación Adicional

### Para Humanos
- **[README.md](../README.md)**: Visión general y setup
- **[docs/STRUCTURE.md](STRUCTURE.md)**: Este archivo - estructura y arquitectura
- **[docs/USAGE.md](USAGE.md)**: API endpoints y uso
- **[data/README.md](../data/README.md)**: Instrucciones para PDFs
- **[api/.env.example](../api/.env.example)**: Variables de entorno

### Para Agentes IA
- **[.ai/context.md](../.ai/context.md)**: Contexto completo del proyecto (stack, arquitectura, comandos)
- **[.ai/evaluation.md](../.ai/evaluation.md)**: Criterios de evaluación del TFM y estado de entrega

---

**Proyecto:** TFM Bibliotecario-IA
**Arquitectura:** Hexagonal (Puertos y Adaptadores)
**Stack:** Python + FastAPI + LangChain + Ollama + ChromaDB + React + Observabilidad
