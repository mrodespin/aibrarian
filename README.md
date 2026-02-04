# 🤖 tfm-bibliotecario-ia

![TFM](https://img.shields.io/badge/Proyecto-TFM_MDEV_IA-blue.svg)
![Licencia](https://img.shields.io/badge/Licencia-MIT-green.svg)

TFM que implementa un asistente RAG ('Bibliotecario IA') para consultar documentos (PDFs locales y Notion) usando Ollama y LangChain.

---

## 📖 Descripción del Proyecto

**`bibliotecario-ia`** es un Trabajo Final de Máster que demuestra la implementación de un sistema RAG (Retrieval-Augmented Generation) de principio a fin, enfocado en la privacidad y la arquitectura de software desacoplada.

El objetivo es crear un *chatbot* capaz de responder preguntas sobre una base de conocimiento privada (alojada en **Notion**) utilizando un modelo de lenguaje que se ejecuta localmente (**Ollama**). Esto garantiza que los datos sensibles nunca abandonen la máquina local.

El sistema se construye sobre una **Arquitectura Hexagonal** para asegurar que los componentes (API, lógica de IA, bases de datos) estén desacoplados y sean fáciles de mantener o sustituir.

## 🛠️ Stack Tecnológico

* **Framework Backend:** **Python** con **FastAPI**
* **Orquestación de IA:** **LangChain** con **Query Expansion**
* **Modelo de Lenguaje (LLM):** **Ollama** (ej. `llama3.2`)
* **Base de Datos Vectorial:** **ChromaDB**
* **Fuentes de Datos:** **PDFs locales** y **Notion API**
* **Frontend:** **React 18** + **Vite 5** + **Tailwind CSS v4** (Dark Mode)
* **Observabilidad:** **Structlog** + **Prometheus** + **OpenTelemetry**
* **Contenerización:** **Docker Compose**

---

## 🏛️ Arquitectura del Sistema

El proyecto sigue un patrón de **Arquitectura Hexagonal (Puertos y Adaptadores)** y se desarrolla en fases incrementales:

* **MVP (Verde):** Pipeline de ingesta de PDFs locales - Garantiza funcionalidad básica del TFM
* **Fase 1 (Azul):** Sistema RAG completo para consultas - El chatbot IA con frontend React
* **Extensión (Naranja):** Integración con Notion API - Valor añadido y diferenciación

```mermaid
graph TD
    %% --- Definiciones de Estilo ---
    classDef mvp fill:#f0fff0,stroke:#2e6b2e,stroke-width:2px;
    classDef phase1 fill:#e6f7ff,stroke:#0056b3,stroke-width:2px;
    classDef extension fill:#fff3e0,stroke:#f57c00,stroke-width:2px;
    classDef observability fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px;

    %% --- Fuentes de Datos ---
    subgraph "Fuentes de Documentos"
        PDFs["PDFs Locales<br>/data/*.pdf"]
        NotionAPI["Notion API<br>Páginas y Bases de Datos"]
    end

    %% --- Adaptadores de Entrada ---
    subgraph "Capa de Presentación"
        UI["Frontend React<br>Chat + Sync UI<br>Dark Mode"]
        CLI["Scripts CLI<br>ingest_pdfs.py<br>ingest_notion.py"]
        API["FastAPI REST<br>/sync, /ask, /health"]
    end

    %% --- Observabilidad ---
    subgraph "Observabilidad"
        Logging["Structlog<br>Logging Estructurado"]
        Metrics["Prometheus<br>Métricas"]
        Tracing["OpenTelemetry<br>Tracing"]
    end

    %% --- Núcleo Hexagonal ---
    subgraph "Núcleo de Negocio (Hexágono)"
        SyncService["SyncService<br>Pipeline de Ingesta"]
        RAGService["RAGService<br>Query Expansion + RAG"]
        Ports["Puertos<br>DocumentProcessor<br>LLM<br>VectorDB"]
    end

    %% --- Adaptadores de Salida ---
    subgraph "Adaptadores Externos"
        PDFAdapter["PDFProcessor<br>PyPDFLoader"]
        NotionAdapter["NotionProcessor<br>Notion Client"]
        OllamaAdapter["Ollama<br>LLM + Embeddings"]
        ChromaAdapter["ChromaDB<br>Vector Store"]
    end

    %% --- Conexiones Presentación ---
    UI --> API
    CLI --> API
    PDFs --> CLI
    NotionAPI --> UI

    %% --- Conexiones API a Servicios ---
    API --> SyncService
    API --> RAGService

    %% --- Conexiones Servicios a Puertos ---
    SyncService --> Ports
    RAGService --> Ports

    %% --- Conexiones Puertos a Adaptadores ---
    Ports --> PDFAdapter
    Ports --> NotionAdapter
    Ports --> OllamaAdapter
    Ports --> ChromaAdapter

    %% --- Observabilidad ---
    API -.-> Logging
    SyncService -.-> Metrics
    RAGService -.-> Tracing

    %% --- Asignación de Clases ---
    class PDFs,CLI,SyncService,PDFAdapter,ChromaAdapter mvp
    class UI,RAGService,OllamaAdapter,API phase1
    class NotionAPI,NotionAdapter extension
    class Logging,Metrics,Tracing observability
    class Ports mvp
```
---

## 🔄 Flujos de Trabajo por Fases

El sistema implementa flujos de ingesta y consulta que demuestran la arquitectura hexagonal en acción.

### **MVP: Ingesta de PDFs Locales**
Pipeline de ingesta simple y robusto. Garantiza funcionalidad core del sistema sin dependencias externas. (Verde).

```mermaid
flowchart TD
    %% --- Definiciones de Estilo ---
    classDef mvp fill:#f0fff0,stroke:#2e6b2e,stroke-width:2px;

    %% --- Nodos ---
    A["PDFs en /data"]
    B["Script CLI / API<br>ingest_pdfs.py<br>POST /sync"]
    C["SyncService<br>Orquestación"]
    D["PyPDFLoader<br>Carga y extracción"]
    E["RecursiveTextSplitter<br>División en chunks"]
    F["Ollama<br>Generación de embeddings"]
    G["ChromaDB<br>Almacenamiento vectorial"]

    %% --- Asignación de Clases ---
    class A,B,C,D,E,F,G mvp

    %% --- Flujo MVP ---
    A -->|"1. Lee archivos"| B
    B -->|"2. Inicia pipeline"| C
    C -->|"3. Procesa PDF"| D
    D -->|"4. Divide texto"| E
    E -->|"5. Vectoriza chunks"| F
    F -->|"6. Almacena vectores"| G
```

### **Extensión: Integración con Notion**
Mismo pipeline, diferente adaptador. Demuestra la flexibilidad de la arquitectura hexagonal. (Naranja).

```mermaid
flowchart TD
    %% --- Definiciones de Estilo ---
    classDef extension fill:#fff3e0,stroke:#f57c00,stroke-width:2px;
    classDef mvp fill:#f0fff0,stroke:#2e6b2e,stroke-width:2px;

    %% --- Nodos ---
    A["Notion Pages"]
    B["Script CLI / API<br>ingest_notion.py<br>POST /sync/notion"]
    C["SyncService<br>(Misma lógica)"]
    D["NotionProcessor<br>Extrae contenido"]
    E["RecursiveTextSplitter<br>(Mismo proceso)"]
    F["Ollama<br>(Mismos embeddings)"]
    G["ChromaDB<br>(Mismo storage)"]

    %% --- Asignación de Clases ---
    class A,B,D extension
    class C,E,F,G mvp

    %% --- Flujo Notion ---
    A -->|"1. API call"| B
    B -->|"2. Inicia pipeline"| C
    C -->|"3. Procesa página"| D
    D -->|"4. Divide texto"| E
    E -->|"5. Vectoriza chunks"| F
    F -->|"6. Almacena vectores"| G
```

### **Fase 1: Sistema RAG (Chatbot)**
El chatbot inteligente con Query Expansion que responde preguntas usando la base de conocimientos indexada. (Azul).

```mermaid
flowchart TD
    %% --- Definiciones de Estilo ---
    classDef mvp fill:#f0fff0,stroke:#2e6b2e,stroke-width:2px;
    classDef phase1 fill:#e6f7ff,stroke:#0056b3,stroke-width:2px;

    %% --- Nodos ---
    A["Usuario<br>Hace pregunta"]
    B["Frontend React<br>Chat Interface"]
    C["API FastAPI<br>POST /ask"]
    D["RAGService<br>Orquestador"]
    QE["Query Expansion<br>LLM genera keywords"]
    E["Ollama Embeddings<br>Vectoriza pregunta"]
    F["ChromaDB<br>Búsqueda similaridad<br>+ keyword filter"]
    G["RAGService<br>Construye prompt"]
    H["Ollama LLM<br>Genera respuesta"]
    I["Respuesta + Fuentes<br>al usuario"]

    %% --- Asignación de Clases ---
    class A,B,C,D,QE,E,G,H,I phase1
    class F mvp

    %% --- Flujo Fase 1 ---
    A --> B
    B --> C
    C --> D
    D -->|"1. Query Expansion"| QE
    QE -->|"2. Keywords extraídos"| D
    D -->|"3. Embedding query"| E
    E -->|"4. Vector pregunta"| D
    D -->|"5. Búsqueda híbrida"| F
    F -->|"6. Top-K chunks<br>(PDFs/Notion)"| D
    D -->|"7. Prompt con contexto"| G
    G -->|"8. Genera respuesta"| H
    H -->|"9. Respuesta + fuentes"| D
    D --> C
    C --> B
    B --> I
```

---

## 🔍 Observabilidad

El sistema incluye una **capa completa de observabilidad** para monitoreo en producción:

### **Logging Estructurado** (Structlog)
- Logs en formato JSON para fácil parsing
- Contexto enriquecido (request_id, user_id, timestamps)
- Niveles configurables por módulo

### **Métricas** (Prometheus)
- `vector_search_latency_seconds`: Latencia de búsquedas vectoriales
- `llm_generation_time_seconds`: Tiempo de generación del LLM
- `documents_synced_total`: Contador de documentos procesados
- Endpoint `/metrics` para scraping

### **Tracing** (OpenTelemetry)
- Trazas distribuidas end-to-end
- Spans para cada operación crítica
- Integración con Jaeger/Zipkin (opcional)

**Arquitectura de Observabilidad:**

```mermaid
graph LR
    %% --- Definiciones de Estilo ---
    classDef app fill:#e6f7ff,stroke:#0056b3,stroke-width:2px;
    classDef obs fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px;
    classDef external fill:#fff3e0,stroke:#f57c00,stroke-width:2px;

    %% --- Aplicación ---
    subgraph "Aplicación"
        API["FastAPI<br>Endpoints"]
        Services["Services<br>RAGService<br>SyncService"]
        Adapters["Adapters<br>Ollama<br>ChromaDB"]
    end

    %% --- Capa de Observabilidad ---
    subgraph "Observability Layer"
        Logger["Structlog<br>Structured Logging"]
        Metrics["Prometheus<br>Metrics Registry"]
        Tracer["OpenTelemetry<br>Tracing"]
    end

    %% --- Sistemas Externos ---
    subgraph "External Systems (Opcional)"
        LogAgg["Log Aggregator<br>ELK/Loki"]
        MetricsDB["Prometheus Server<br>Time Series DB"]
        TracingBackend["Jaeger/Zipkin<br>Tracing Backend"]
    end

    %% --- Flujo de Observabilidad ---
    API --> Logger
    API --> Metrics
    API --> Tracer

    Services --> Logger
    Services --> Metrics
    Services --> Tracer

    Adapters --> Logger
    Adapters --> Metrics

    %% --- Exportación ---
    Logger -.->|JSON Logs| LogAgg
    Metrics -.->|/metrics endpoint| MetricsDB
    Tracer -.->|OTLP| TracingBackend

    %% --- Asignación de Clases ---
    class API,Services,Adapters app
    class Logger,Metrics,Tracer obs
    class LogAgg,MetricsDB,TracingBackend external
```

**Ejemplo de uso:**
```python
# Los logs estructurados se generan automáticamente
logger.info("Query processed",
           query=query,
           results_count=len(sources),
           latency=duration)

# Las métricas se registran automáticamente
VECTOR_SEARCH_LATENCY.observe(duration)
```

---

## 📚 Documentación

| Documento | Descripción |
|-----------|-------------|
| **[docs/STRUCTURE.md](docs/STRUCTURE.md)** | Arquitectura y estructura del proyecto |
| **[docs/USAGE.md](docs/USAGE.md)** | API endpoints y scripts CLI |
| **[docs/USAGE_TESTING.md](docs/USAGE_TESTING.md)** | Suite de tests y guía de testing |
| **[.ai/context.md](.ai/context.md)** | Contexto para agentes IA |

---

## 🚀 Quick Start

### Prerequisitos

1. **Python 3.11+**
2. **Docker** (para ChromaDB)
3. **Ollama** instalado localmente (Para Mac/Desarrollo local) o en Docker (Para entornos productivos)

### Instalación

**Opción 1: Instalación Automática (Recomendada)**

```bash
# 1. Clonar repositorio
git clone <URL_DEL_REPO>
cd tfm-bibliotecario-ia

# 2. Ejecutar script de instalación
python3 setup.py
```

El script `setup.py` te guiará interactivamente por todo el proceso:
- Detecta qué está instalado y qué falta
- Te permite elegir entre Modo Docker o Modo Local/Híbrido
- Instala sólo lo necesario
- Configura el entorno automáticamente
- Ejecuta verificación al final

**Opción 2: Instalación Manual**

```bash
# 1. Clonar repositorio
git clone <URL_DEL_REPO>
cd tfm-bibliotecario-ia

# 2. Instalar Ollama y descargar modelos
brew install ollama  # macOS
ollama pull llama3.2
ollama pull nomic-embed-text

# 3. Setup Python
cd api
python -m venv venv
source venv/bin/activate  # macOS/Linux
pip install -r requirements.txt

# 4. Configurar variables de entorno
cp .env.example .env
# Editar .env con tus valores

# 5. Iniciar ChromaDB
cd ..
docker-compose up -d chromadb

# 6. Verificar setup
python scripts/verify_setup.py
```

### Uso Básico

**Opción A: Con Frontend (Recomendado)**

```bash
# Terminal 1: Ollama
ollama serve

# Terminal 2: ChromaDB
docker-compose up -d chromadb

# Terminal 3: API Backend
cd api && source venv/bin/activate
uvicorn app.main:app --reload

# Terminal 4: Frontend React
cd frontend
npm install  # Solo la primera vez
npm run dev

# Abrir navegador en http://localhost:5173
```

El frontend incluye:
- 💬 **Chat Interface** con Dark Mode
- 📊 **Panel de Estadísticas** en tiempo real
- 📁 **Sincronización de Documentos** (PDF y Notion) desde la UI
- 📈 **Visualización de Fuentes** con scores de relevancia

**Opción B: Solo API (sin Frontend)**

```bash
# Terminal 1: Ollama + API
ollama serve &
cd api && source venv/bin/activate
uvicorn app.main:app --reload

# Terminal 2: Ingestar documentos
python scripts/ingest_pdfs.py

# Terminal 3: Hacer consultas vía cURL
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "¿De qué tratan los documentos?"}'
```

Ver [docs/USAGE.md](docs/USAGE.md) para documentación completa de la API y scripts CLI.

---

## 📄 Licencia

Este proyecto está bajo la licencia MIT. Ver [LICENSE](LICENSE) para más detalles.

---

**Proyecto:** TFM Bibliotecario-IA
**Arquitectura:** Hexagonal (Puertos y Adaptadores)
**Stack:** Python + FastAPI + LangChain + Ollama + ChromaDB
