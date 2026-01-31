# /api/app/core/services/sync_service.py
"""
Servicio de Sincronización de Documentos - TFM Bibliotecario-IA

Este servicio ORQUESTA el pipeline de ingesta de documentos.
Es el "director de orquesta" que coordina los tres puertos:
1. DocumentProcessorPort → Carga y divide documentos
2. LLMPort → Genera embeddings (vectores)
3. VectorDBPort → Almacena en ChromaDB

Pipeline de ingesta:
    PDF/Notion → load → chunks → embeddings → ChromaDB

¿Por qué un servicio separado?
- Separa la lógica de negocio de los adaptadores
- Facilita testing (puedes mockear los puertos)
- Cumple con el principio de responsabilidad única (SRP)

Equivalente en TypeScript:
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

Endpoints que usan este servicio:
- POST /sync → sync_document_from_file()
- POST /sync/directory → sync_directory()
- DELETE /documents/{id} → delete_document()
"""

# ============================================================================
# IMPORTS
# ============================================================================
import logging  # Sistema de logs de Python (como winston/pino en Node.js)
import time     # Para medir tiempos de procesamiento
from pathlib import Path  # Manejo de rutas de archivos (como path en Node.js)
from typing import Optional

# Importamos los PUERTOS (interfaces), no las implementaciones
# Esto es clave para la arquitectura hexagonal
from app.core.ports.document_processor_port import DocumentProcessorPort
from app.core.ports.llm_port import LLMPort
from app.core.ports.vector_db_port import VectorDBPort
from app.core.domain.models import SyncResult, Chunk
from app.config.settings import settings  # Configuración centralizada


# Configuración del logger para este módulo
# __name__ = "app.core.services.sync_service" (útil para filtrar logs)
logger = logging.getLogger(__name__)


# ============================================================================
# SERVICIO DE SINCRONIZACIÓN
# ============================================================================
class SyncService:
    """
    Servicio para sincronizar documentos en la base de datos vectorial.

    Este servicio implementa el patrón de INYECCIÓN DE DEPENDENCIAS:
    - Recibe interfaces (puertos) en el constructor
    - NO crea las implementaciones directamente
    - Permite cambiar ChromaDB por Pinecone sin modificar este código

    Responsabilidades:
    1. Orquestar el pipeline de ingesta
    2. Manejar errores y devolver resultados estructurados
    3. Logging de operaciones para debugging
    """

    def __init__(
        self,
        document_processor: DocumentProcessorPort,
        llm: LLMPort,
        vector_db: VectorDBPort
    ):
        """
        Inicializa el servicio con las dependencias requeridas.

        PATRÓN: Inyección de Dependencias (Dependency Injection)

        En lugar de crear las dependencias dentro de la clase:
            self.vector_db = ChromaDBAdapter()  # ❌ Acoplado

        Las recibimos como parámetros:
            self.vector_db = vector_db  # ✅ Desacoplado

        Esto permite:
        - Cambiar implementaciones sin modificar el servicio
        - Testing con mocks/stubs
        - Configuración flexible por entorno

        Args:
            document_processor: Adaptador para procesar documentos (PDF, Notion)
                              Implementa DocumentProcessorPort
            llm: Adaptador del modelo de lenguaje (Ollama)
                Implementa LLMPort
            vector_db: Adaptador de base de datos vectorial (ChromaDB)
                      Implementa VectorDBPort
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
        Sincroniza un documento desde un archivo a la base de datos vectorial.

        ESTE ES EL MÉTODO PRINCIPAL DEL MVP.
        Ejecuta el pipeline completo de ingesta:

        Pipeline:
            ① process_document() → Document + [Chunk, Chunk, ...]
            ② generate_embeddings_batch() → [embedding, embedding, ...]
            ③ store_chunks() → Almacenado en ChromaDB

        Args:
            file_path: Ruta al archivo (PDF, etc.)
                      Ejemplo: "/data/manual.pdf" o Path("/data/manual.pdf")
            collection_name: Nombre de la colección en ChromaDB (opcional)
                           Si no se especifica, usa el valor de settings

        Returns:
            SyncResult: Resultado estructurado con:
                - document_id: ID del documento procesado
                - chunks_created: Número de chunks generados
                - success: True/False
                - message: Mensaje informativo o de error
                - processing_time: Tiempo total en segundos

        Ejemplo de uso:
            result = await sync_service.sync_document_from_file("/data/manual.pdf")
            if result.success:
                print(f"Creados {result.chunks_created} chunks")
            else:
                print(f"Error: {result.message}")
        """
        # time.time() devuelve timestamp Unix (segundos desde 1970)
        # Lo usamos para medir cuánto tarda el proceso
        start_time = time.time()

        # Operador "or" para valores por defecto
        # Si collection_name es None, usa el valor de settings
        # Equivalente JS: const collection = collectionName || settings.chromadbCollectionName
        collection = collection_name or settings.chromadb_collection_name

        try:
            # Logging informativo para debugging
            # f-string: f"texto {variable}" es como `texto ${variable}` en JS
            logger.info(f"Starting sync for file: {file_path}")

            # ================================================================
            # PASO 1 y 2: Cargar documento y dividir en chunks
            # ================================================================
            # process_document() combina load_document() + split_into_chunks()
            # Devuelve una tupla que "desempaquetamos" en dos variables
            # En JS sería: const [document, chunks] = await ...
            document, chunks = await self.document_processor.process_document(
                source=file_path,
                chunk_size=settings.chunk_size,      # ~1000 caracteres
                chunk_overlap=settings.chunk_overlap  # ~200 caracteres
            )

            # Validación: si no hay chunks, el documento estaba vacío
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
            # PASO 3: Generar embeddings para todos los chunks
            # ================================================================
            # List comprehension: extrae el contenido de cada chunk
            # Equivalente JS: chunks.map(chunk => chunk.content)
            chunk_texts = [chunk.content for chunk in chunks]

            # Genera embeddings en batch (más eficiente que uno por uno)
            embeddings = await self.llm.generate_embeddings_batch(chunk_texts)

            # zip() combina dos listas elemento a elemento
            # zip([A, B, C], [1, 2, 3]) → [(A,1), (B,2), (C,3)]
            # Equivalente JS: chunks.forEach((chunk, i) => chunk.embedding = embeddings[i])
            for chunk, embedding in zip(chunks, embeddings):
                chunk.embedding = embedding

            logger.info(f"Generated embeddings for {len(chunks)} chunks")

            # ================================================================
            # PASO 4: Almacenar chunks en la base de datos vectorial
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

            # Calcular tiempo total de procesamiento
            processing_time = time.time() - start_time

            # :.2f formatea el float con 2 decimales
            # Ejemplo: 1.23456 → "1.23"
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
            # Capturamos cualquier error y lo devolvemos como SyncResult
            # En lugar de lanzar la excepción, la "envolvemos" en un resultado
            # Esto facilita el manejo en la API
            error_msg = f"Failed to sync document: {str(e)}"

            # exc_info=True incluye el stack trace completo en el log
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
        Sincroniza todos los documentos soportados de un directorio.

        Útil para ingestar múltiples PDFs de una vez.
        Usado principalmente por el script CLI ingest_pdfs.py.

        Args:
            directory_path: Ruta al directorio con documentos
                          Ejemplo: "/data" o Path("/data")
            collection_name: Colección destino (opcional)

        Returns:
            list[SyncResult]: Lista de resultados, uno por cada documento
                             Permite ver cuáles tuvieron éxito y cuáles fallaron

        Ejemplo:
            results = await sync_service.sync_directory("/data")
            for result in results:
                if result.success:
                    print(f"✓ {result.document_id}")
                else:
                    print(f"✗ {result.message}")
        """
        # Path() convierte string a objeto Path (más funcionalidades)
        # Similar a path.resolve() en Node.js
        directory = Path(directory_path)

        # Validación: verificar que el directorio existe
        # exists() y is_dir() son métodos de Path
        if not directory.exists() or not directory.is_dir():
            logger.error(f"Directory not found: {directory}")
            return []

        results = []

        # glob("*.pdf") busca todos los archivos que coincidan con el patrón
        # Similar a glob.sync("*.pdf") en Node.js
        # list() convierte el generador a lista
        pdf_files = list(directory.glob("*.pdf"))

        logger.info(f"Found {len(pdf_files)} PDF files in {directory}")

        # Procesa cada PDF secuencialmente
        # Nota: podría optimizarse con asyncio.gather() para procesamiento paralelo
        for pdf_file in pdf_files:
            result = await self.sync_document_from_file(
                file_path=pdf_file,
                collection_name=collection_name
            )
            results.append(result)

        # Contar éxitos usando generator expression
        # sum(1 for r in results if r.success) cuenta cuántos tienen success=True
        # Equivalente JS: results.filter(r => r.success).length
        successful = sum(1 for r in results if r.success)
        logger.info(f"Synced {successful}/{len(results)} documents successfully")

        return results

    async def delete_document(
        self,
        document_id: str,
        collection_name: Optional[str] = None
    ) -> bool:
        """
        Elimina un documento de la base de datos vectorial.

        Elimina TODOS los chunks asociados a ese document_id.
        Útil para:
        - Re-procesar un documento actualizado
        - Eliminar documentos obsoletos
        - Limpieza de datos

        Args:
            document_id: ID del documento a eliminar
                        Ejemplo: "doc_abc123"
            collection_name: Colección donde está el documento (opcional)

        Returns:
            bool: True si se eliminó correctamente, False si hubo error

        Ejemplo:
            # Eliminar un documento
            success = await sync_service.delete_document("doc_abc123")

            # Re-ingestar después de actualizar el PDF
            if success:
                await sync_service.sync_document_from_file("/data/updated.pdf")
        """
        collection = collection_name or settings.chromadb_collection_name

        try:
            # Delega la eliminación al adaptador de vector DB
            success = await self.vector_db.delete_document(
                document_id=document_id,
                collection_name=collection
            )

            # Logging según resultado
            if success:
                logger.info(f"Deleted document {document_id} from collection '{collection}'")
            else:
                # warning en lugar de error porque no es necesariamente un fallo
                # (podría ser que el documento no existía)
                logger.warning(f"Failed to delete document {document_id}")

            return success

        except Exception as e:
            logger.error(f"Error deleting document {document_id}: {e}")
            return False
