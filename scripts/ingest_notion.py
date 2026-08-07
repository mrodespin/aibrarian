#!/usr/bin/env python3
# /scripts/ingest_notion.py
"""
Notion Ingestion CLI - Bibliotecario-IA

This script is the CLI version for ingesting Notion content.
Equivalent to the API's POST /sync/notion and POST /sync/notion/database
endpoints, but run from the terminal.

When to use this script vs. the API?
- This script: development, manual ingestion, the API doesn't need to be running
- The API: when another application or the frontend needs to ingest

Two modes of operation:
- --page PAGE_ID:       Ingest a single Notion page
- --database DB_ID:     Ingest all pages in a database

Prerequisite:
    NOTION_API_KEY needs to be configured in .env or as an environment
    variable. Get one at: https://www.notion.so/my-integrations

Usage:
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
# PATH SETUP
# ============================================================================
# Same pattern as ingest_pdfs.py: adds api/ to the path so Python finds
# the "app" package when the script is run directly.
# The script lives in scripts/, so we need to go up to the root and then api/
sys.path.insert(0, str(Path(__file__).parent.parent / "api"))

from app.config.settings import settings
from app.core.services.sync_service import SyncService
from app.adapters.outbound.chromadb_adapter import ChromaDBAdapter
from app.adapters.outbound.ollama_adapter import OllamaAdapter
from app.adapters.outbound.notion_processor_adapter import NotionProcessorAdapter


# ============================================================================
# LOGGING SETUP
# ============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# ============================================================================
# ADAPTER SELECTION (same logic as api/app/main.py, see ADR-007)
# ============================================================================
# Same reasoning as ingest_pdfs.py: this script must respect
# LLM_PROVIDER/VECTOR_DB_PROVIDER instead of always forcing Ollama/ChromaDB,
# or it would silently ignore the config of anyone running Groq/Chroma
# Cloud locally.
def _build_llm_adapter():
    if settings.llm_provider == "groq":
        from app.adapters.outbound.groq_adapter import GroqAdapter
        return GroqAdapter()
    return OllamaAdapter()


def _build_vector_db_adapter():
    if settings.vector_db_provider == "chroma_cloud":
        from app.adapters.outbound.chromadb_cloud_adapter import ChromaCloudAdapter
        return ChromaCloudAdapter()
    return ChromaDBAdapter()


# ============================================================================
# SERVICE AVAILABILITY CHECK
# ============================================================================
async def check_services():
    """
    Checks that all required services are up.

    Unlike ingest_pdfs.py, this adds one extra check: that
    NOTION_API_KEY is configured. Without this key it's not possible to
    connect to the Notion API.

    Returns:
        bool: True if all services and configuration are correct
    """
    logger.info("Checking service availability...")

    # Check NOTION_API_KEY (a requirement specific to this script)
    if not settings.notion_api_key:
        logger.error("❌ Notion API key not configured!")
        logger.error("   Set NOTION_API_KEY environment variable")
        logger.error("   Get your integration token at: https://www.notion.so/my-integrations")
        return False

    logger.info("✅ Notion API key configured")

    # Check the configured LLM (Ollama by default, or Groq)
    llm_adapter = _build_llm_adapter()
    llm_ok = await llm_adapter.is_available()

    if not llm_ok:
        logger.error(f"❌ LLM ({settings.llm_provider}) is not available!")
        if settings.llm_provider == "groq":
            logger.error("   Check GROQ_API_KEY in .env")
        else:
            logger.error(f"   Make sure Ollama is running at {settings.ollama_base_url}")
            logger.error("   Run: ollama serve")
        return False

    logger.info(f"✅ LLM is available (provider={settings.llm_provider})")

    # Check the configured vector DB (local ChromaDB by default, or Chroma Cloud)
    vector_db_adapter = _build_vector_db_adapter()
    try:
        exists = await vector_db_adapter.collection_exists("test")
        logger.info(f"✅ Vector DB is available (provider={settings.vector_db_provider})")
    except Exception as e:
        logger.error(f"❌ Vector DB ({settings.vector_db_provider}) is not available: {e}")
        if settings.vector_db_provider != "chroma_cloud":
            logger.error("   Make sure ChromaDB is running")
        return False

    return True


# ============================================================================
# INGESTION FUNCTIONS
# ============================================================================
async def ingest_page(page_id: str, sync_service: SyncService):
    """
    Ingests a single Notion page.

    Delegates to SyncService, which internally uses NotionProcessorAdapter
    to load the page, split it into chunks, generate embeddings and
    store it in ChromaDB. The pipeline is identical to the PDF one,
    only the source adapter changes.

    Args:
        page_id: Notion page ID or URL
        sync_service: SyncService instance wired with NotionProcessorAdapter

    Returns:
        SyncResult if processing was attempted, None if an exception occurred
    """
    logger.info(f"\n{'='*60}")
    logger.info(f"Processing Notion page: {page_id}")
    logger.info(f"{'='*60}")

    try:
        # sync_document_from_file accepts page_id as the "source" —
        # NotionProcessorAdapter knows how to handle it
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
    Ingests all pages in a Notion database.

    Flow:
        1. Load all pages with load_database_pages()
        2. For each page: split into chunks → embeddings → store

    Why not use sync_service here?
    sync_service.sync_document_from_file() loads the document from
    scratch (it calls load_document internally). Since
    load_database_pages() already returns the documents loaded in
    memory, reloading them one by one would be redundant. That's why
    the split → embed → store pipeline is implemented directly instead.

    Note on per-page errors:
    If a page fails, the error is logged and the loop CONTINUES with
    the rest (continue). A single page doesn't fail the whole ingestion.

    Args:
        database_id: Notion database ID
        notion_processor: Notion adapter (for split and load_database_pages)
        sync_service: SyncService instance (received but unused, see note above)
        max_pages: Maximum number of pages to process (None = all)

    Returns:
        list[SyncResult]: Results for each processed page
    """
    logger.info(f"\n{'='*60}")
    logger.info(f"Loading pages from database: {database_id}")
    logger.info(f"{'='*60}")

    try:
        # Load all pages in the database
        documents = await notion_processor.load_database_pages(
            database_id=database_id,
            max_pages=max_pages
        )

        if not documents:
            logger.warning(f"No pages found in database {database_id}")
            return []

        logger.info(f"Found {len(documents)} pages")

        # NOTE: the lines below create new adapter instances on every
        # loop iteration. This is redundant since they could be
        # instantiated once outside the loop. It works thanks to the
        # adapters' lazy initialization (the real connection is only
        # created once internally), but it's a pattern that could be
        # cleaned up. Also, the SyncResult import inside the loop could
        # be moved to the file's import block.
        # This part WAS fixed here: it used to hardcode
        # OllamaAdapter/ChromaDBAdapter directly, ignoring
        # LLM_PROVIDER/VECTOR_DB_PROVIDER (see _build_llm_adapter /
        # _build_vector_db_adapter above).
        results = []
        for i, doc in enumerate(documents, 1):
            logger.info(f"\n[{i}/{len(documents)}] Processing: {doc.metadata.get('title', 'Untitled')}")

            try:
                # Split the page into chunks
                chunks = await notion_processor.split_into_chunks(doc)

                # Adapter instances (see note above)
                llm_adapter = _build_llm_adapter()
                vector_db_adapter = _build_vector_db_adapter()

                # Generate embeddings in batch for all chunks
                chunk_texts = [chunk.content for chunk in chunks]
                embeddings = await llm_adapter.generate_embeddings_batch(chunk_texts)

                # Assign embeddings to the chunks
                for chunk, embedding in zip(chunks, embeddings):
                    chunk.embedding = embedding

                # Store in the vector DB
                success = await vector_db_adapter.store_chunks(chunks)

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
                # Error on a single page: log it and continue with the next one
                # "continue" jumps to the next loop iteration
                logger.error(f"   ❌ Error: {e}")
                continue

        return results

    except Exception as e:
        logger.error(f"❌ Failed to load database: {e}", exc_info=True)
        return []


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================
async def main():
    """
    Main function: parses arguments, initializes services and
    orchestrates the ingestion according to the selected mode (page vs.
    database).

    Unlike ingest_pdfs.py where the mode is auto-detected (file vs.
    directory), here the mode is explicit:
    - --page    → single page mode
    - --database → full database mode
    """
    # ================================================================
    # CLI ARGUMENT PARSING
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
        type=int,  # type=int: argparse automatically converts the value to an int
        help="Maximum number of pages to ingest from database"
    )
    parser.add_argument(
        "--collection",
        "-c",
        default=None,
        help="Collection name (defaults to config setting)"
    )

    args = parser.parse_args()

    # Validation: at least one of the two modes is required.
    # parser.error() prints the error message and exits automatically.
    if not args.page and not args.database:
        parser.error("Either --page or --database must be specified")

    # Visual banner
    print("\n" + "="*60)
    print("📚 Bibliotecario-IA - Notion Ingestion Script")
    print("="*60 + "\n")

    # ================================================================
    # SERVICE CHECK
    # ================================================================
    if not await check_services():
        logger.error("\n❌ Service checks failed. Please fix the issues above and try again.")
        sys.exit(1)

    # ================================================================
    # DEPENDENCY INITIALIZATION
    # ================================================================
    # Same wiring as notion_sync_service in main.py:
    # SyncService with NotionProcessorAdapter as the DocumentProcessor.
    logger.info("\nInitializing services...")
    vector_db_adapter = _build_vector_db_adapter()
    llm_adapter = _build_llm_adapter()
    notion_processor = NotionProcessorAdapter()

    sync_service = SyncService(
        document_processor=notion_processor,
        llm=llm_adapter,
        vector_db=vector_db_adapter
    )

    # ================================================================
    # OPERATION MODE
    # ================================================================
    results = []

    if args.page:
        # --- Single page mode ---
        # Delegates entirely to SyncService
        result = await ingest_page(args.page, sync_service)
        if result:
            results.append(result)

    elif args.database:
        # --- Database mode ---
        # Needs notion_processor for load_database_pages()
        # and sync_service is passed for signature reasons (it's not
        # actually used internally, see the note in ingest_database)
        database_id = args.database
        results = await ingest_database(
            database_id=database_id,
            notion_processor=notion_processor,
            sync_service=sync_service,
            max_pages=args.max
        )

    # ================================================================
    # RESULTS SUMMARY
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
# ENTRY POINT
# ============================================================================
# Same pattern as ingest_pdfs.py:
# asyncio.run() bridges the synchronous and async worlds.
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n\n⚠️  Ingestion interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"\n\n❌ Fatal error: {e}", exc_info=True)
        sys.exit(1)
