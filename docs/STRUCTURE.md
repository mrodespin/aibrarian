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
├── /frontend/                      # Frontend React (Futuro - Fase 1)
│   └── .gitkeep                    # Placeholder hasta la implementación
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

### **Qué contiene cada capa:**

| Capa | Directorio | Responsabilidad |
|------|-----------|-----------------|
| **Domain** | `core/domain/` | Entidades del dominio (`Document`, `Chunk`, `Query`). Estructuras de datos que representan los conceptos principales del sistema, independientes de cualquier infraestructura. |
| **Ports** | `core/ports/` | Interfaces abstractas (contratos). Definen **cómo** hablar con el exterior sin implementar el **cómo**. |
| **Services** | `core/services/` | Lógica de negocio (orquestación). `SyncService` coordina la ingesta, `RAGService` coordina las consultas. Conocen los puertos, pero no saben qué adaptador concreto hay detrás. |
| **Adapters (outbound)** | `adapters/outbound/` | Implementaciones concretas de los puertos. Conectan la lógica de negocio con servicios externos (ChromaDB, Ollama, PDF, Notion). |
| **Adapters (inbound)** | `main.py` + scripts CLI | Puntos de entrada al sistema. Las rutas de FastAPI (`main.py`) y los scripts CLI (`ingest_pdfs.py`, `ingest_notion.py`) actúan de adaptadores de entrada sin un directorio dedicado. |

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

Orquesta los 4 servicios del proyecto:
- **ollama**: LLM local (modelos llama3.2 y nomic-embed-text)
- **chromadb**: Base de datos vectorial
- **api**: API FastAPI
- **n8n**: Automatización de workflows

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
python scripts/ingest_pdfs.py
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
python scripts/ingest_notion.py --page PAGE_ID
```

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
**Stack:** Python + FastAPI + LangChain + Ollama + ChromaDB
