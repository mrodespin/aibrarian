#!/usr/bin/env python3
# /api/ingest_notion.py

"""
Notion Ingestion Script for Bibliotecario-IA.

This script processes Notion pages and ingests them into the vector database.
It can be run from the command line.

Usage:
    python ingest_notion.py --page PAGE_ID              # Process a single page
    python ingest_notion.py --database DATABASE_ID      # Process all pages in a database
    python ingest_notion.py --database DATABASE_ID --max 10  # Process up to 10 pages
"""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Optional
import argparse

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent))

from app.config.settings import settings
from app.core.services.sync_service import SyncService
from app.adapters.outbound.chromadb_adapter import ChromaDBAdapter
from app.adapters.outbound.ollama_adapter import OllamaAdapter
from app.adapters.outbound.notion_processor_adapter import NotionProcessorAdapter


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def check_services():
    """Check if required services are available."""
    logger.info("Checking service availability...")

    # Check Notion API key
    if not settings.notion_api_key:
        logger.error("❌ Notion API key not configured!")
        logger.error("   Set NOTION_API_KEY environment variable")
        logger.error("   Get your integration token at: https://www.notion.so/my-integrations")
        return False

    logger.info("✅ Notion API key configured")

    # Check Ollama
    ollama = OllamaAdapter()
    ollama_ok = await ollama.is_available()

    if not ollama_ok:
        logger.error("❌ Ollama is not available!")
        logger.error(f"   Make sure Ollama is running at {settings.ollama_base_url}")
        logger.error("   Run: ollama serve")
        return False

    logger.info(f"✅ Ollama is available ({settings.ollama_model})")

    # Check ChromaDB
    chromadb = ChromaDBAdapter()
    try:
        exists = await chromadb.collection_exists("test")
        logger.info(f"✅ ChromaDB is available ({settings.chromadb_url})")
    except Exception as e:
        logger.error(f"❌ ChromaDB is not available: {e}")
        logger.error("   Make sure ChromaDB is running")
        return False

    return True


async def ingest_page(page_id: str, sync_service: SyncService):
    """Ingest a single Notion page."""
    logger.info(f"\n{'='*60}")
    logger.info(f"Processing Notion page: {page_id}")
    logger.info(f"{'='*60}")

    try:
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
    """Ingest all pages from a Notion database."""
    logger.info(f"\n{'='*60}")
    logger.info(f"Loading pages from database: {database_id}")
    logger.info(f"{'='*60}")

    try:
        # Load all pages
        documents = await notion_processor.load_database_pages(
            database_id=database_id,
            max_pages=max_pages
        )

        if not documents:
            logger.warning(f"No pages found in database {database_id}")
            return []

        logger.info(f"Found {len(documents)} pages")

        results = []
        for i, doc in enumerate(documents, 1):
            logger.info(f"\n[{i}/{len(documents)}] Processing: {doc.metadata.get('title', 'Untitled')}")

            try:
                # Split into chunks
                chunks = await notion_processor.split_into_chunks(doc)

                # The sync service will handle embedding generation and storage
                # We'll manually process since we already have the document loaded
                from app.adapters.outbound.ollama_adapter import OllamaAdapter
                from app.adapters.outbound.chromadb_adapter import ChromaDBAdapter

                ollama = OllamaAdapter()
                chromadb = ChromaDBAdapter()

                # Generate embeddings
                chunk_texts = [chunk.content for chunk in chunks]
                embeddings = await ollama.generate_embeddings_batch(chunk_texts)

                # Attach embeddings
                for chunk, embedding in zip(chunks, embeddings):
                    chunk.embedding = embedding

                # Store
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
                logger.error(f"   ❌ Error: {e}")
                continue

        return results

    except Exception as e:
        logger.error(f"❌ Failed to load database: {e}", exc_info=True)
        return []


async def main():
    """Main entry point."""
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
        type=int,
        help="Maximum number of pages to ingest from database"
    )
    parser.add_argument(
        "--collection",
        "-c",
        default=None,
        help="Collection name (defaults to config setting)"
    )

    args = parser.parse_args()

    # Validate arguments
    if not args.page and not args.database:
        parser.error("Either --page or --database must be specified")

    # Print banner
    print("\n" + "="*60)
    print("📚 Bibliotecario-IA - Notion Ingestion Script")
    print("="*60 + "\n")

    # Check services
    if not await check_services():
        logger.error("\n❌ Service checks failed. Please fix the issues above and try again.")
        sys.exit(1)

    # Initialize services
    logger.info("\nInitializing services...")
    chromadb_adapter = ChromaDBAdapter()
    ollama_adapter = OllamaAdapter()
    notion_processor = NotionProcessorAdapter()

    sync_service = SyncService(
        document_processor=notion_processor,
        llm=ollama_adapter,
        vector_db=chromadb_adapter
    )

    # Process pages
    results = []

    if args.page:
        # Single page mode
        result = await ingest_page(args.page, sync_service)
        if result:
            results.append(result)

    elif args.database:
        # Database mode
        database_id = args.database
        results = await ingest_database(
            database_id=database_id,
            notion_processor=notion_processor,
            sync_service=sync_service,
            max_pages=args.max
        )

    # Print summary
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


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n\n⚠️  Ingestion interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"\n\n❌ Fatal error: {e}", exc_info=True)
        sys.exit(1)
