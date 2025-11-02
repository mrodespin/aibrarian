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

El proyecto sigue un patrón de **Arquitectura Hexagonal (Puertos y Adaptadores)** y se desarrolla en tres fases claras:

* **MVP (Base de Datos):** El *pipeline* de ingesta y sincronización de datos. (Componentes en verde).
* **Fase 1 (Chatbot):** La interfaz de usuario y la API de consulta. (Componentes en azul).
* **Fase 2 (Futuro):** El sistema de notificaciones. (Componentes en gris discontinuo).

```mermaid
graph TD
    %% --- Definiciones de Estilo ---
    classDef mvp fill:#f0fff0,stroke:#2e6b2e,stroke-width:2px;
    classDef phase1 fill:#e6f7ff,stroke:#0056b3,stroke-width:2px;
    classDef phase2 fill:#f5f5f5,stroke:#999,stroke-width:2px,stroke-dasharray: 5 5;

    %% --- Nodos de Entrada ---
    subgraph "Adaptadores de Entrada (Driving)"
        direction LR
        UI("Interfaz Web")
        N8N("Workflow n8n<br><i>Disparador: Notion actualizado</i>")
    end

    %% --- Nodos del Nucleo ---
    subgraph "Núcleo de la Aplicación (Hexágono)"
        direction TB
        Port_API["Puerto: API REST<br>(askQuestion)"]
        Port_Sync["Puerto: Sincronización<br>(syncDocuments)"]
        CoreLogic["Lógica de Negocio<br>- Orquestación RAG<br>- Gestión de Chat<br>- Procesamiento de Documentos"]
        Port_LLM["Puerto: Generador LLM"]
        Port_DB["Puerto: Base de Datos Vectorial"]
        Port_Email["Puerto: Notificador"]
    end
    
    %% --- Nodos de Salida ---
    subgraph "Adaptadores de Salida (Driven / Servicios)"
        direction LR
        Adapter_LLM("Ollama")
        Adapter_DB("ChromaDB")
        Adapter_Email("Servicio Email")
    end

    %% --- Nodos Externos (n8n) ---
    subgraph "Servicios Externos (Usados por n8n)"
        Adapter_Notion("API de Notion")
    end

    %% --- Asignación de Clases ---
    class N8N,Port_Sync,CoreLogic,Port_DB,Adapter_DB,Adapter_Notion mvp
    class UI,Port_API,Port_LLM,Adapter_LLM phase1
    class Port_Email,Adapter_Email phase2

    %% --- Conexiones ---
    Port_API --> CoreLogic
    Port_Sync --> CoreLogic
    CoreLogic --> Port_LLM
    CoreLogic --> Port_DB
    CoreLogic --> Port_Email      
    UI --> Port_API
    N8N --> Port_Sync
    Port_LLM --> Adapter_LLM
    Port_DB --> Adapter_DB
    Port_Email --> Adapter_Email
    N8N -- "usa el 'Nodo Notion'" --> Adapter_Notion

    %% --- Estilos de Links (Fases 1 y 2) ---
    linkStyle 0 stroke:#0056b3,stroke-width:2px;
    linkStyle 2 stroke:#0056b3,stroke-width:2px;
    linkStyle 4 stroke:#999,stroke-width:2px,stroke-dasharray: 5 5;
    linkStyle 5 stroke:#0056b3,stroke-width:2px;
    linkStyle 7 stroke:#0056b3,stroke-width:2px;
    linkStyle 9 stroke:#999,stroke-width:2px,stroke-dasharray: 5 5;
```
---

## 🔄 Flujos de Trabajo por Fases

El sistema se divide en tres flujos funcionales claros que definen la hoja de ruta del proyecto.

* **MVP: Flujo de Sincronización de Contenidos**
Este es el pipeline de ingesta de datos. Su único trabajo es mover el conocimiento desde Notion a la base de datos vectorial. (Todo en verde).

```mermaid
flowchart TD
    %% --- Definiciones de Estilo ---
    classDef mvp fill:#f0fff0,stroke:#2e6b2e,stroke-width:2px;

    %% --- Nodos ---
    A("Notion API")
    C("n8n Workflow")
    D["API de FastAPI (Endpoint /sync)"]
    E["LangChain (Procesador)"]
    F["ChromaDB (Base de Datos Vectorial)"]
    
    %% --- Asignación de Clases ---
    class A,C,D,E,F mvp

    %% --- Flujo MVP (Corregido) ---
    C -->|"1. 'Nodo Notion Trigger'<br>Pide docs"| A
    A -->|2. Entrega páginas| C
    C -->|3. Envía a procesar| D
    D --> E
    E -->|4. Trocea y vectoriza| F
    F -->|5. Datos guardados| E
    E --> D
    D --> C
```

* **Fase 1 (Chatbot): Flujo de Consulta del Usuario (Q&A)**

Este es el chatbot. Utiliza los datos creados por el MVP (ChromaDB en verde) y los componentes de IA (en azul) para responder preguntas.

```mermaid
flowchart TD
    %% --- Definiciones de Estilo ---
    classDef mvp fill:#f0fff0,stroke:#2e6b2e,stroke-width:2px;
    classDef phase1 fill:#e6f7ff,stroke:#0056b3,stroke-width:2px;

    subgraph "Usuario"
        A("Usuario")
    end
    
    subgraph "Frontend"
        B("React UI")
    end
    
    subgraph "Backend (Tu API)"
        C["API de FastAPI (askQuestion)"]
        D["LangChain (Orquestador)"]
        E["ChromaDB (Base de Datos Vectorial)"]
        F["Ollama (LLM Local)"]
    end
    
    %% --- Asignación de Clases ---
    class A,B,C,D,F phase1
    class E mvp

    %% --- Flujo (Corregido) ---
    A --> B
    B --> C
    C -->|1. Pregunta| D
    D -->|2. ¿Contexto?| E
    E -->|3. Chunks de Notion| D
    D -->|"4. Prompt (Contexto + Pregunta)"| F
    F -->|5. Respuesta generada| D
    D -->|6. Respuesta final| C
    C --> B
    B --> A
```

* **Fase 2: Flujo de Notificación**

Esta es una mejora futura. Se "engancha" al flujo del MVP (el n8n Workflow en verde) para añadir la funcionalidad de enviar emails (en gris discontinuo).


```mermaid
flowchart TD
    %% --- Definiciones de Estilo ---
    classDef mvp fill:#f0fff0,stroke:#2e6b2e,stroke-width:2px;
    classDef phase2 fill:#f5f5f5,stroke:#999,stroke-width:2px,stroke-dasharray: 5 5;

    %% --- Nodos ---
    B("Servidor de Email")
    C("n8n Workflow")
    
    %% --- Asignación de Clases ---
    class C mvp
    class B phase2

    %% --- Flujo Fase 2 (Corregido) ---
    C -->|"Tras sincronizar (Fase 2)"<br>Envía email| B
    
    %% --- Estilo del Link (Fase 2) ---
    linkStyle 0 stroke:#999,stroke-width:2px,stroke-dasharray: 5 5;
```
