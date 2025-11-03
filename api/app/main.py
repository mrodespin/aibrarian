# /api/app/main.py

from fastapi import FastAPI

# Initialize the FastAPI app
app = FastAPI(
    title="tfm-bibliotecario-ia API",
    description="API for the AI Librarian RAG project.",
    version="0.1.0"
)

# --- Root Endpoint ---
@app.get("/")
def read_root():
    """
    Root endpoint to check if the API is running.
    """
    return {"status": "API is running!"}


# --- MVP Endpoint (Placeholder) ---
@app.post("/sync")
async def sync_documents():
    """
    Placeholder for the MVP endpoint.
    This will receive data from n8n and trigger the ingestion process.
    """
    # TODO: Implement logic from ROADMAP.md (MVP Task 1)
    return {"status": "sync_endpoint_placeholder"}


# --- Phase 1 Endpoint (Placeholder) ---
@app.post("/ask")
async def ask_question():
    """
    Placeholder for the Phase 1 endpoint.
    This will receive a question and return an answer from the RAG.
    """
    # TODO: Implement logic from ROADMAP.md (Phase 1 Task 1)
    return {"status": "ask_endpoint_placeholder"}