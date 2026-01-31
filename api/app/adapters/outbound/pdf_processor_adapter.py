# /api/app/adapters/outbound/pdf_processor_adapter.py
"""
Adaptador de procesamiento de PDFs - TFM Bibliotecario-IA

Implementación concreta de DocumentProcessorPort para archivos PDF locales.
Es el adaptador que convierte un archivo .pdf en chunks listos para vectorizar.

¿Qué hace este adaptador?
1. Lee un archivo PDF desde el disco local
2. Extrae todo el texto (página por página con PyPDFLoader)
3. Divide el texto en chunks inteligentes con overlap

Tecnologías usadas:
- PyPDFLoader (LangChain): extrae texto de PDFs página a página
- RecursiveCharacterTextSplitter (LangChain): divide texto respetando estructura

¿Qué es RecursiveCharacterTextSplitter?
Divide texto intentando respetar la estructura natural del documento.
Intenta cortar primero por párrafos, luego por líneas, luego por palabras.
Esto evita cortar palabras o ideas a la mitad.

Separadores por prioridad:
    1. "\n\n" → párrafos (mejor opción, corte más natural)
    2. "\n"   → líneas
    3. " "    → palabras
    4. ""     → caracteres (último recurso)

Equivalente en TypeScript:
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
import uuid  # Para generar IDs únicos (como crypto.randomUUID() en JS)

# LangChain: PyPDFLoader extrae texto de PDFs página a página
from langchain_community.document_loaders import PyPDFLoader
# RecursiveCharacterTextSplitter: divide texto respetando la estructura natural
from langchain_text_splitters import RecursiveCharacterTextSplitter

# Importamos el PUERTO (interfaz) que implementamos
from app.core.ports.document_processor_port import DocumentProcessorPort
from app.core.domain.models import Document, Chunk, DocumentSource
from app.config.settings import settings


logger = logging.getLogger(__name__)


# ============================================================================
# ADAPTADOR PDF
# ============================================================================
class PDFProcessorAdapter(DocumentProcessorPort):
    """
    Implementación concreta de DocumentProcessorPort para archivos PDF.

    Esta clase es el ÚNICO lugar del sistema que conoce cómo leer PDFs.
    El resto del código solo habla con la interfaz DocumentProcessorPort.

    Si cambiaras la librería de lectura de PDFs (ej: de PyPDF a pdfplumber),
    solo modificarías este archivo, sin tocar servicios ni otros adaptadores.
    """

    def __init__(self):
        """
        Inicializa el procesador de PDFs.

        _text_splitter no se crea aquí porque los parámetros chunk_size
        y chunk_overlap pueden variar por cada llamada.
        """
        self._text_splitter = None

    def _get_text_splitter(
        self,
        chunk_size: int = None,
        chunk_overlap: int = None
    ) -> RecursiveCharacterTextSplitter:
        """
        Crea un RecursiveCharacterTextSplitter con los parámetros dados.

        ¿Por qué "Recursive"?
        Intenta dividir el texto usando separadores en orden de prioridad:
            1. "\n\n" (párrafos) → corte más natural
            2. "\n"  (líneas)
            3. " "   (palabras)
            4. ""    (caracteres) → último recurso

        Si un párrafo cabe en chunk_size, lo mantiene íntegro.
        Solo lo subdivide si es más grande que chunk_size.

        length_function=len: usa len() para medir tamaño en caracteres.
        Equivalente JS: (text) => text.length

        Args:
            chunk_size: Tamaño objetivo por chunk (None = usa settings)
            chunk_overlap: Overlap entre chunks (None = usa settings)

        Returns:
            RecursiveCharacterTextSplitter configurado
        """
        actual_chunk_size = chunk_size or settings.chunk_size
        actual_overlap = chunk_overlap or settings.chunk_overlap

        return RecursiveCharacterTextSplitter(
            chunk_size=actual_chunk_size,
            chunk_overlap=actual_overlap,
            length_function=len,                     # Mide por caracteres
            separators=["\n\n", "\n", " ", ""]       # Prioridad de corte
        )

    async def load_document(self, source: str | Path) -> Document:
        """
        Carga un archivo PDF y extrae todo su texto.

        Proceso interno:
        1. Verifica que el archivo existe y es PDF
        2. PyPDFLoader lee el PDF página a página
        3. Une todo el texto con separadores de párrafo (\n\n)
        4. Crea un objeto Document con el contenido y metadatos

        Args:
            source: Ruta al archivo PDF
                   Ejemplo: "/data/manual.pdf" o Path("/data/manual.pdf")

        Returns:
            Document: Objeto con todo el texto extraído y metadatos
                     - id: identificador único (ej: "pdf_a3f2b1c9")
                     - content: todo el texto del PDF
                     - metadata: filename, page_count, file_size, etc.

        Ejemplo:
            doc = await pdf_processor.load_document("/data/manual.pdf")
            print(doc.content[:100])  # "Capítulo 1: Introducción..."
            print(doc.metadata)       # {"filename": "manual.pdf", "page_count": 50, ...}
        """
        try:
            file_path = Path(source)

            # Validaciones antes de procesar
            if not file_path.exists():
                raise FileNotFoundError(f"File not found: {file_path}")

            if not self.supports_format(file_path):
                raise ValueError(f"Unsupported file format: {file_path.suffix}")

            # PyPDFLoader: carga el PDF y extrae texto página a página
            # Cada página se convierte en un objeto con .page_content
            loader = PyPDFLoader(str(file_path))
            pages = loader.load()

            # Une todas las páginas en un solo texto
            # "\n\n" entre páginas para mantener separación visual
            # Equivalente JS: pages.map(p => p.pageContent).join("\n\n")
            full_content = "\n\n".join([page.page_content for page in pages])

            # Crea el objeto Document con metadatos del archivo
            document = Document(
                # uuid.uuid4().hex[:8] genera un ID corto y único
                # Ejemplo: "pdf_a3f2b1c9"
                id=f"pdf_{uuid.uuid4().hex[:8]}",
                source=DocumentSource.PDF,
                content=full_content,
                metadata={
                    "filename": file_path.name,                    # "manual.pdf"
                    "filepath": str(file_path.absolute()),         # Ruta absoluta
                    "page_count": len(pages),                      # Número de páginas
                    "file_size": file_path.stat().st_size          # Tamaño en bytes
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
        Divide el contenido del documento en chunks pequeños.

        Cada chunk hereda los metadatos del documento padre y añade
        su propia posición (chunk_index) y total (chunk_total).

        Los chunks salen SIN embedding. Los embeddings se generan
        después en el SyncService usando el LLM.

        IDs de chunks:
            Si el documento es "pdf_a3f2b1c9", los chunks serán:
            - "pdf_a3f2b1c9_chunk_0"
            - "pdf_a3f2b1c9_chunk_1"
            - "pdf_a3f2b1c9_chunk_2"
            Esto permite trazar de qué documento viene cada chunk.

        Args:
            document: Documento ya cargado (con load_document)
            chunk_size: Tamaño objetivo por chunk en caracteres
            chunk_overlap: Caracteres de overlap entre chunks

        Returns:
            List[Chunk]: Lista de chunks sin embeddings
        """
        try:
            text_splitter = self._get_text_splitter(chunk_size, chunk_overlap)

            # split_text divide el contenido en lista de strings
            text_chunks = text_splitter.split_text(document.content)

            # Convierte cada string en un objeto Chunk con metadatos
            chunks = []
            for i, chunk_text in enumerate(text_chunks):
                chunk = Chunk(
                    id=f"{document.id}_chunk_{i}",     # ID trazable al documento
                    document_id=document.id,            # Referencia al padre
                    content=chunk_text,                 # Texto del fragmento
                    embedding=None,                     # Se añade después con el LLM
                    metadata={
                        **document.metadata,            # Hereda metadatos del PDF
                        "chunk_index": i,               # Posición (0, 1, 2, ...)
                        "chunk_total": len(text_chunks) # Total de chunks
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
        Pipeline completo: carga el PDF y lo divide en chunks.

        Método de conveniencia que combina load_document() + split_into_chunks().
        Es el que lo llama el SyncService en un solo paso.

        Args:
            source: Ruta al archivo PDF
            chunk_size: Tamaño de chunks
            chunk_overlap: Overlap entre chunks

        Returns:
            tuple[Document, List[Chunk]]: Documento y sus chunks
        """
        try:
            # Paso 1: Cargar y extraer texto del PDF
            document = await self.load_document(source)

            # Paso 2: Dividir en chunks
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
        Verifica si el archivo es un PDF.

        path.suffix devuelve la extensión del archivo.
        Equivalente JS: path.extname(filePath)
        Ejemplo: Path("manual.pdf").suffix → ".pdf"

        Args:
            file_path: Ruta al archivo a verificar

        Returns:
            bool: True solo si la extensión es .pdf
        """
        path = Path(file_path)
        return path.suffix.lower() == ".pdf"
