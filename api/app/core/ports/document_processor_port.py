# /api/app/core/ports/document_processor_port.py
"""
Port (Interface) for document processing - Bibliotecario-IA

This file defines the CONTRACT for processing documents from different
sources. It lets the system support PDFs, Notion, Word, etc. with the
same code.

What does a Document Processor do?
1. LOADS documents from different sources (PDF, Notion, etc.)
2. EXTRACTS the document's text
3. SPLITS the text into small chunks for the RAG system

Why split into chunks?
- LLMs have a token (context) limit
- Vector search works better with short texts
- Lets you find specific relevant sections

TypeScript equivalent:
    interface DocumentProcessorPort {
        loadDocument(source: string | Path): Promise<Document>;
        splitIntoChunks(doc: Document, size?: number, overlap?: number): Promise<Chunk[]>;
        processDocument(source: string | Path): Promise<[Document, Chunk[]]>;
        supportsFormat(filePath: string | Path): boolean;
    }

Existing implementations:
- /adapters/outbound/pdf_processor_adapter.py (local PDFs)
- /adapters/outbound/notion_processor_adapter.py (Notion pages)
"""

# ============================================================================
# IMPORTS
# ============================================================================
from abc import ABC, abstractmethod
from typing import List
# Path is like Node.js's 'path' module, but object-oriented
from pathlib import Path
from app.core.domain.models import Document, Chunk


# ============================================================================
# DOCUMENT PROCESSING INTERFACE
# ============================================================================
class DocumentProcessorPort(ABC):
    """
    Abstract interface for document processing operations.

    This interface lets the system be AGNOSTIC to the data source.
    The same business logic works with PDFs, Notion, Word, etc.

    Processing flow:
        File/URL → load_document() → Document
                                            ↓
                                    split_into_chunks()
                                            ↓
                                    [Chunk, Chunk, Chunk, ...]
                                            ↓
                            Sent to the LLM to generate embeddings
                                            ↓
                                Stored in ChromaDB

    Current implementations:
    - PDFProcessorAdapter: Processes local .pdf files
    - NotionProcessorAdapter: Processes Notion pages via the API

    To add Word support, you'd just need to create:
    - A WordProcessorAdapter implementing this interface
    """

    @abstractmethod
    async def load_document(self, source: str | Path) -> Document:
        """
        Loads a document from a file or external source.

        This is the FIRST STEP in the ingestion pipeline.
        Extracts all of the document's text and turns it into a
        Document object.

        Args:
            source: Path to the file or the source's identifier
                   - For PDFs: "/data/manual.pdf" or Path("/data/manual.pdf")
                   - For Notion: "https://notion.so/page-id" or the page_id

        Returns:
            Document: Object with the extracted content and metadata
                     - content: All of the document's text
                     - metadata: {filename, page_count, url, etc.}
                     - source: "pdf" or "notion"

        Example:
            # Load a PDF
            doc = await processor.load_document("/data/manual.pdf")
            print(doc.content)  # "Chapter 1: Introduction..."
            print(doc.metadata)  # {"filename": "manual.pdf", "page_count": 50}

        Note on str | Path:
            This is a Python "Union Type" (like TypeScript's string | Path)
            Accepts both strings and Path objects
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
        Splits a document's content into small chunks.

        This is the SECOND STEP in the ingestion pipeline.

        Why chunk_size and chunk_overlap?

        chunk_size = 1000 characters per chunk (~200 words)
        - Too small → loses context
        - Too large → search becomes less precise

        chunk_overlap = 200 characters shared between chunks
        - Avoids cutting ideas in half
        - Keeps continuity between fragments

        Visual example (overlap):
            Document: "ABCDEFGHIJ"

            Without overlap (size=5):
              Chunk 1: "ABCDE"
              Chunk 2: "FGHIJ"
              → If the important info is in "EF", it's lost

            With overlap (size=5, overlap=2):
              Chunk 1: "ABCDE"
              Chunk 2: "DEFGH"
              Chunk 3: "GHIJ"
              → "DE" and "GH" appear in two chunks, preserving context

        Args:
            document: Document to split (already loaded with load_document)
            chunk_size: Target size of each chunk in characters
                       Default: 1000 (~200 words)
            chunk_overlap: Overlap characters between chunks
                          Default: 200 (~40 words)

        Returns:
            List[Chunk]: List of chunks WITHOUT embeddings yet
                        Embeddings are generated afterward with the LLM

        Example:
            chunks = await processor.split_into_chunks(document, size=500, overlap=100)
            # chunks[0].content = "Chapter 1: Introduction. This document..."
            # chunks[1].content = "document describes the system for..."
            # (note the overlap: "document" appears in both)
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
        Full pipeline: loads a document and splits it into chunks.

        A CONVENIENCE method that combines:
        1. load_document()
        2. split_into_chunks()

        Useful when you want to do all the processing in a single call.

        Args:
            source: Path to the document (same as load_document)
            chunk_size: Chunk size (same as split_into_chunks)
            chunk_overlap: Overlap between chunks

        Returns:
            tuple[Document, List[Chunk]]: Tuple with both results
                                         In TypeScript this would be: [Document, Chunk[]]

        Example:
            # Instead of:
            doc = await processor.load_document("/data/manual.pdf")
            chunks = await processor.split_into_chunks(doc)

            # You can do:
            doc, chunks = await processor.process_document("/data/manual.pdf")

        Note on tuple:
            Python can return multiple values packed into a tuple.
            They're "unpacked" with: doc, chunks = await process_document(...)
            Similar to destructuring in JavaScript: const [doc, chunks] = ...
        """
        pass

    @abstractmethod
    def supports_format(self, file_path: str | Path) -> bool:
        """
        Checks whether this processor supports the file's format.

        Useful for:
        - Automatically picking the right processor
        - Validating files before processing them
        - Showing clear errors to the user

        Args:
            file_path: Path to the file to check

        Returns:
            bool: True if the format is supported

        Example:
            pdf_processor = PDFProcessorAdapter()
            pdf_processor.supports_format("manual.pdf")     # True
            pdf_processor.supports_format("manual.docx")    # False

            notion_processor = NotionProcessorAdapter()
            notion_processor.supports_format("notion://page-id")  # True

        Note: This method is NOT async because it only checks the
              extension, it doesn't need to actually access the filesystem.
        """
        pass
