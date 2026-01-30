#!/usr/bin/env python3
# /api/ingest_pdfs.py

"""
PDF Ingestion Script for Bibliotecario-IA.

This script processes PDF documents from a specified directory and ingests them
into the vector database. It can be run from the command line.

Usage:
    python ingest_pdfs.py                    # Process all PDFs in ./data
    python ingest_pdfs.py /path/to/pdfs      # Process PDFs from specific directory
    python ingest_pdfs.py --file document.pdf # Process a single PDF file
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
from app.adapters.outbound.pdf_processor_adapter import PDFProcessorAdapter


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def check_services():
    """Check if required services are available."""
    logger.info("Checking service availability...")

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


async def ingest_file(file_path: Path, sync_service: SyncService):
    """Ingest a single PDF file."""
    logger.info(f"\n{'='*60}")
    logger.info(f"Processing: {file_path.name}")
    logger.info(f"{'='*60}")

    try:
        result = await sync_service.sync_document_from_file(file_path)

        if result.success:
            logger.info(f"✅ Successfully ingested: {file_path.name}")
            logger.info(f"   Document ID: {result.document_id}")
            logger.info(f"   Chunks created: {result.chunks_created}")
            logger.info(f"   Processing time: {result.processing_time:.2f}s")
        else:
            logger.error(f"❌ Failed to ingest: {file_path.name}")
            logger.error(f"   Error: {result.message}")

        return result

    except Exception as e:
        logger.error(f"❌ Error processing {file_path.name}: {e}", exc_info=True)
        return None


async def ingest_directory(directory_path: Path, sync_service: SyncService):
    """Ingest all PDF files from a directory."""
    logger.info(f"\n{'='*60}")
    logger.info(f"Scanning directory: {directory_path}")
    logger.info(f"{'='*60}")

    pdf_files = list(directory_path.glob("*.pdf"))

    if not pdf_files:
        logger.warning(f"No PDF files found in {directory_path}")
        return []

    logger.info(f"Found {len(pdf_files)} PDF files")

    results = []
    for pdf_file in pdf_files:
        result = await ingest_file(pdf_file, sync_service)
        if result:
            results.append(result)

    return results


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Ingest PDF documents into Bibliotecario-IA vector database"
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=None,
        help="Path to PDF file or directory (defaults to ./data)"
    )
    parser.add_argument(
        "--file",
        "-f",
        action="store_true",
        help="Treat path as a single file, not a directory"
    )
    parser.add_argument(
        "--collection",
        "-c",
        default=None,
        help="Collection name (defaults to config setting)"
    )

    args = parser.parse_args()

    # Print banner
    print("\n" + "="*60)
    print("📚 Bibliotecario-IA - PDF Ingestion Script")
    print("="*60 + "\n")

    # Check services
    if not await check_services():
        logger.error("\n❌ Service checks failed. Please fix the issues above and try again.")
        sys.exit(1)

    # Initialize services
    logger.info("\nInitializing services...")
    chromadb_adapter = ChromaDBAdapter()
    ollama_adapter = OllamaAdapter()
    pdf_processor = PDFProcessorAdapter()

    sync_service = SyncService(
        document_processor=pdf_processor,
        llm=ollama_adapter,
        vector_db=chromadb_adapter
    )

    # Determine path
    if args.path:
        path = Path(args.path)
    else:
        path = Path(settings.data_directory)
        logger.info(f"Using default data directory: {path}")

    if not path.exists():
        logger.error(f"❌ Path does not exist: {path}")
        sys.exit(1)

    # Process files
    results = []

    if args.file or path.is_file():
        # Single file mode
        if not path.suffix.lower() == ".pdf":
            logger.error("❌ File must be a PDF")
            sys.exit(1)

        result = await ingest_file(path, sync_service)
        if result:
            results.append(result)

    else:
        # Directory mode
        if not path.is_dir():
            logger.error(f"❌ Not a directory: {path}")
            sys.exit(1)

        results = await ingest_directory(path, sync_service)

    # Print summary
    print("\n" + "="*60)
    print("📊 Ingestion Summary")
    print("="*60)

    if results:
        successful = sum(1 for r in results if r.success)
        failed = len(results) - successful
        total_chunks = sum(r.chunks_created for r in results if r.success)
        total_time = sum(r.processing_time for r in results if r.processing_time)

        print(f"Total files: {len(results)}")
        print(f"✅ Successful: {successful}")
        print(f"❌ Failed: {failed}")
        print(f"📦 Total chunks created: {total_chunks}")
        print(f"⏱️  Total processing time: {total_time:.2f}s")

        if successful > 0:
            print(f"\n✨ Documents are now available for querying!")
            print(f"   Collection: {args.collection or settings.chromadb_collection_name}")
    else:
        print("❌ No documents were processed")

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
