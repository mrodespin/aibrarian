# /api/app/core/ports/document_processor_port.py

"""
Port (interface) for document processing operations.
"""

from abc import ABC, abstractmethod
from typing import List
from pathlib import Path
from app.core.domain.models import Document, Chunk


class DocumentProcessorPort(ABC):
    """Abstract interface for document processing operations."""

    @abstractmethod
    async def load_document(self, source: str | Path) -> Document:
        """
        Load a document from a file path or other source.

        Args:
            source: File path, URL, or other source identifier

        Returns:
            Document object with content and metadata
        """
        pass

    @abstractmethod
    async def split_into_chunks(
        self,
        document: Document,
        chunk_size: int = 1000,
        chunk_overlap: int = 200
    ) -> List[Chunk]:
        """
        Split document content into smaller chunks for processing.

        Args:
            document: Document to split
            chunk_size: Target size of each chunk in characters
            chunk_overlap: Number of characters to overlap between chunks

        Returns:
            List of Chunk objects without embeddings
        """
        pass

    @abstractmethod
    async def process_document(
        self,
        source: str | Path,
        chunk_size: int = 1000,
        chunk_overlap: int = 200
    ) -> tuple[Document, List[Chunk]]:
        """
        Complete pipeline: load document and split into chunks.

        Args:
            source: Document source (file path, etc.)
            chunk_size: Target chunk size
            chunk_overlap: Overlap between chunks

        Returns:
            Tuple of (Document, List of Chunks)
        """
        pass

    @abstractmethod
    def supports_format(self, file_path: str | Path) -> bool:
        """
        Check if this processor supports the given file format.

        Args:
            file_path: Path to the file

        Returns:
            True if format is supported
        """
        pass
