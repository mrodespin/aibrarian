# 🗂️ Repository Structure

This project is organized as a **monorepo**. All services (backend, frontend, orchestration) are contained within this single repository. This simplifies development, deployment, and version control.

## 🌳 File Tree Overview

```text
/tfm-bibliotecario-ia
|
|--- /api/                 <-- Python (FastAPI) Backend
|    |--- /app/            <-- Core application code (main.py, endpoints, etc.)
|    |--- Dockerfile       <-- Build recipe for the API container
|    |--- requirements.txt <-- Python dependencies
|
|--- /frontend/            <-- React (Vite) Frontend
|    |--- /src/            <-- Core application code (App.jsx, etc.)
|    |--- Dockerfile       <-- (Optional) Build recipe for frontend container
|    |--- package.json     <-- JavaScript dependencies
|
|--- /n8n/                 <-- n8n configuration
|    |--- workflow.json    <-- Exported workflow for easy import
|
|--- .gitignore            <-- Files and folders to ignore (secrets, node_modules)
|--- docker-compose.yml    <-- Main orchestration file (starts all services)
|--- LICENSE               <-- MIT License
|--- README.md             <-- Main project documentation (what, why, how)
|--- ROADMAP.md            <-- Project task list and development phases
|--- STRUCTURE.md          <-- (This file)
```

## 📂 Component Descriptions

### /api

* **Language:** Python
* **Framework:** FastAPI, LangChain
* **Role:** This is the project's "brain". It's a server that exposes HTTP endpoints.
* **Key Endpoints:**
    * `POST /sync`: (MVP) Receives data from n8n to process and save into the vector database.
    * `POST /ask`: (Phase 1) Receives a user's question, runs the RAG chain, and returns an answer.
* **Connects to:** `ChromaDB` (to store/retrieve vectors) and `Ollama` (to generate text).

### /frontend

* **Language:** JavaScript (using React)
* **Framework:** Vite (or Create React App)
* **Role:** This is the user-facing application (the UI).
* **Functionality:** Provides a chat interface that sends user questions to the `/api/ask` endpoint and displays the response.

### /n8n

* **Tool:** n8n (via Docker)
* **Role:** This is the automation or "ingestion" service.
* **Functionality:** Contains the `workflow.json` file. This workflow runs on a trigger (e.g., "when a Notion page is updated"), fetches the new data, and sends it to the `/api/sync` endpoint for processing.

### Root Files

* **`docker-compose.yml`**: The master file. Defines and starts all services (`api`, `n8n`, `chromadb`) and connects them in a shared Docker network.
* **`README.md`**: General project overview, architecture diagrams, and setup instructions.
* **`ROADMAP.md`**: The detailed task list, broken down by MVP, Phase 1, and Phase 2.
* **`STRUCTURE.md`**: This file, explaining the layout of the monorepo.
* **`.gitignore`**: Specifies which files (like `.env`, `node_modules`, `__pycache__`) to exclude from Git.