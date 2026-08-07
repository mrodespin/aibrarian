# /api/app/adapters/outbound/pdf_processor_adapter.py
"""
PDF Processing Adapter - Bibliotecario-IA

Concrete implementation of DocumentProcessorPort for local PDF files.
This is the adapter that turns a .pdf file into chunks ready to be
vectorized.

What does this adapter do?
1. Reads a PDF file from the local disk
2. Extracts all the text (page by page, with PyPDFLoader)
3. Splits the text into smart chunks with overlap

Technologies used:
- PyPDFLoader (LangChain): extracts text from PDFs page by page
- RecursiveCharacterTextSplitter (LangChain): splits text while respecting structure

What is RecursiveCharacterTextSplitter?
Splits text trying to respect the document's natural structure. It
tries to cut on paragraphs first, then lines, then words. This avoids
cutting words or ideas in half.

Separators by priority:
    1. "\n\n" → paragraphs (best option, most natural cut)
    2. "\n"   → lines
    3. " "    → words
    4. ""     → characters (last resort)

TypeScript equivalent:
    class PDFProcessorAdapter implements DocumentProcessorPort {
        async loadDocument(source: string | Path): Promise<Document> { ... }
        async splitIntoChunks(doc: Document, size?, overlap?): Promise<Chunk[]> { ... }
        async processDocument(source: string | Path): Promise<[Document, Chunk[]]> { ... }
        supportsFormat(filePath: string | Path): boolean { ... }
    }
"""

# ============================================================================
# IMPORTS
# ============================================================================
from typing import List
from pathlib import Path
import logging
import uuid  # For generating unique IDs (like crypto.randomUUID() in JS)

# LangChain: PyPDFLoader extracts text from PDFs page by page
from langchain_community.document_loaders import PyPDFLoader
# RecursiveCharacterTextSplitter: splits text while respecting the natural structure
from langchain_text_splitters import RecursiveCharacterTextSplitter

# Import the PORT (interface) we're implementing
from app.core.ports.document_processor_port import DocumentProcessorPort
from app.core.domain.models import Document, Chunk, DocumentSource
from app.config.settings import settings


logger = logging.getLogger(__name__)


# ============================================================================
# PDF ADAPTER
# ============================================================================
class PDFProcessorAdapter(DocumentProcessorPort):
    """
    Concrete implementation of DocumentProcessorPort for PDF files.

    This class is the ONLY place in the system that knows how to read
    PDFs. Everywhere else in the code only talks to the
    DocumentProcessorPort interface.

    If you swapped the PDF-reading library (e.g. from PyPDF to
    pdfplumber), you'd only need to modify this file, without touching
    services or other adapters.
    """

    def __init__(self):
        """
        Initializes the PDF processor.

        _text_splitter isn't created here because the chunk_size and
        chunk_overlap parameters can vary on each call.
        """
        self._text_splitter = None

    def _get_text_splitter(
        self,
        chunk_size: int = None,
        chunk_overlap: int = None
    ) -> RecursiveCharacterTextSplitter:
        """
        Creates a RecursiveCharacterTextSplitter with the given parameters.

        Why "Recursive"?
        It tries to split the text using separators in priority order:
            1. "\n\n" (paragraphs) → most natural cut
            2. "\n"  (lines)
            3. " "   (words)
            4. ""    (characters) → last resort

        If a paragraph fits within chunk_size, it's kept whole.
        It's only split further if it's bigger than chunk_size.

        length_function=len: uses len() to measure size in characters.
        JS equivalent: (text) => text.length

        Args:
            chunk_size: Target size per chunk (None = uses settings)
            chunk_overlap: Overlap between chunks (None = uses settings)

        Returns:
            A configured RecursiveCharacterTextSplitter
        """
        actual_chunk_size = chunk_size or settings.chunk_size
        actual_overlap = chunk_overlap or settings.chunk_overlap

        return RecursiveCharacterTextSplitter(
            chunk_size=actual_chunk_size,
            chunk_overlap=actual_overlap,
            length_function=len,                     # Measures by characters
            separators=["\n\n", "\n", " ", ""]       # Split priority
        )

    async def load_document(self, source: str | Path) -> Document:
        """
        Loads a PDF file and extracts all its text.

        Internal process:
        1. Checks the file exists and is a PDF
        2. PyPDFLoader reads the PDF page by page
        3. Joins all the text with paragraph separators (\n\n)
        4. Creates a Document object with the content and metadata

        Args:
            source: Path to the PDF file
                   Example: "/data/manual.pdf" or Path("/data/manual.pdf")

        Returns:
            Document: Object with all the extracted text and metadata
                     - id: unique identifier (e.g. "pdf_a3f2b1c9")
                     - content: the PDF's full text
                     - metadata: filename, page_count, file_size, etc.

        Example:
            doc = await pdf_processor.load_document("/data/manual.pdf")
            print(doc.content[:100])  # "Chapter 1: Introduction..."
            print(doc.metadata)       # {"filename": "manual.pdf", "page_count": 50, ...}
        """
        try:
            file_path = Path(source)

            # Validations before processing
            if not file_path.exists():
                raise FileNotFoundError(f"File not found: {file_path}")

            if not self.supports_format(file_path):
                raise ValueError(f"Unsupported file format: {file_path.suffix}")

            # PyPDFLoader: loads the PDF and extracts text page by page
            # Each page becomes an object with .page_content
            loader = PyPDFLoader(str(file_path))
            pages = loader.load()

            # Joins all pages into a single text
            # "\n\n" between pages to keep visual separation
            # JS equivalent: pages.map(p => p.pageContent).join("\n\n")
            full_content = "\n\n".join([page.page_content for page in pages])

            # Creates the Document object with the file's metadata
            document = Document(
                # uuid.uuid4().hex[:8] generates a short, unique ID
                # Example: "pdf_a3f2b1c9"
                id=f"pdf_{uuid.uuid4().hex[:8]}",
                source=DocumentSource.PDF,
                content=full_content,
                metadata={
                    "filename": file_path.name,                    # "manual.pdf"
                    "filepath": str(file_path.absolute()),         # Absolute path
                    "page_count": len(pages),                      # Number of pages
                    "file_size": file_path.stat().st_size          # Size in bytes
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
        """
        Splits the document's content into small chunks.

        Each chunk inherits the parent document's metadata and adds its
        own position (chunk_index) and total (chunk_total).

        Chunks come out WITHOUT an embedding. Embeddings are generated
        afterward in SyncService using the LLM.

        Chunk IDs:
            If the document is "pdf_a3f2b1c9", its chunks will be:
            - "pdf_a3f2b1c9_chunk_0"
            - "pdf_a3f2b1c9_chunk_1"
            - "pdf_a3f2b1c9_chunk_2"
            This lets you trace which document each chunk came from.

        Args:
            document: An already-loaded document (via load_document)
            chunk_size: Target size per chunk in characters
            chunk_overlap: Overlap characters between chunks

        Returns:
            List[Chunk]: List of chunks with no embeddings
        """
        try:
            text_splitter = self._get_text_splitter(chunk_size, chunk_overlap)

            # split_text splits the content into a list of strings
            text_chunks = text_splitter.split_text(document.content)

            # Converts each string into a Chunk object with metadata
            chunks = []
            for i, chunk_text in enumerate(text_chunks):
                chunk = Chunk(
                    id=f"{document.id}_chunk_{i}",     # ID traceable back to the document
                    document_id=document.id,            # Reference to the parent
                    content=chunk_text,                 # The fragment's text
                    embedding=None,                     # Added later with the LLM
                    metadata={
                        **document.metadata,            # Inherits the PDF's metadata
                        "chunk_index": i,               # Position (0, 1, 2, ...)
                        "chunk_total": len(text_chunks) # Total number of chunks
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
        """
        Full pipeline: loads the PDF and splits it into chunks.

        A convenience method combining load_document() + split_into_chunks().
        This is the one SyncService calls, in a single step.

        Args:
            source: Path to the PDF file
            chunk_size: Chunk size
            chunk_overlap: Overlap between chunks

        Returns:
            tuple[Document, List[Chunk]]: The document and its chunks
        """
        try:
            # Step 1: Load and extract the PDF's text
            document = await self.load_document(source)

            # Step 2: Split into chunks
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
        """
        Checks whether the file is a PDF.

        path.suffix returns the file's extension.
        JS equivalent: path.extname(filePath)
        Example: Path("manual.pdf").suffix → ".pdf"

        Args:
            file_path: Path to the file to check

        Returns:
            bool: True only if the extension is .pdf
        """
        path = Path(file_path)
        return path.suffix.lower() == ".pdf"
