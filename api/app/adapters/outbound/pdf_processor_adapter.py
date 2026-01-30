# /api/app/adapters/outbound/pdf_processor_adapter.py

"""
PDF document processor adapter using LangChain.
"""

from typing import List
from pathlib import Path
import logging
import uuid

from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.ports.document_processor_port import DocumentProcessorPort
from app.core.domain.models import Document, Chunk, DocumentSource
from app.config.settings import settings


logger = logging.getLogger(__name__)


class PDFProcessorAdapter(DocumentProcessorPort):
    """PDF processor implementation using LangChain."""

    def __init__(self):
        """Initialize PDF processor."""
        self._text_splitter = None

    def _get_text_splitter(
        self,
        chunk_size: int = None,
        chunk_overlap: int = None
    ) -> RecursiveCharacterTextSplitter:
        """Get or create text splitter with specified parameters."""
        actual_chunk_size = chunk_size or settings.chunk_size
        actual_overlap = chunk_overlap or settings.chunk_overlap

        return RecursiveCharacterTextSplitter(
            chunk_size=actual_chunk_size,
            chunk_overlap=actual_overlap,
            length_function=len,
            separators=["\n\n", "\n", " ", ""]
        )

    async def load_document(self, source: str | Path) -> Document:
        """Load a PDF document."""
        try:
            file_path = Path(source)

            if not file_path.exists():
                raise FileNotFoundError(f"File not found: {file_path}")

            if not self.supports_format(file_path):
                raise ValueError(f"Unsupported file format: {file_path.suffix}")

            # Load PDF using LangChain's PyPDFLoader
            loader = PyPDFLoader(str(file_path))
            pages = loader.load()

            # Combine all pages into a single document
            full_content = "\n\n".join([page.page_content for page in pages])

            # Create Document object
            document = Document(
                id=f"pdf_{uuid.uuid4().hex[:8]}",
                source=DocumentSource.PDF,
                content=full_content,
                metadata={
                    "filename": file_path.name,
                    "filepath": str(file_path.absolute()),
                    "page_count": len(pages),
                    "file_size": file_path.stat().st_size
                }
            )

            logger.info(f"Loaded PDF: {file_path.name} ({len(pages)} pages)")
            return document

        except Exception as e:
            logger.error(f"Failed to load document from {source}: {e}")
            raise

    async def split_into_chunks(
        self,
        document: Document,
        chunk_size: int = 1000,
        chunk_overlap: int = 200
    ) -> List[Chunk]:
        """Split document into chunks."""
        try:
            text_splitter = self._get_text_splitter(chunk_size, chunk_overlap)

            # Split text
            text_chunks = text_splitter.split_text(document.content)

            # Create Chunk objects
            chunks = []
            for i, chunk_text in enumerate(text_chunks):
                chunk = Chunk(
                    id=f"{document.id}_chunk_{i}",
                    document_id=document.id,
                    content=chunk_text,
                    embedding=None,  # Embeddings will be added later
                    metadata={
                        **document.metadata,
                        "chunk_index": i,
                        "chunk_total": len(text_chunks)
                    }
                )
                chunks.append(chunk)

            logger.info(f"Split document {document.id} into {len(chunks)} chunks")
            return chunks

        except Exception as e:
            logger.error(f"Failed to split document: {e}")
            raise

    async def process_document(
        self,
        source: str | Path,
        chunk_size: int = 1000,
        chunk_overlap: int = 200
    ) -> tuple[Document, List[Chunk]]:
        """Complete pipeline: load and split document."""
        try:
            # Load document
            document = await self.load_document(source)

            # Split into chunks
            chunks = await self.split_into_chunks(document, chunk_size, chunk_overlap)

            logger.info(
                f"Processed document {document.id}: "
                f"{len(chunks)} chunks from {document.metadata.get('page_count', '?')} pages"
            )

            return document, chunks

        except Exception as e:
            logger.error(f"Failed to process document: {e}")
            raise

    def supports_format(self, file_path: str | Path) -> bool:
        """Check if file format is supported (PDF only)."""
        path = Path(file_path)
        return path.suffix.lower() == ".pdf"
