# /api/app/main.py

"""
FastAPI application for Bibliotecario-IA.
Main entry point for the RAG API.
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.config.settings import settings
from app.core.domain.models import Query, QueryResult, SyncResult
from app.core.services.sync_service import SyncService
from app.core.services.rag_service import RAGService
from app.adapters.outbound.chromadb_adapter import ChromaDBAdapter
from app.adapters.outbound.ollama_adapter import OllamaAdapter
from app.adapters.outbound.pdf_processor_adapter import PDFProcessorAdapter
from app.adapters.outbound.notion_processor_adapter import NotionProcessorAdapter


# Configure logging
logging.basicConfig(
    level=logging.INFO if not settings.debug else logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# ===================================
# Dependency Injection Setup
# ===================================
# Initialize adapters (singletons)
chromadb_adapter = ChromaDBAdapter()
ollama_adapter = OllamaAdapter()
pdf_processor = PDFProcessorAdapter()
notion_processor = NotionProcessorAdapter()

# Initialize services
sync_service = SyncService(
    document_processor=pdf_processor,
    llm=ollama_adapter,
    vector_db=chromadb_adapter
)

# Notion sync service (uses Notion processor)
notion_sync_service = SyncService(
    document_processor=notion_processor,
    llm=ollama_adapter,
    vector_db=chromadb_adapter
)

rag_service = RAGService(
    llm=ollama_adapter,
    vector_db=chromadb_adapter
)


# ===================================
# Application Lifecycle
# ===================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")
    logger.info(f"Ollama URL: {settings.ollama_base_url}")
    logger.info(f"ChromaDB URL: {settings.chromadb_url}")

    # Check if Ollama is available
    is_available = await ollama_adapter.is_available()
    if not is_available:
        logger.warning("Ollama service is not available!")
    else:
        logger.info("Ollama service is ready")

    yield

    # Shutdown
    logger.info("Shutting down application")


# ===================================
# FastAPI Application
# ===================================
app = FastAPI(
    title=settings.app_name,
    description="API for the AI Librarian RAG project - Local knowledge base with privacy.",
    version=settings.app_version,
    lifespan=lifespan
)

# CORS middleware (for frontend integration)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ===================================
# Request/Response Models
# ===================================
class SyncFileRequest(BaseModel):
    """Request model for syncing a file."""
    file_path: str
    collection_name: str | None = None


class SyncNotionPageRequest(BaseModel):
    """Request model for syncing a Notion page."""
    page_id: str
    collection_name: str | None = None


class SyncNotionDatabaseRequest(BaseModel):
    """Request model for syncing a Notion database."""
    database_id: str | None = None
    max_pages: int | None = None
    collection_name: str | None = None


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str
    ollama_available: bool
    chromadb_available: bool


# ===================================
# API Endpoints
# ===================================

@app.get("/", response_model=HealthResponse)
async def root():
    """
    Root endpoint - Health check.
    """
    ollama_ok = await ollama_adapter.is_available()
    chromadb_ok = await chromadb_adapter.collection_exists(settings.chromadb_collection_name)

    return HealthResponse(
        status="running",
        version=settings.app_version,
        ollama_available=ollama_ok,
        chromadb_available=chromadb_ok
    )


@app.get("/health")
async def health_check():
    """
    Detailed health check endpoint.
    """
    return {
        "status": "healthy",
        "services": {
            "ollama": await ollama_adapter.is_available(),
            "chromadb": await chromadb_adapter.collection_exists(settings.chromadb_collection_name)
        },
        "config": {
            "ollama_model": settings.ollama_model,
            "embedding_model": settings.ollama_embedding_model,
            "collection": settings.chromadb_collection_name,
            "data_directory": settings.data_directory
        }
    }


@app.get("/stats")
async def get_stats():
    """
    Get database statistics and model information.
    """
    try:
        info = await rag_service.get_collection_info()
        return info
    except Exception as e:
        logger.error(f"Failed to get stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===================================
# MVP Endpoint: Document Synchronization
# ===================================

@app.post("/sync", response_model=SyncResult)
async def sync_document(request: SyncFileRequest):
    """
    MVP Endpoint: Sync a document file into the vector database.

    This endpoint:
    1. Loads the document from the specified file path
    2. Splits it into chunks
    3. Generates embeddings
    4. Stores in ChromaDB

    Args:
        request: File path and optional collection name

    Returns:
        SyncResult with processing details
    """
    try:
        file_path = Path(request.file_path)

        if not file_path.exists():
            raise HTTPException(status_code=404, detail=f"File not found: {request.file_path}")

        if not pdf_processor.supports_format(file_path):
            raise HTTPException(status_code=400, detail="Only PDF files are supported")

        result = await sync_service.sync_document_from_file(
            file_path=file_path,
            collection_name=request.collection_name
        )

        if not result.success:
            raise HTTPException(status_code=500, detail=result.message)

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Sync endpoint error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/sync/directory")
async def sync_directory(directory_path: str | None = None):
    """
    Sync all PDF documents from a directory.

    Args:
        directory_path: Path to directory (defaults to configured data directory)

    Returns:
        List of sync results
    """
    try:
        dir_path = directory_path or settings.data_directory

        results = await sync_service.sync_directory(dir_path)

        successful = sum(1 for r in results if r.success)
        failed = len(results) - successful

        return {
            "total": len(results),
            "successful": successful,
            "failed": failed,
            "results": results
        }

    except Exception as e:
        logger.error(f"Directory sync error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ===================================
# Notion Integration Endpoints
# ===================================

@app.post("/sync/notion", response_model=SyncResult)
async def sync_notion_page(request: SyncNotionPageRequest):
    """
    Sync a Notion page into the vector database.

    This endpoint:
    1. Connects to Notion API
    2. Loads the page content
    3. Splits it into chunks
    4. Generates embeddings
    5. Stores in ChromaDB

    Args:
        request: Notion page ID and optional collection name

    Returns:
        SyncResult with processing details
    """
    try:
        if not settings.notion_api_key:
            raise HTTPException(
                status_code=400,
                detail="Notion API key not configured. Set NOTION_API_KEY environment variable."
            )

        result = await notion_sync_service.sync_document_from_file(
            file_path=request.page_id,
            collection_name=request.collection_name
        )

        if not result.success:
            raise HTTPException(status_code=500, detail=result.message)

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Notion sync endpoint error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/sync/notion/database")
async def sync_notion_database(request: SyncNotionDatabaseRequest):
    """
    Sync all pages from a Notion database.

    Args:
        request: Database ID (defaults to config), max pages, and collection name

    Returns:
        Summary of sync results
    """
    try:
        if not settings.notion_api_key:
            raise HTTPException(
                status_code=400,
                detail="Notion API key not configured. Set NOTION_API_KEY environment variable."
            )

        database_id = request.database_id or settings.notion_database_id

        if not database_id:
            raise HTTPException(
                status_code=400,
                detail="Database ID is required. Provide in request or set NOTION_DATABASE_ID environment variable."
            )

        # Load all pages from database
        documents = await notion_processor.load_database_pages(
            database_id=database_id,
            max_pages=request.max_pages
        )

        if not documents:
            return {
                "total": 0,
                "successful": 0,
                "failed": 0,
                "message": "No pages found in database",
                "results": []
            }

        # Sync each document
        results = []
        for doc in documents:
            # Process and split the document
            chunks = await notion_processor.split_into_chunks(doc)

            # Generate embeddings
            chunk_texts = [chunk.content for chunk in chunks]
            embeddings = await ollama_adapter.generate_embeddings_batch(chunk_texts)

            # Attach embeddings
            for chunk, embedding in zip(chunks, embeddings):
                chunk.embedding = embedding

            # Store in database
            collection = request.collection_name or settings.chromadb_collection_name
            success = await chromadb_adapter.store_chunks(chunks, collection)

            results.append(
                SyncResult(
                    document_id=doc.id,
                    chunks_created=len(chunks),
                    success=success,
                    message=f"Synced '{doc.metadata.get('title', 'Untitled')}'"
                )
            )

        successful = sum(1 for r in results if r.success)
        failed = len(results) - successful

        return {
            "total": len(results),
            "successful": successful,
            "failed": failed,
            "results": results
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Notion database sync error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ===================================
# Phase 1 Endpoint: Question Answering (RAG)
# ===================================

@app.post("/ask", response_model=QueryResult)
async def ask_question(query: Query):
    """
    Phase 1 Endpoint: Ask a question to the AI librarian.

    This endpoint:
    1. Generates embedding for the question
    2. Retrieves relevant context from ChromaDB
    3. Builds a prompt with context
    4. Generates answer using Ollama
    5. Returns answer with source documents

    Args:
        query: User question and optional parameters

    Returns:
        QueryResult with answer and sources
    """
    try:
        result = await rag_service.ask_question(query)
        return result

    except Exception as e:
        logger.error(f"Ask endpoint error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ===================================
# Utility Endpoints
# ===================================

@app.delete("/documents/{document_id}")
async def delete_document(document_id: str):
    """
    Delete a document from the vector database.

    Args:
        document_id: ID of the document to delete

    Returns:
        Success status
    """
    try:
        success = await sync_service.delete_document(document_id)

        if not success:
            raise HTTPException(status_code=404, detail="Document not found or deletion failed")

        return {"status": "success", "message": f"Document {document_id} deleted"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete endpoint error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
