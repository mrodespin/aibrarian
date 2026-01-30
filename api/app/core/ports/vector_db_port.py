# /api/app/core/ports/vector_db_port.py

"""
Port (interface) for vector database operations.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from app.core.domain.models import Chunk, SourceDocument


class VectorDBPort(ABC):
    """Abstract interface for vector database operations."""

    @abstractmethod
    async def store_chunks(self, chunks: List[Chunk], collection_name: str = "documents") -> bool:
        """
        Store text chunks with their embeddings in the vector database.

        Args:
            chunks: List of Chunk objects with embeddings
            collection_name: Name of the collection/index to store chunks in

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    async def similarity_search(
        self,
        query_embedding: List[float],
        collection_name: str = "documents",
        top_k: int = 4,
        filter_metadata: Optional[Dict[str, Any]] = None
    ) -> List[SourceDocument]:
        """
        Perform similarity search using query embedding.

        Args:
            query_embedding: Vector embedding of the query
            collection_name: Collection to search in
            top_k: Number of results to return
            filter_metadata: Optional metadata filters

        Returns:
            List of SourceDocument objects with relevance scores
        """
        pass

    @abstractmethod
    async def delete_document(self, document_id: str, collection_name: str = "documents") -> bool:
        """
        Delete all chunks associated with a document.

        Args:
            document_id: ID of the document to delete
            collection_name: Collection to delete from

        Returns:
            True if successful
        """
        pass

    @abstractmethod
    async def collection_exists(self, collection_name: str) -> bool:
        """
        Check if a collection exists.

        Args:
            collection_name: Name of the collection

        Returns:
            True if exists, False otherwise
        """
        pass

    @abstractmethod
    async def get_collection_stats(self, collection_name: str = "documents") -> Dict[str, Any]:
        """
        Get statistics about a collection.

        Args:
            collection_name: Name of the collection

        Returns:
            Dictionary with stats (count, dimensions, etc.)
        """
        pass
