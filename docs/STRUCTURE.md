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
│   │   │   └── /services/          # Servicios de lógica de negocio
│   │   │       ├── sync_service.py      # Pipeline de ingesta
│   │   │       └── rag_service.py       # Sistema RAG (consultas)
│   │   │
│   │   ├── /adapters/              # Adaptadores (implementaciones)
│   │   │   ├── /inbound/           # Adaptadores de entrada (futuros)
│   │   │   └── /outbound/          # Adaptadores de salida
│   │   │       ├── chromadb_adapter.py
│   │   │       ├── ollama_adapter.py
│   │   │       ├── pdf_processor_adapter.py
│   │   │       └── notion_processor_adapter.py
│   │   │
│   │   └── /config/
│   │       └── settings.py         # Configuración con Pydantic Settings
│   │
│   ├── ingest_pdfs.py              # Script CLI para ingestar PDFs
│   ├── ingest_notion.py            # Script CLI para ingestar Notion
│   ├── requirements.txt            # Dependencias Python
│   ├── .env.example                # Template de variables de entorno
│   └── Dockerfile                  # Imagen Docker para la API
│
├── /data/                          # Directorio para PDFs locales (MVP)
│   ├── README.md                   # Instrucciones de uso
│   └── .gitkeep                    # Mantiene el directorio en Git
│
├── /frontend/                      # Frontend React (Futuro - Fase 1)
│   ├── /src/                       # Código fuente React
│   ├── package.json                # Dependencias JavaScript
│   └── Dockerfile                  # (Opcional) Imagen Docker
│
├── /.ai/                           # Contexto para Agentes IA (Universal)
│   ├── README.md                   # Índice de documentos para IAs
│   ├── project-context.md          # Contexto completo del TFM
│   ├── python-guide.md             # Guía de Python para JS devs
│   └── portability.md              # Guía de portabilidad
│
├── /docs/                          # Documentación Técnica (Humanos)
│   ├── README.md                   # Índice de documentación
│   ├── USAGE.md                    # Documentación de API
│   └── TESTING_GUIDE.md            # Guía de testing
│
├── docker-compose.yml              # Orquestación de servicios
├── .gitignore                      # Archivos ignorados por Git
├── LICENSE                         # Licencia MIT
│
├── README.md                       # Documentación principal del proyecto
└── STRUCTURE.md                    # Este archivo - estructura del repo
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

---

### `/data` - Directorio de Documentos (MVP)

**Propósito:** Almacena PDFs locales para ingesta

Este directorio es la fuente de datos del MVP. Los PDFs aquí son procesados por:
1. Script CLI: `python api/ingest_pdfs.py`
2. API: `POST /sync/directory`

**Estructura:**
```
/data/
├── README.md          # Instrucciones de uso
├── .gitkeep           # Mantiene directorio en Git
└── *.pdf              # Tus documentos PDF
```

---

### `/frontend` - Interfaz Web (Fase 1)

**Lenguaje:** JavaScript
**Framework:** React + Vite
**Estado:** Estructura básica (implementación futura)

**Funcionalidad planeada:**
- Interfaz de chat para interactuar con el RAG
- Visualización de fuentes de información
- Historial de conversaciones
- Muestra de metadatos de documentos

**Integración:**
- Consume endpoint `POST /ask` para consultas
- Muestra respuestas y fuentes devueltas por la API

---

## 🏗️ Arquitectura Hexagonal Explicada

La estructura del proyecto implementa **Arquitectura Hexagonal** (también conocida como Puertos y Adaptadores):

```
┌─────────────────────────────────────────────────────┐
│                    Adaptadores                      │
│                    de Entrada                       │
│         (FastAPI, CLI Scripts, Frontend)            │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│              NÚCLEO HEXAGONAL                       │
│                                                     │
│  ┌─────────────┐         ┌─────────────┐          │
│  │  Services   │────────▶│   Ports     │          │
│  │  (Lógica)   │         │ (Interfaces)│          │
│  └─────────────┘         └─────────────┘          │
│         │                        ▲                 │
│         │                        │                 │
│         ▼                        │                 │
│  ┌─────────────┐                 │                │
│  │   Domain    │                 │                │
│  │  (Modelos)  │                 │                │
│  └─────────────┘                 │                │
└──────────────────────────────────┼─────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────┐
│                Adaptadores                          │
│                de Salida                            │
│    (ChromaDB, Ollama, PDF, Notion)                 │
└─────────────────────────────────────────────────────┘
```

### **Ventajas de esta Arquitectura:**

1. **Testabilidad**: Los servicios pueden probarse con mocks de los puertos
2. **Intercambiabilidad**: Cambiar ChromaDB por Pinecone solo requiere crear un nuevo adaptador
3. **Independencia**: La lógica de negocio no depende de frameworks específicos
4. **Mantenibilidad**: Cambios en implementaciones no afectan la lógica core
5. **Escalabilidad**: Fácil agregar nuevas fuentes de datos (Google Docs, Confluence, etc.)

### **Ejemplo Práctico:**

Para agregar soporte para Google Docs:
1. ✅ Crear `google_docs_adapter.py` que implemente `DocumentProcessorPort`
2. ✅ Inyectar el adaptador en `SyncService`
3. ❌ **NO** necesitas cambiar `SyncService` (ya funciona con cualquier `DocumentProcessorPort`)
4. ❌ **NO** necesitas cambiar `RAGService` (no sabe de dónde vienen los datos)

---

## 🔗 Archivos de Configuración Raíz

### `docker-compose.yml`

Orquesta los servicios del proyecto:
- **chromadb**: Base de datos vectorial
- **api** (futuro): API FastAPI en contenedor
- **frontend** (futuro): UI React en contenedor

**Uso actual:**
```bash
# Solo ChromaDB (Ollama corre en host)
docker-compose up -d chromadb
```

### `.env` (no incluido - usar .env.example)

Variables de entorno para configuración:
```bash
# Ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2

# ChromaDB
CHROMADB_HOST=localhost
CHROMADB_PORT=8000

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

### Python (Backend)

**Core API:**
- `fastapi` - Framework web moderno y rápido
- `uvicorn` - Servidor ASGI
- `pydantic-settings` - Gestión de configuración

**LangChain & RAG:**
- `langchain` - Framework para aplicaciones LLM
- `langchain-ollama` - Integración con Ollama
- `langchain-chroma` - Integración con ChromaDB

**Document Processing:**
- `pypdf` - Lectura de PDFs
- `notion-client` - Cliente de Notion API

**Utilities:**
- `chromadb` - Cliente de base de datos vectorial
- `httpx` - Cliente HTTP asíncrono
- `tenacity` - Lógica de reintentos

---

## 🚀 Flujo de Desarrollo

### 1. MVP - Ingesta de PDFs
```bash
# 1. Colocar PDFs en /data
cp mis_documentos/*.pdf data/

# 2. Ejecutar ingesta
cd api
python ingest_pdfs.py
```

### 2. Fase 1 - Consultas RAG
```bash
# 1. Iniciar API
uvicorn app.main:app --reload

# 2. Hacer consultas
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "¿De qué trata el documento?"}'
```

### 3. Extensión - Notion
```bash
# 1. Configurar API key
export NOTION_API_KEY=secret_xxx

# 2. Sincronizar página
python ingest_notion.py --page PAGE_ID
```

---

## 📚 Documentación Adicional

### Para Humanos
- **[README.md](README.md)**: Visión general y setup
- **[STRUCTURE.md](STRUCTURE.md)**: Este archivo - estructura y arquitectura
- **[docs/USAGE.md](docs/USAGE.md)**: API endpoints y uso
- **[docs/TESTING_GUIDE.md](docs/TESTING_GUIDE.md)**: Guía de testing
- **[data/README.md](data/README.md)**: Instrucciones para PDFs
- **[api/.env.example](api/.env.example)**: Variables de entorno

### Para Agentes IA
- **[.ai/README.md](.ai/README.md)**: Índice de contexto para IAs
- **[.ai/project-context.md](.ai/project-context.md)**: Contexto completo del TFM
- **[.ai/python-guide.md](.ai/python-guide.md)**: Guía de Python para JS devs
- **[.ai/portability.md](.ai/portability.md)**: Guía de portabilidad

---

**Proyecto:** TFM Bibliotecario-IA
**Arquitectura:** Hexagonal (Puertos y Adaptadores)
**Stack:** Python + FastAPI + LangChain + Ollama + ChromaDB
