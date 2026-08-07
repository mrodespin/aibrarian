#!/usr/bin/env python3
# /scripts/ingest_pdfs.py
"""
PDF Ingestion CLI - Bibliotecario-IA

This script is an ALTERNATIVE to the API for ingesting PDFs from the
terminal. Instead of making an HTTP request to POST /sync, you run it
directly from the command line.

When to use this script vs. the API?
- This script: development, manual batch ingestion, the API doesn't need to be running
- The API (POST /sync): when another application or the frontend needs to ingest

What does it do internally?
Exactly the same as main.py's /sync and /sync/directory endpoints:
it creates the same dependencies, uses the same SyncService, and runs
the same pipeline (load → split → embed → store). The only difference
is the entry point (CLI vs. HTTP).

Execution flow:
    1. check_services()     → Checks that the LLM and vector DB are up
    2. Initializes adapters and SyncService (same wiring as main.py)
    3. ingest_file() or ingest_directory() depending on the CLI arguments
    4. Prints a results summary

Usage:
    python ingest_pdfs.py                     # All PDFs in ./data
    python ingest_pdfs.py /path/to/pdfs       # PDFs from a specific directory
    python ingest_pdfs.py manual.pdf          # A single PDF (detects it's a file)
    python ingest_pdfs.py --file manual.pdf   # Same result, explicit
"""

# ============================================================================
# IMPORTS
# ============================================================================
import asyncio   # To run async code from a synchronous script
import logging
import sys
from pathlib import Path
from typing import Optional
import argparse   # Python's standard library for parsing CLI arguments
                  # Equivalent to libraries like 'commander' or 'yargs' in Node.js

# ============================================================================
# PATH SETUP
# ============================================================================
# sys.path.insert(0, ...): adds the api/ directory to the module search path.
#
# Why is this needed?
# This script lives in scripts/, but needs to import from api/app/*.
# Without this line, Python wouldn't find the "app" package.
#
# Path(__file__).parent = scripts/
# Path(__file__).parent.parent = project root
# Path(__file__).parent.parent / "api" = api/
sys.path.insert(0, str(Path(__file__).parent.parent / "api"))

from app.config.settings import settings
from app.core.services.sync_service import SyncService
from app.adapters.outbound.chromadb_adapter import ChromaDBAdapter
from app.adapters.outbound.ollama_adapter import OllamaAdapter
from app.adapters.outbound.pdf_processor_adapter import PDFProcessorAdapter


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
# This script is an alternative entry point to the API, not a separate
# system: it must respect LLM_PROVIDER/VECTOR_DB_PROVIDER just like
# main.py does, or if someone configures .env to use Groq/Chroma Cloud
# (e.g. to avoid running Ollama/ChromaDB locally), the CLI ingestion
# would silently ignore that config and hit Ollama/ChromaDB anyway.
# GroqAdapter/ChromaCloudAdapter are imported lazily, inside the
# function, so their heavy dependencies (groq, sentence-transformers →
# torch) aren't loaded unless they're actually used.
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
    Checks that the configured LLM and vector DB are up before
    proceeding (per settings.llm_provider / settings.vector_db_provider).

    Runs at the start of the script to fail fast with clear messages if
    a service isn't available, instead of failing mid-processing with
    confusing errors.

    Creates temporary adapter instances just for the check. The actual
    instances are created afterward in main().

    Returns:
        bool: True if all services are available
    """
    logger.info("Checking service availability...")

    # Check the LLM (needed for embeddings and text generation)
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

    # Check the vector DB (needed to store the embeddings)
    # collection_exists("test") is a lightweight call that checks
    # connectivity without creating or modifying real data.
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
async def ingest_file(file_path: Path, sync_service: SyncService):
    """
    Ingests a single PDF file.

    A thin wrapper around SyncService.sync_document_from_file() that adds
    visual formatting to the terminal output (separators, icons).

    Args:
        file_path: Path to the PDF file to process
        sync_service: Sync service instance

    Returns:
        SyncResult if processing was attempted, None if an exception occurred
    """
    logger.info(f"\n{'='*60}")
    logger.info(f"Processing: {file_path.name}")
    logger.info(f"{'='*60}")

    try:
        # Delegate all the work to the service (same pipeline as the API)
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
    """
    Ingests all PDF files in a directory.

    Iterates sequentially over the PDFs found, calling ingest_file() for
    each one. If a PDF fails, the script continues with the rest (a
    single file failing doesn't fail the whole run).

    Args:
        directory_path: Path to the directory to scan
        sync_service: Sync service instance

    Returns:
        list[SyncResult]: Results for each successfully processed PDF
    """
    logger.info(f"\n{'='*60}")
    logger.info(f"Scanning directory: {directory_path}")
    logger.info(f"{'='*60}")

    # glob("*.pdf") finds all .pdf files in the directory
    # list() materializes the generator into a list
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


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================
async def main():
    """
    Script's main function: parses arguments, initializes services and
    orchestrates the ingestion.

    Flow:
        1. Parse CLI arguments with argparse
        2. Check services (check_services)
        3. Initialize adapters and SyncService (same wiring as main.py)
        4. Detect mode: single file vs. directory
        5. Run the ingestion
        6. Print a summary
    """
    # ================================================================
    # CLI ARGUMENT PARSING (argparse)
    # ================================================================
    # argparse automatically builds --help and validates arguments.
    # JS equivalent: const program = new Command(); program.argument(...)
    parser = argparse.ArgumentParser(
        description="Ingest PDF documents into Bibliotecario-IA vector database"
    )
    parser.add_argument(
        "path",
        nargs="?",          # "?" = the argument is optional (positional)
        default=None,       # If not provided, it's None
        help="Path to PDF file or directory (defaults to ./data)"
    )
    parser.add_argument(
        "--file",
        "-f",               # "-f" is the short alias for "--file"
        action="store_true", # Takes no value: True if present, False otherwise
        help="Treat path as a single file, not a directory"
    )
    parser.add_argument(
        "--collection",
        "-c",
        default=None,
        help="Collection name (defaults to config setting)"
    )

    # parse_args() reads sys.argv and returns an object with the values.
    # args.path, args.file, args.collection are available afterward.
    args = parser.parse_args()

    # Script's visual banner
    print("\n" + "="*60)
    print("📚 Bibliotecario-IA - PDF Ingestion Script")
    print("="*60 + "\n")

    # ================================================================
    # SERVICE CHECK
    # ================================================================
    # Fail fast if something isn't available.
    # sys.exit(1) ends the script with an error code (not 0 = failure).
    if not await check_services():
        logger.error("\n❌ Service checks failed. Please fix the issues above and try again.")
        sys.exit(1)

    # ================================================================
    # DEPENDENCY INITIALIZATION
    # ================================================================
    # Same wiring as main.py: adapters → service.
    # Repeated here because this script is independent from the API.
    logger.info("\nInitializing services...")
    vector_db_adapter = _build_vector_db_adapter()
    llm_adapter = _build_llm_adapter()
    pdf_processor = PDFProcessorAdapter()

    sync_service = SyncService(
        document_processor=pdf_processor,
        llm=llm_adapter,
        vector_db=vector_db_adapter
    )

    # ================================================================
    # DETERMINE THE PATH TO PROCESS
    # ================================================================
    # If the user doesn't pass a path, use the default directory (./data)
    if args.path:
        path = Path(args.path)
    else:
        path = Path(settings.data_directory)
        logger.info(f"Using default data directory: {path}")

    if not path.exists():
        logger.error(f"❌ Path does not exist: {path}")
        sys.exit(1)

    # ================================================================
    # MODE: SINGLE FILE vs. DIRECTORY
    # ================================================================
    # Automatically detects whether it's a file or a directory.
    # The --file flag forces file mode (useful if the name is ambiguous).
    results = []

    if args.file or path.is_file():
        # --- Single file mode ---
        if not path.suffix.lower() == ".pdf":
            logger.error("❌ File must be a PDF")
            sys.exit(1)

        result = await ingest_file(path, sync_service)
        if result:
            results.append(result)

    else:
        # --- Directory mode ---
        if not path.is_dir():
            logger.error(f"❌ Not a directory: {path}")
            sys.exit(1)

        results = await ingest_directory(path, sync_service)

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


# ============================================================================
# ENTRY POINT
# ============================================================================
# asyncio.run(main()): bridges the synchronous world (if __name__) with
# the asynchronous one (all functions are async).
#
# asyncio.run() creates an event loop, runs the main() coroutine, and
# closes it when done. It's the equivalent of:
#   const main = async () => { ... };
#   main().catch(console.error);
#
# KeyboardInterrupt: caught when the user presses Ctrl+C.
# sys.exit(0) = clean exit (code 0 = success).
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n\n⚠️  Ingestion interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"\n\n❌ Fatal error: {e}", exc_info=True)
        sys.exit(1)
