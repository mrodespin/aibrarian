# /api/app/core/ports/document_processor_port.py
"""
Puerto (Interfaz) para procesamiento de documentos - TFM Bibliotecario-IA

Este archivo define el CONTRATO para procesar documentos de diferentes fuentes.
Permite que el sistema soporte PDFs, Notion, Word, etc. con el mismo código.

¿Qué hace un Document Processor?
1. CARGAR documentos desde diferentes fuentes (PDF, Notion, etc.)
2. EXTRAER el texto del documento
3. DIVIDIR el texto en chunks pequeños para el sistema RAG

¿Por qué dividir en chunks?
- Los LLMs tienen límite de tokens (contexto)
- La búsqueda vectorial funciona mejor con textos cortos
- Permite encontrar secciones específicas relevantes

Equivalente en TypeScript:
    interface DocumentProcessorPort {
        loadDocument(source: string | Path): Promise<Document>;
        splitIntoChunks(doc: Document, size?: number, overlap?: number): Promise<Chunk[]>;
        processDocument(source: string | Path): Promise<[Document, Chunk[]]>;
        supportsFormat(filePath: string | Path): boolean;
    }

Implementaciones existentes:
- /adapters/outbound/pdf_processor_adapter.py (PDFs locales)
- /adapters/outbound/notion_processor_adapter.py (páginas de Notion)
"""

# ============================================================================
# IMPORTS
# ============================================================================
from abc import ABC, abstractmethod
from typing import List
# Path es como el módulo 'path' de Node.js, pero orientado a objetos
from pathlib import Path
from app.core.domain.models import Document, Chunk


# ============================================================================
# INTERFAZ DE PROCESAMIENTO DE DOCUMENTOS
# ============================================================================
class DocumentProcessorPort(ABC):
    """
    Interfaz abstracta para operaciones de procesamiento de documentos.

    Esta interfaz permite que el sistema sea AGNÓSTICO a la fuente de datos.
    El mismo código de negocio funciona con PDFs, Notion, Word, etc.

    Flujo de procesamiento:
        Archivo/URL → load_document() → Document
                                            ↓
                                    split_into_chunks()
                                            ↓
                                    [Chunk, Chunk, Chunk, ...]
                                            ↓
                            Se envían al LLM para generar embeddings
                                            ↓
                                Se almacenan en ChromaDB

    Implementaciones actuales:
    - PDFProcessorAdapter: Procesa archivos .pdf locales
    - NotionProcessorAdapter: Procesa páginas de Notion vía API

    Para añadir soporte a Word, solo habría que crear:
    - WordProcessorAdapter que implemente esta interfaz
    """

    @abstractmethod
    async def load_document(self, source: str | Path) -> Document:
        """
        Carga un documento desde un archivo o fuente externa.

        Este es el PRIMER PASO del pipeline de ingesta.
        Extrae todo el texto del documento y lo convierte en un objeto Document.

        Args:
            source: Ruta al archivo o identificador de la fuente
                   - Para PDFs: "/data/manual.pdf" o Path("/data/manual.pdf")
                   - Para Notion: "https://notion.so/page-id" o el page_id

        Returns:
            Document: Objeto con el contenido extraído y metadatos
                     - content: Todo el texto del documento
                     - metadata: {filename, page_count, url, etc.}
                     - source: "pdf" o "notion"

        Ejemplo:
            # Cargar un PDF
            doc = await processor.load_document("/data/manual.pdf")
            print(doc.content)  # "Capítulo 1: Introducción..."
            print(doc.metadata)  # {"filename": "manual.pdf", "page_count": 50}

        Nota sobre str | Path:
            Es un "Union Type" de Python (como en TypeScript: string | Path)
            Acepta tanto strings como objetos Path
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
        Divide el contenido de un documento en chunks pequeños.

        Este es el SEGUNDO PASO del pipeline de ingesta.

        ¿Por qué chunk_size y chunk_overlap?

        chunk_size = 1000 caracteres por chunk (aprox. 200 palabras)
        - Muy pequeño → pierde contexto
        - Muy grande → la búsqueda es menos precisa

        chunk_overlap = 200 caracteres compartidos entre chunks
        - Evita cortar ideas a la mitad
        - Mantiene continuidad entre fragmentos

        Ejemplo visual (overlap):
            Documento: "ABCDEFGHIJ"

            Sin overlap (size=5):
              Chunk 1: "ABCDE"
              Chunk 2: "FGHIJ"
              → Si la info importante está en "EF", se pierde

            Con overlap (size=5, overlap=2):
              Chunk 1: "ABCDE"
              Chunk 2: "DEFGH"
              Chunk 3: "GHIJ"
              → "DE" y "GH" están en dos chunks, manteniendo contexto

        Args:
            document: Documento a dividir (ya cargado con load_document)
            chunk_size: Tamaño objetivo de cada chunk en caracteres
                       Default: 1000 (~200 palabras)
            chunk_overlap: Caracteres de solapamiento entre chunks
                          Default: 200 (~40 palabras)

        Returns:
            List[Chunk]: Lista de chunks SIN embeddings todavía
                        Los embeddings se generan después con el LLM

        Ejemplo:
            chunks = await processor.split_into_chunks(document, size=500, overlap=100)
            # chunks[0].content = "Capítulo 1: Introducción. Este documento..."
            # chunks[1].content = "documento describe el sistema de..."
            # (nótese el overlap: "documento" aparece en ambos)
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
        Pipeline completo: carga documento y lo divide en chunks.

        Es un método de CONVENIENCIA que combina:
        1. load_document()
        2. split_into_chunks()

        Útil cuando quieres hacer todo el procesamiento en una sola llamada.

        Args:
            source: Ruta al documento (igual que load_document)
            chunk_size: Tamaño de chunks (igual que split_into_chunks)
            chunk_overlap: Overlap entre chunks

        Returns:
            tuple[Document, List[Chunk]]: Tupla con ambos resultados
                                         En TypeScript sería: [Document, Chunk[]]

        Ejemplo:
            # En lugar de:
            doc = await processor.load_document("/data/manual.pdf")
            chunks = await processor.split_into_chunks(doc)

            # Puedes hacer:
            doc, chunks = await processor.process_document("/data/manual.pdf")

        Nota sobre tuple:
            Python puede devolver múltiples valores empaquetados en una tupla.
            Se "desempaquetan" con: doc, chunks = await process_document(...)
            Es similar a destructuring en JavaScript: const [doc, chunks] = ...
        """
        pass

    @abstractmethod
    def supports_format(self, file_path: str | Path) -> bool:
        """
        Verifica si este procesador soporta el formato del archivo.

        Útil para:
        - Seleccionar el procesador correcto automáticamente
        - Validar archivos antes de procesarlos
        - Mostrar errores claros al usuario

        Args:
            file_path: Ruta al archivo a verificar

        Returns:
            bool: True si el formato es soportado

        Ejemplo:
            pdf_processor = PDFProcessorAdapter()
            pdf_processor.supports_format("manual.pdf")     # True
            pdf_processor.supports_format("manual.docx")    # False

            notion_processor = NotionProcessorAdapter()
            notion_processor.supports_format("notion://page-id")  # True

        Nota: Este método NO es async porque solo verifica la extensión,
              no necesita acceder al sistema de archivos realmente.
        """
        pass
