# /api/app/core/domain/models.py

"""
Domain models for the Bibliotecario-IA project.
These models represent the core business entities.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field
from enum import Enum


class DocumentSource(str, Enum):
    """Source type of the document."""
    PDF = "pdf"
    NOTION = "notion"
    TEXT = "text"


class Document(BaseModel):
    """Represents a source document."""
    id: str = Field(..., description="Unique identifier for the document")
    source: DocumentSource = Field(..., description="Source type of the document")
    content: str = Field(..., description="Full text content of the document")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    created_at: datetime = Field(default_factory=datetime.now, description="Creation timestamp")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "doc_123",
                "source": "pdf",
                "content": "This is the content of the document...",
                "metadata": {"filename": "example.pdf", "page_count": 10}
            }
        }


class Chunk(BaseModel):
    """Represents a processed text chunk from a document."""
    id: str = Field(..., description="Unique identifier for the chunk")
    document_id: str = Field(..., description="Reference to the source document")
    content: str = Field(..., description="Text content of the chunk")
    embedding: Optional[List[float]] = Field(None, description="Vector embedding of the chunk")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Chunk metadata (page, position, etc.)")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "chunk_456",
                "document_id": "doc_123",
                "content": "This is a text chunk...",
                "metadata": {"page": 1, "position": 0}
            }
        }


class Query(BaseModel):
    """Represents a user query for the RAG system."""
    question: str = Field(..., min_length=1, description="The user's question")
    session_id: Optional[str] = Field(None, description="Optional session identifier for conversation tracking")
    max_results: int = Field(default=4, ge=1, le=10, description="Maximum number of context chunks to retrieve")

    class Config:
        json_schema_extra = {
            "example": {
                "question": "What is the main topic of the document?",
                "session_id": "session_789",
                "max_results": 4
            }
        }


class SourceDocument(BaseModel):
    """Represents a source document snippet used as context."""
    document_id: str = Field(..., description="Document identifier")
    chunk_content: str = Field(..., description="The relevant text chunk")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Source metadata")
    relevance_score: Optional[float] = Field(None, description="Similarity/relevance score")


class QueryResult(BaseModel):
    """Represents the result of a RAG query."""
    question: str = Field(..., description="The original question")
    answer: str = Field(..., description="Generated answer from the LLM")
    source_documents: List[SourceDocument] = Field(default_factory=list, description="Context sources used")
    session_id: Optional[str] = Field(None, description="Session identifier")
    processing_time: Optional[float] = Field(None, description="Processing time in seconds")

    class Config:
        json_schema_extra = {
            "example": {
                "question": "What is RAG?",
                "answer": "RAG stands for Retrieval-Augmented Generation...",
                "source_documents": [
                    {
                        "document_id": "doc_123",
                        "chunk_content": "RAG is a technique...",
                        "metadata": {"page": 1},
                        "relevance_score": 0.95
                    }
                ]
            }
        }


class SyncResult(BaseModel):
    """Result of a document synchronization/ingestion operation."""
    document_id: str = Field(..., description="Processed document ID")
    chunks_created: int = Field(..., description="Number of chunks created")
    success: bool = Field(..., description="Whether the operation succeeded")
    message: Optional[str] = Field(None, description="Additional information or error message")
    processing_time: Optional[float] = Field(None, description="Processing time in seconds")
