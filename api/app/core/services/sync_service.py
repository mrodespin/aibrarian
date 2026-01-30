# /api/app/core/services/sync_service.py

"""
Document synchronization service (MVP).
Orchestrates the ingestion pipeline: load -> chunk -> embed -> store.
"""

import logging
import time
from pathlib import Path
from typing import Optional

from app.core.ports.document_processor_port import DocumentProcessorPort
from app.core.ports.llm_port import LLMPort
from app.core.ports.vector_db_port import VectorDBPort
from app.core.domain.models import SyncResult, Chunk
from app.config.settings import settings


logger = logging.getLogger(__name__)


class SyncService:
    """Service for synchronizing documents into the vector database."""

    def __init__(
        self,
        document_processor: DocumentProcessorPort,
        llm: LLMPort,
        vector_db: VectorDBPort
    ):
        """
        Initialize sync service with required dependencies.

        Args:
            document_processor: Document processing adapter
            llm: LLM adapter for generating embeddings
            vector_db: Vector database adapter
        """
        self.document_processor = document_processor
        self.llm = llm
        self.vector_db = vector_db

    async def sync_document_from_file(
        self,
        file_path: str | Path,
        collection_name: Optional[str] = None
    ) -> SyncResult:
        """
        Sync a document from a file into the vector database.

        This is the main MVP pipeline:
        1. Load and process the document
        2. Split into chunks
        3. Generate embeddings for each chunk
        4. Store in vector database

        Args:
            file_path: Path to the document file
            collection_name: Optional collection name (defaults to config)

        Returns:
            SyncResult with processing details
        """
        start_time = time.time()
        collection = collection_name or settings.chromadb_collection_name

        try:
            logger.info(f"Starting sync for file: {file_path}")

            # Step 1 & 2: Load and chunk document
            document, chunks = await self.document_processor.process_document(
                source=file_path,
                chunk_size=settings.chunk_size,
                chunk_overlap=settings.chunk_overlap
            )

            if not chunks:
                return SyncResult(
                    document_id=document.id,
                    chunks_created=0,
                    success=False,
                    message="No chunks created from document",
                    processing_time=time.time() - start_time
                )

            logger.info(f"Created {len(chunks)} chunks from document {document.id}")

            # Step 3: Generate embeddings for all chunks
            chunk_texts = [chunk.content for chunk in chunks]
            embeddings = await self.llm.generate_embeddings_batch(chunk_texts)

            # Attach embeddings to chunks
            for chunk, embedding in zip(chunks, embeddings):
                chunk.embedding = embedding

            logger.info(f"Generated embeddings for {len(chunks)} chunks")

            # Step 4: Store chunks in vector database
            success = await self.vector_db.store_chunks(
                chunks=chunks,
                collection_name=collection
            )

            if not success:
                return SyncResult(
                    document_id=document.id,
                    chunks_created=len(chunks),
                    success=False,
                    message="Failed to store chunks in vector database",
                    processing_time=time.time() - start_time
                )

            processing_time = time.time() - start_time
            logger.info(
                f"Successfully synced document {document.id} "
                f"({len(chunks)} chunks) in {processing_time:.2f}s"
            )

            return SyncResult(
                document_id=document.id,
                chunks_created=len(chunks),
                success=True,
                message=f"Document synced successfully to collection '{collection}'",
                processing_time=processing_time
            )

        except Exception as e:
            error_msg = f"Failed to sync document: {str(e)}"
            logger.error(error_msg, exc_info=True)

            return SyncResult(
                document_id="unknown",
                chunks_created=0,
                success=False,
                message=error_msg,
                processing_time=time.time() - start_time
            )

    async def sync_directory(
        self,
        directory_path: str | Path,
        collection_name: Optional[str] = None
    ) -> list[SyncResult]:
        """
        Sync all supported documents from a directory.

        Args:
            directory_path: Path to directory containing documents
            collection_name: Optional collection name

        Returns:
            List of SyncResult for each document
        """
        directory = Path(directory_path)

        if not directory.exists() or not directory.is_dir():
            logger.error(f"Directory not found: {directory}")
            return []

        results = []
        pdf_files = list(directory.glob("*.pdf"))

        logger.info(f"Found {len(pdf_files)} PDF files in {directory}")

        for pdf_file in pdf_files:
            result = await self.sync_document_from_file(
                file_path=pdf_file,
                collection_name=collection_name
            )
            results.append(result)

        successful = sum(1 for r in results if r.success)
        logger.info(f"Synced {successful}/{len(results)} documents successfully")

        return results

    async def delete_document(
        self,
        document_id: str,
        collection_name: Optional[str] = None
    ) -> bool:
        """
        Delete a document from the vector database.

        Args:
            document_id: ID of document to delete
            collection_name: Optional collection name

        Returns:
            True if successful
        """
        collection = collection_name or settings.chromadb_collection_name

        try:
            success = await self.vector_db.delete_document(
                document_id=document_id,
                collection_name=collection
            )

            if success:
                logger.info(f"Deleted document {document_id} from collection '{collection}'")
            else:
                logger.warning(f"Failed to delete document {document_id}")

            return success

        except Exception as e:
            logger.error(f"Error deleting document {document_id}: {e}")
            return False
