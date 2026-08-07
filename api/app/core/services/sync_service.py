# /api/app/core/services/sync_service.py
"""
Document Sync Service - Bibliotecario-IA

This service ORCHESTRATES the document ingestion pipeline. It's the
"conductor" that coordinates the three ports:
1. DocumentProcessorPort → Loads and splits documents
2. LLMPort → Generates embeddings (vectors)
3. VectorDBPort → Stores them in ChromaDB

Ingestion pipeline:
    PDF/Notion → load → chunks → embeddings → ChromaDB

Why a separate service?
- Separates business logic from the adapters
- Makes testing easier (you can mock the ports)
- Follows the Single Responsibility Principle (SRP)

TypeScript equivalent:
    class SyncService {
        constructor(
            private documentProcessor: DocumentProcessorPort,
            private llm: LLMPort,
            private vectorDb: VectorDBPort
        ) {}

        async syncDocumentFromFile(filePath: string): Promise<SyncResult> { ... }
        async syncDirectory(dirPath: string): Promise<SyncResult[]> { ... }
        async deleteDocument(docId: string): Promise<boolean> { ... }
    }

Endpoints that use this service:
- POST /sync → sync_document_from_file()
- POST /sync/directory → sync_directory()
- DELETE /documents/{id} → delete_document()
"""

# ============================================================================
# IMPORTS
# ============================================================================
import logging  # Python's logging system (like winston/pino in Node.js)
import time     # For measuring processing time
from pathlib import Path  # File path handling (like path in Node.js)
from typing import Optional

# We import the PORTS (interfaces), not the implementations
# This is key to hexagonal architecture
from app.core.ports.document_processor_port import DocumentProcessorPort
from app.core.ports.llm_port import LLMPort
from app.core.ports.vector_db_port import VectorDBPort
from app.core.domain.models import SyncResult, Chunk
from app.config.settings import settings  # Centralized configuration


# Logger configuration for this module
# __name__ = "app.core.services.sync_service" (useful for filtering logs)
logger = logging.getLogger(__name__)


# ============================================================================
# SYNC SERVICE
# ============================================================================
class SyncService:
    """
    Service for syncing documents into the vector database.

    This service implements the DEPENDENCY INJECTION pattern:
    - Receives interfaces (ports) in the constructor
    - Does NOT create the implementations directly
    - Lets you swap ChromaDB for Pinecone without modifying this code

    Responsibilities:
    1. Orchestrate the ingestion pipeline
    2. Handle errors and return structured results
    3. Log operations for debugging
    """

    def __init__(
        self,
        document_processor: DocumentProcessorPort,
        llm: LLMPort,
        vector_db: VectorDBPort
    ):
        """
        Initializes the service with its required dependencies.

        PATTERN: Dependency Injection

        Instead of creating the dependencies inside the class:
            self.vector_db = ChromaDBAdapter()  # ❌ Coupled

        We receive them as parameters:
            self.vector_db = vector_db  # ✅ Decoupled

        This enables:
        - Swapping implementations without modifying the service
        - Testing with mocks/stubs
        - Flexible per-environment configuration

        Args:
            document_processor: Adapter for processing documents (PDF, Notion)
                              Implements DocumentProcessorPort
            llm: Language model adapter (Ollama)
                Implements LLMPort
            vector_db: Vector database adapter (ChromaDB)
                      Implements VectorDBPort
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
        Syncs a document from a file into the vector database.

        THIS IS THE MVP'S MAIN METHOD.
        Runs the full ingestion pipeline:

        Pipeline:
            ① process_document() → Document + [Chunk, Chunk, ...]
            ② generate_embeddings_batch() → [embedding, embedding, ...]
            ③ store_chunks() → Stored in ChromaDB

        Args:
            file_path: Path to the file (PDF, etc.)
                      Example: "/data/manual.pdf" or Path("/data/manual.pdf")
            collection_name: ChromaDB collection name (optional)
                           If not given, uses the value from settings

        Returns:
            SyncResult: Structured result with:
                - document_id: ID of the processed document
                - chunks_created: Number of chunks generated
                - success: True/False
                - message: Informational or error message
                - processing_time: Total time in seconds

        Usage example:
            result = await sync_service.sync_document_from_file("/data/manual.pdf")
            if result.success:
                print(f"Created {result.chunks_created} chunks")
            else:
                print(f"Error: {result.message}")
        """
        # time.time() returns a Unix timestamp (seconds since 1970)
        # We use it to measure how long the process takes
        start_time = time.time()

        # "or" operator for default values
        # If collection_name is None, use the value from settings
        # JS equivalent: const collection = collectionName || settings.chromadbCollectionName
        collection = collection_name or settings.chromadb_collection_name

        try:
            # Informational logging for debugging
            # f-string: f"text {variable}" is like `text ${variable}` in JS
            logger.info(f"Starting sync for file: {file_path}")

            # ================================================================
            # STEPS 1 and 2: Load the document and split it into chunks
            # ================================================================
            # process_document() combines load_document() + split_into_chunks()
            # Returns a tuple that we "unpack" into two variables
            # In JS this would be: const [document, chunks] = await ...
            document, chunks = await self.document_processor.process_document(
                source=file_path,
                chunk_size=settings.chunk_size,      # ~1000 characters
                chunk_overlap=settings.chunk_overlap  # ~200 characters
            )

            # Validation: if there are no chunks, the document was empty
            if not chunks:
                return SyncResult(
                    document_id=document.id,
                    chunks_created=0,
                    success=False,
                    message="No chunks created from document",
                    processing_time=time.time() - start_time
                )

            logger.info(f"Created {len(chunks)} chunks from document {document.id}")

            # ================================================================
            # STEP 3: Generate embeddings for all chunks
            # ================================================================
            # List comprehension: extracts the content of each chunk
            # JS equivalent: chunks.map(chunk => chunk.content)
            chunk_texts = [chunk.content for chunk in chunks]

            # Generates embeddings in a batch (more efficient than one by one)
            embeddings = await self.llm.generate_embeddings_batch(chunk_texts)

            # zip() combines two lists element by element
            # zip([A, B, C], [1, 2, 3]) → [(A,1), (B,2), (C,3)]
            # JS equivalent: chunks.forEach((chunk, i) => chunk.embedding = embeddings[i])
            for chunk, embedding in zip(chunks, embeddings):
                chunk.embedding = embedding

            logger.info(f"Generated embeddings for {len(chunks)} chunks")

            # ================================================================
            # STEP 4: Store the chunks in the vector database
            # ================================================================
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

            # Compute total processing time
            processing_time = time.time() - start_time

            # :.2f formats the float with 2 decimal places
            # Example: 1.23456 → "1.23"
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
            # Catch any error and return it as a SyncResult
            # Instead of raising the exception, we "wrap" it in a result
            # This makes it easier to handle in the API
            error_msg = f"Failed to sync document: {str(e)}"

            # exc_info=True includes the full stack trace in the log
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
        Syncs all supported documents in a directory.

        Useful for ingesting multiple PDFs at once.
        Used mainly by the ingest_pdfs.py CLI script.

        Args:
            directory_path: Path to the directory containing documents
                          Example: "/data" or Path("/data")
            collection_name: Target collection (optional)

        Returns:
            list[SyncResult]: List of results, one per document
                             Lets you see which succeeded and which failed

        Example:
            results = await sync_service.sync_directory("/data")
            for result in results:
                if result.success:
                    print(f"✓ {result.document_id}")
                else:
                    print(f"✗ {result.message}")
        """
        # Path() converts a string into a Path object (more functionality)
        # Similar to path.resolve() in Node.js
        directory = Path(directory_path)

        # Validation: check that the directory exists
        # exists() and is_dir() are Path methods
        if not directory.exists() or not directory.is_dir():
            logger.error(f"Directory not found: {directory}")
            return []

        results = []

        # glob("*.pdf") finds all files matching the pattern
        # Similar to glob.sync("*.pdf") in Node.js
        # list() converts the generator into a list
        pdf_files = list(directory.glob("*.pdf"))

        logger.info(f"Found {len(pdf_files)} PDF files in {directory}")

        # Processes each PDF sequentially
        # Note: could be optimized with asyncio.gather() for parallel processing
        for pdf_file in pdf_files:
            result = await self.sync_document_from_file(
                file_path=pdf_file,
                collection_name=collection_name
            )
            results.append(result)

        # Count successes using a generator expression
        # sum(1 for r in results if r.success) counts how many have success=True
        # JS equivalent: results.filter(r => r.success).length
        successful = sum(1 for r in results if r.success)
        logger.info(f"Synced {successful}/{len(results)} documents successfully")

        return results

    async def delete_document(
        self,
        document_id: str,
        collection_name: Optional[str] = None
    ) -> bool:
        """
        Deletes a document from the vector database.

        Deletes ALL chunks associated with that document_id.
        Useful for:
        - Reprocessing an updated document
        - Removing stale documents
        - Data cleanup

        Args:
            document_id: ID of the document to delete
                        Example: "doc_abc123"
            collection_name: Collection the document is in (optional)

        Returns:
            bool: True if deleted successfully, False on error

        Example:
            # Delete a document
            success = await sync_service.delete_document("doc_abc123")

            # Re-ingest after updating the PDF
            if success:
                await sync_service.sync_document_from_file("/data/updated.pdf")
        """
        collection = collection_name or settings.chromadb_collection_name

        try:
            # Delegate deletion to the vector DB adapter
            success = await self.vector_db.delete_document(
                document_id=document_id,
                collection_name=collection
            )

            # Logging based on the result
            if success:
                logger.info(f"Deleted document {document_id} from collection '{collection}'")
            else:
                # warning instead of error because it's not necessarily a failure
                # (the document might simply not have existed)
                logger.warning(f"Failed to delete document {document_id}")

            return success

        except Exception as e:
            logger.error(f"Error deleting document {document_id}: {e}")
            return False
