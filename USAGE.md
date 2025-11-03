# 📚 API & Services Documentation (tfm-bibliotecario-ia)

This document details all the services, ports, and API endpoints for the AI Librarian project.

---

## 🌐 Project Services & Ports

When you run `docker-compose up -d`, several services are started. Here is a summary of what they are and where to find them:

| Service | Local URL (in your browser) | Internal URL (for other containers) | Purpose (Who interacts with it?) |
| :--- | :--- | :--- | :--- |
| **FastAPI API** | `http://localhost:8000` | `http://api:8000` | **(You / Frontend / n8n)**. This is the main API for the project. |
| **n8n UI** | `http://localhost:5678` | `http://n8n:5678` | **(You)**. You open this in your browser to build the automation workflow. |
| **ChromaDB API** | `http://localhost:8001` | `http://chromadb:8000` | **(FastAPI ONLY)**. Your API talks to this service to store/retrieve vectors. |
| **Ollama API** | `http://localhost:11434` | `http://host.docker.internal:11434` | **(FastAPI ONLY)**. Your API talks to this service to run the LLM. |

*Note on Ollama:* Ollama runs on your host machine, not in Docker. `host.docker.internal` is a special DNS name that allows a Docker container (like your API) to talk to the host machine.

---

## 🤖 FastAPI API Endpoints

This section details the endpoints for the main project API (running on `http://localhost:8000`).

### 1. Health Check

* **Endpoint:** `GET /`
* **Description:** A simple endpoint to verify that the API is running and responsive.
* **Request Body:** None.
* **Success Response (200 OK):**
    ```json
    {
      "status": "API is running!"
    }
    ```

---

### 2. MVP: Sync Documents

* **Endpoint:** `POST /sync`
* **Description:** This is the main **MVP** endpoint, designed to be called by the n8n workflow. It receives the content of a Notion page and triggers the ingestion pipeline (processing, chunking, embedding, and storing in ChromaDB).
* **Request Body (JSON):**
    ```json
    {
      "page_id": "string",
      "content": "string"
    }
    ```
* **Success Response (200 OK):**
    ```json
    {
      "status": "success",
      "processed_page_id": "string",
      "chunks_created": "integer"
    }
    ```
* **Error Response (400 Bad Request):**
    ```json
    {
      "detail": "Invalid payload."
    }
    ```

---

### 3. Phase 1: Ask Question (Chatbot)

* **Endpoint:** `POST /ask`
* **Description:** This is the **Phase 1** endpoint, designed to be called by the React frontend. It receives a user's question, runs the full RAG chain (query ChromaDB, build prompt, call Ollama), and returns a textual answer.
* **Request Body (JSON):**
    ```json
    {
      "question": "string",
      "session_id": "string (optional)"
    }
    ```
* **Success Response (200 OK):**
    ```json
    {
      "answer": "string (the model's generated answer)",
      "source_docs": [
        {
          "page_id": "string",
          "snippet": "string (the text chunk used as context)"
        }
      ]
    }
    ```