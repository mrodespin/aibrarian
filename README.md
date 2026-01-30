# 🤖 tfm-bibliotecario-ia

![TFM](https://img.shields.io/badge/Proyecto-TFM_MDEV_IA-blue.svg)
![Licencia](https://img.shields.io/badge/Licencia-MIT-green.svg)

TFM que implementa un asistente RAG ('Bibliotecario IA') para consultar documentos de Notion usando Ollama y LangChain, con sincronización automática vía n8n.

---

## 📖 Descripción del Proyecto

**`bibliotecario-ia`** es un Trabajo Final de Máster que demuestra la implementación de un sistema RAG (Retrieval-Augmented Generation) de principio a fin, enfocado en la privacidad y la arquitectura de software desacoplada.

El objetivo es crear un *chatbot* capaz de responder preguntas sobre una base de conocimiento privada (alojada en **Notion**) utilizando un modelo de lenguaje que se ejecuta localmente (**Ollama**). Esto garantiza que los datos sensibles nunca abandonen la máquina local.

El sistema se construye sobre una **Arquitectura Hexagonal** para asegurar que los componentes (API, lógica de IA, bases de datos) estén desacoplados y sean fáciles de mantener o sustituir.

## 🛠️ Stack Tecnológico

* **Framework Backend:** **Python** con **FastAPI**
* **Orquestación de IA:** **LangChain**
* **Modelo de Lenguaje (LLM):** **Ollama** (ej. `llama3` o `mistral`)
* **Base de Datos Vectorial:** **ChromaDB**
* **Fuente de Datos:** **Notion API**
* **Automatización / Sincronización:** **n8n** (self-hosted)
* **Contenerización:** **Docker Compose**

---

## 🏛️ Arquitectura del Sistema

El proyecto sigue un patrón de **Arquitectura Hexagonal (Puertos y Adaptadores)** y se desarrolla en fases incrementales:

* **MVP (Verde):** Pipeline de ingesta de PDFs locales - Garantiza funcionalidad básica del TFM
* **Fase 1 (Azul):** Sistema RAG completo para consultas - El chatbot IA
* **Extensión (Naranja):** Integración con Notion API - Valor añadido y diferenciación
* **Futuro (Gris):** Automatización con n8n y notificaciones - Mejoras opcionales

```mermaid
graph TD
    %% --- Definiciones de Estilo ---
    classDef mvp fill:#f0fff0,stroke:#2e6b2e,stroke-width:2px;
    classDef phase1 fill:#e6f7ff,stroke:#0056b3,stroke-width:2px;
    classDef extension fill:#fff3e0,stroke:#f57c00,stroke-width:2px;
    classDef future fill:#f5f5f5,stroke:#999,stroke-width:2px,stroke-dasharray: 5 5;

    %% --- Fuentes de Datos ---
    subgraph "Fuentes de Documentos"
        PDFs["PDFs Locales<br>/data/*.pdf"]
        NotionAPI["Notion API<br>Páginas y Bases de Datos"]
    end

    %% --- Adaptadores de Entrada ---
    subgraph "Capa de Presentación"
        CLI["Scripts CLI<br>ingest_pdfs.py<br>ingest_notion.py"]
        API["FastAPI REST<br>/sync, /ask"]
        UI["Frontend Web<br>(React)"]
        N8N["n8n Workflows<br>(Futuro)"]
    end

    %% --- Núcleo Hexagonal ---
    subgraph "Núcleo de Negocio (Hexágono)"
        SyncService["SyncService<br>Pipeline de Ingesta"]
        RAGService["RAGService<br>Consultas Q&A"]
        Ports["Puertos<br>DocumentProcessor<br>LLM<br>VectorDB"]
    end

    %% --- Adaptadores de Salida ---
    subgraph "Adaptadores Externos"
        PDFAdapter["PDFProcessor<br>PyPDFLoader"]
        NotionAdapter["NotionProcessor<br>Notion Client"]
        OllamaAdapter["Ollama<br>LLM + Embeddings"]
        ChromaAdapter["ChromaDB<br>Vector Store"]
    end

    %% --- Conexiones MVP (Verde) ---
    PDFs --> CLI
    CLI --> API
    API --> SyncService
    SyncService --> Ports
    Ports --> PDFAdapter
    Ports --> OllamaAdapter
    Ports --> ChromaAdapter

    %% --- Conexiones Fase 1 (Azul) ---
    UI --> API
    API --> RAGService
    RAGService --> Ports

    %% --- Conexiones Extensión (Naranja) ---
    NotionAPI --> API
    Ports --> NotionAdapter

    %% --- Conexiones Futuro (Gris) ---
    N8N -.-> API

    %% --- Asignación de Clases ---
    class PDFs,CLI,SyncService,PDFAdapter,ChromaAdapter mvp
    class UI,RAGService,OllamaAdapter phase1
    class NotionAPI,NotionAdapter extension
    class N8N future
    class API,Ports mvp
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
El chatbot inteligente que responde preguntas usando la base de conocimientos indexada. (Azul).

```mermaid
flowchart TD
    %% --- Definiciones de Estilo ---
    classDef mvp fill:#f0fff0,stroke:#2e6b2e,stroke-width:2px;
    classDef phase1 fill:#e6f7ff,stroke:#0056b3,stroke-width:2px;

    %% --- Nodos ---
    A["Usuario<br>Hace pregunta"]
    B["Frontend Web<br>Interfaz chat"]
    C["API FastAPI<br>POST /ask"]
    D["RAGService<br>Orquestador"]
    E["Ollama Embeddings<br>Vectoriza pregunta"]
    F["ChromaDB<br>Búsqueda similaridad"]
    G["RAGService<br>Construye prompt"]
    H["Ollama LLM<br>Genera respuesta"]
    I["Respuesta + Fuentes<br>al usuario"]

    %% --- Asignación de Clases ---
    class A,B,C,D,E,G,H,I phase1
    class F mvp

    %% --- Flujo Fase 1 ---
    A --> B
    B --> C
    C --> D
    D -->|"1. Embedding query"| E
    E -->|"2. Vector pregunta"| D
    D -->|"3. Busca contexto"| F
    F -->|"4. Top-K chunks<br>(PDFs/Notion)"| D
    D -->|"5. Prompt con contexto"| G
    G -->|"6. Genera respuesta"| H
    H -->|"7. Respuesta + fuentes"| D
    D --> C
    C --> B
    B --> I
```

### **Futuro: Automatización con n8n**
Mejoras opcionales para automatizar sincronización y notificaciones. (Gris - No implementado).

**Posibles extensiones:**
- Workflow n8n que detecte cambios en Notion y sincronice automáticamente
- Notificaciones por email cuando se añaden nuevos documentos
- Webhooks para integración con otros sistemas
- Sincronización programada (cron jobs)

Estas mejoras quedan documentadas como evolución natural del proyecto, pero no son necesarias para demostrar el valor del TFM.

---

## 📚 Documentación

| Documento | Descripción |
|-----------|-------------|
| **[docs/STRUCTURE.md](docs/STRUCTURE.md)** | Arquitectura y estructura del proyecto |
| **[docs/USAGE.md](docs/USAGE.md)** | API endpoints y ejemplos |
| **[docs/PYTHON_GUIDE.md](docs/PYTHON_GUIDE.md)** | Guía de Python para JS devs |
| **[.ai/context.md](.ai/context.md)** | Contexto para agentes IA |

---

## 🚀 Quick Start

### Prerequisitos

1. **Python 3.11+**
2. **Docker** (para ChromaDB)
3. **Ollama** instalado localmente

### Instalación

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
cd api
python verify_setup.py
```

### Uso Básico

```bash
# Terminal 1: Ollama
ollama serve

# Terminal 2: API
cd api && source venv/bin/activate
uvicorn app.main:app --reload

# Terminal 3: Ingestar documentos
python api/ingest_pdfs.py --directory data/

# Terminal 4: Hacer consultas
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "¿De qué tratan los documentos?"}'
```

Ver [docs/USAGE.md](docs/USAGE.md) para documentación completa de la API.

---

## 📄 Licencia

Este proyecto está bajo la licencia MIT. Ver [LICENSE](LICENSE) para más detalles.

---

**Proyecto:** TFM Bibliotecario-IA
**Arquitectura:** Hexagonal (Puertos y Adaptadores)
**Stack:** Python + FastAPI + LangChain + Ollama + ChromaDB
