#!/usr/bin/env python3
# /api/ingest_notion.py
"""
Script CLI de Ingesta de Notion - TFM Bibliotecario-IA

Este script es la versión CLI para ingestar contenido de Notion.
Equivalente a los endpoints POST /sync/notion y POST /sync/notion/database
de la API, pero ejecutado desde el terminal.

¿Cuándo usar este script vs la API?
- Este script: desarrollo, ingesta manual, no necesitas la API activa
- La API: cuando otra aplicación o el frontend necesita ingestar

Dos modos de operación:
- --page PAGE_ID:       Ingesta una página individual de Notion
- --database DB_ID:     Ingesta todas las páginas de una base de datos

Requisito previo:
    Se necesita NOTION_API_KEY configurada en .env o como variable de entorno.
    Se obtiene desde: https://www.notion.so/my-integrations

Uso:
    python ingest_notion.py --page PAGE_ID
    python ingest_notion.py --database DATABASE_ID
    python ingest_notion.py --database DATABASE_ID --max 10
"""

# ============================================================================
# IMPORTS
# ============================================================================
import asyncio
import logging
import sys
from pathlib import Path
from typing import Optional
import argparse

# ============================================================================
# CONFIGURACIÓN DE PATH
# ============================================================================
# Mismo patrón que en ingest_pdfs.py: añade api/ al path para que
# Python encuentre el paquete "app" al ejecutar el script directamente.
sys.path.insert(0, str(Path(__file__).parent))

from app.config.settings import settings
from app.core.services.sync_service import SyncService
from app.adapters.outbound.chromadb_adapter import ChromaDBAdapter
from app.adapters.outbound.ollama_adapter import OllamaAdapter
from app.adapters.outbound.notion_processor_adapter import NotionProcessorAdapter


# ============================================================================
# CONFIGURACIÓN DE LOGGING
# ============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# ============================================================================
# VERIFICACIÓN DE SERVICIOS
# ============================================================================
async def check_services():
    """
    Verifica que todos los servicios necesarios están activos.

    A diferencia de ingest_pdfs.py, aquí se añade una verificación extra:
    que NOTION_API_KEY esté configurada. Sin esta key no es posible conectar
    con la API de Notion.

    Returns:
        bool: True si todos los servicios y la configuración están correctos
    """
    logger.info("Checking service availability...")

    # Verificar NOTION_API_KEY (requisito específico de este script)
    if not settings.notion_api_key:
        logger.error("❌ Notion API key not configured!")
        logger.error("   Set NOTION_API_KEY environment variable")
        logger.error("   Get your integration token at: https://www.notion.so/my-integrations")
        return False

    logger.info("✅ Notion API key configured")

    # Verificar Ollama
    ollama = OllamaAdapter()
    ollama_ok = await ollama.is_available()

    if not ollama_ok:
        logger.error("❌ Ollama is not available!")
        logger.error(f"   Make sure Ollama is running at {settings.ollama_base_url}")
        logger.error("   Run: ollama serve")
        return False

    logger.info(f"✅ Ollama is available ({settings.ollama_model})")

    # Verificar ChromaDB
    chromadb = ChromaDBAdapter()
    try:
        exists = await chromadb.collection_exists("test")
        logger.info(f"✅ ChromaDB is available ({settings.chromadb_url})")
    except Exception as e:
        logger.error(f"❌ ChromaDB is not available: {e}")
        logger.error("   Make sure ChromaDB is running")
        return False

    return True


# ============================================================================
# FUNCIONES DE INGESTA
# ============================================================================
async def ingest_page(page_id: str, sync_service: SyncService):
    """
    Ingesta una página individual de Notion.

    Delega al SyncService que internamente usa NotionProcessorAdapter
    para cargar la página, dividirla en chunks, generar embeddings
    y almacenarla en ChromaDB. El pipeline es idéntico al de PDFs,
    solo cambia el adaptador de origen.

    Args:
        page_id: ID de página o URL de Notion
        sync_service: Instancia de SyncService con NotionProcessorAdapter

    Returns:
        SyncResult si el procesamiento se intentó, None si hubo excepción
    """
    logger.info(f"\n{'='*60}")
    logger.info(f"Processing Notion page: {page_id}")
    logger.info(f"{'='*60}")

    try:
        # sync_document_from_file acepta page_id como "source"
        # el NotionProcessorAdapter sabe cómo tratarlo
        result = await sync_service.sync_document_from_file(page_id)

        if result.success:
            logger.info(f"✅ Successfully ingested page")
            logger.info(f"   Document ID: {result.document_id}")
            logger.info(f"   Chunks created: {result.chunks_created}")
            logger.info(f"   Processing time: {result.processing_time:.2f}s")
        else:
            logger.error(f"❌ Failed to ingest page")
            logger.error(f"   Error: {result.message}")

        return result

    except Exception as e:
        logger.error(f"❌ Error processing page {page_id}: {e}", exc_info=True)
        return None


async def ingest_database(
    database_id: str,
    notion_processor: NotionProcessorAdapter,
    sync_service: SyncService,
    max_pages: Optional[int] = None
):
    """
    Ingesta todas las páginas de una base de datos de Notion.

    Flujo:
        1. Cargar todas las páginas con load_database_pages()
        2. Para cada página: dividir en chunks → embeddings → almacenar

    ¿Por qué no usar sync_service aquí?
    sync_service.sync_document_from_file() carga el documento desde cero
    (llama a load_document internamente). Como load_database_pages() ya
    nos devuelve los documentos cargados en memoria, volver a cargarlos
    uno a uno sería redundante. Por eso se implementa el pipeline
    split → embed → store de forma directa.

    Nota sobre errores por página:
    Si una página falla, se loguea el error y el bucle CONTINÚA con las
    siguientes (continue). No falla toda la ingesta por una página.

    Args:
        database_id: ID de la base de datos de Notion
        notion_processor: Adaptador de Notion (para split y load_database_pages)
        sync_service: Instancia de SyncService (recibido pero no usado, ver nota)
        max_pages: Máximo de páginas a procesar (None = todas)

    Returns:
        list[SyncResult]: Resultados de cada página procesada
    """
    logger.info(f"\n{'='*60}")
    logger.info(f"Loading pages from database: {database_id}")
    logger.info(f"{'='*60}")

    try:
        # Cargar todas las páginas de la base de datos
        documents = await notion_processor.load_database_pages(
            database_id=database_id,
            max_pages=max_pages
        )

        if not documents:
            logger.warning(f"No pages found in database {database_id}")
            return []

        logger.info(f"Found {len(documents)} pages")

        # NOTE: Las siguientes líneas crean instancias nuevas de los adaptadores
        # en cada iteración del bucle. Esto es redundante porque OllamaAdapter
        # y ChromaDBAdapter ya están importados arriba y podrían instanciarse
        # una sola vez fuera del bucle. Funciona gracias a la lazy initialization
        # de los adaptadores (la conexión real se crea una sola vez internamente),
        # pero es un patrón que podría limpiarse.
        # También, la importación de SyncResult dentro del bucle podría
        # moverse al bloque de imports del fichero.
        results = []
        for i, doc in enumerate(documents, 1):
            logger.info(f"\n[{i}/{len(documents)}] Processing: {doc.metadata.get('title', 'Untitled')}")

            try:
                # Dividir la página en chunks
                chunks = await notion_processor.split_into_chunks(doc)

                # Instancias de adaptadores (ver nota de arriba)
                from app.adapters.outbound.ollama_adapter import OllamaAdapter
                from app.adapters.outbound.chromadb_adapter import ChromaDBAdapter

                ollama = OllamaAdapter()
                chromadb = ChromaDBAdapter()

                # Generar embeddings en batch para todos los chunks
                chunk_texts = [chunk.content for chunk in chunks]
                embeddings = await ollama.generate_embeddings_batch(chunk_texts)

                # Asignar embeddings a los chunks
                for chunk, embedding in zip(chunks, embeddings):
                    chunk.embedding = embedding

                # Almacenar en ChromaDB
                success = await chromadb.store_chunks(chunks)

                from app.core.domain.models import SyncResult
                result = SyncResult(
                    document_id=doc.id,
                    chunks_created=len(chunks),
                    success=success,
                    message=f"Synced '{doc.metadata.get('title', 'Untitled')}'"
                )

                results.append(result)

                if success:
                    logger.info(f"   ✅ Success: {len(chunks)} chunks")
                else:
                    logger.error(f"   ❌ Failed to store chunks")

            except Exception as e:
                # Error en una página: loguear y continuar con la siguiente
                # "continue" salta a la siguiente iteración del bucle
                logger.error(f"   ❌ Error: {e}")
                continue

        return results

    except Exception as e:
        logger.error(f"❌ Failed to load database: {e}", exc_info=True)
        return []


# ============================================================================
# PUNTO DE ENTRADA PRINCIPAL
# ============================================================================
async def main():
    """
    Función principal: parsea argumentos, inicializa servicios y orquesta
    la ingesta según el modo seleccionado (página vs base de datos).

    A diferencia de ingest_pdfs.py donde el modo se detecta automáticamente
    (fichero vs directorio), aquí el modo es explícito:
    - --page    → modo página individual
    - --database → modo base de datos completa
    """
    # ================================================================
    # PARSEO DE ARGUMENTOS CLI
    # ================================================================
    parser = argparse.ArgumentParser(
        description="Ingest Notion pages into Bibliotecario-IA vector database"
    )
    parser.add_argument(
        "--page",
        "-p",
        help="Notion page ID or URL to ingest"
    )
    parser.add_argument(
        "--database",
        "-d",
        help="Notion database ID to ingest all pages from"
    )
    parser.add_argument(
        "--max",
        "-m",
        type=int,  # type=int: argparse convierte el valor automáticamente a entero
        help="Maximum number of pages to ingest from database"
    )
    parser.add_argument(
        "--collection",
        "-c",
        default=None,
        help="Collection name (defaults to config setting)"
    )

    args = parser.parse_args()

    # Validación: se necesita al menos uno de los dos modos.
    # parser.error() imprime el mensaje de error y sale automáticamente.
    if not args.page and not args.database:
        parser.error("Either --page or --database must be specified")

    # Banner visual
    print("\n" + "="*60)
    print("📚 Bibliotecario-IA - Notion Ingestion Script")
    print("="*60 + "\n")

    # ================================================================
    # VERIFICACIÓN DE SERVICIOS
    # ================================================================
    if not await check_services():
        logger.error("\n❌ Service checks failed. Please fix the issues above and try again.")
        sys.exit(1)

    # ================================================================
    # INICIALIZACIÓN DE DEPENDENCIAS
    # ================================================================
    # Misma wiring que notion_sync_service en main.py:
    # SyncService con NotionProcessorAdapter como DocumentProcessor.
    logger.info("\nInitializing services...")
    chromadb_adapter = ChromaDBAdapter()
    ollama_adapter = OllamaAdapter()
    notion_processor = NotionProcessorAdapter()

    sync_service = SyncService(
        document_processor=notion_processor,
        llm=ollama_adapter,
        vector_db=chromadb_adapter
    )

    # ================================================================
    # MODO DE OPERACIÓN
    # ================================================================
    results = []

    if args.page:
        # --- Modo página individual ---
        # Delega completamente al SyncService
        result = await ingest_page(args.page, sync_service)
        if result:
            results.append(result)

    elif args.database:
        # --- Modo base de datos ---
        # Necesita notion_processor para load_database_pages()
        # y sync_service se pasa por firma (aunque internamente no lo usa, ver nota en ingest_database)
        database_id = args.database
        results = await ingest_database(
            database_id=database_id,
            notion_processor=notion_processor,
            sync_service=sync_service,
            max_pages=args.max
        )

    # ================================================================
    # RESUMEN DE RESULTADOS
    # ================================================================
    print("\n" + "="*60)
    print("📊 Ingestion Summary")
    print("="*60)

    if results:
        successful = sum(1 for r in results if r.success)
        failed = len(results) - successful
        total_chunks = sum(r.chunks_created for r in results if r.success)
        total_time = sum(r.processing_time for r in results if r.processing_time)

        print(f"Total pages: {len(results)}")
        print(f"✅ Successful: {successful}")
        print(f"❌ Failed: {failed}")
        print(f"📦 Total chunks created: {total_chunks}")
        if total_time > 0:
            print(f"⏱️  Total processing time: {total_time:.2f}s")

        if successful > 0:
            print(f"\n✨ Notion pages are now available for querying!")
            print(f"   Collection: {args.collection or settings.chromadb_collection_name}")
    else:
        print("❌ No pages were processed")

    print("="*60 + "\n")


# ============================================================================
# BLOQUE DE ENTRADA
# ============================================================================
# Mismo patrón que en ingest_pdfs.py:
# asyncio.run() es el puente entre el mundo síncrono y async.
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n\n⚠️  Ingestion interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"\n\n❌ Fatal error: {e}", exc_info=True)
        sys.exit(1)
