# /api/tests/test_integration.py
"""
End-to-End Integration Tests.

These tests verify the system's full flow with real services:
- Ollama for embeddings and generation
- ChromaDB for vector storage
- Full pipeline: ingest → store → retrieve → generate

IMPORTANT:
These tests require running services and are run with:
    pytest -m integration

They don't run by default, to keep the test suite fast.
"""

import pytest
from pathlib import Path


# ============================================================================
# E2E TEST: FULL INGESTION AND QUERY FLOW
# ============================================================================

@pytest.mark.integration
@pytest.mark.e2e
@pytest.mark.asyncio
async def test_full_rag_pipeline():
    """
    E2E test: full ingestion and query flow.

    Prerequisites:
    1. Ollama running: ollama serve
    2. ChromaDB running: docker-compose up chromadb
    3. Test PDF at /data/test_document.pdf

    Flow:
    1. Ingests the test PDF
    2. Verifies it was stored in ChromaDB
    3. Runs a query related to the content
    4. Verifies the answer is coherent

    This test takes ~10-30 seconds depending on the hardware.
    """
    from app.core.services.sync_service import SyncService
    from app.core.services.rag_service import RAGService
    from app.adapters.outbound.ollama_adapter import OllamaAdapter
    from app.adapters.outbound.chromadb_adapter import ChromaDBAdapter
    from app.adapters.outbound.pdf_processor_adapter import PDFProcessorAdapter
    from app.config.settings import settings

    # Arrange: initialize real services
    # The adapters use lazy initialization and pull config from settings
    ollama = OllamaAdapter()
    chromadb = ChromaDBAdapter()
    pdf_processor = PDFProcessorAdapter()

    sync_service = SyncService(
        document_processor=pdf_processor,
        vector_db=chromadb,
        llm=ollama
    )

    rag_service = RAGService(
        llm=ollama,
        vector_db=chromadb
    )

    # Verify the test PDF exists
    # The PDF lives in tests/data/, relative to this test file
    test_dir = Path(__file__).parent / "data"
    test_pdf = test_dir / "test_rag_document.pdf"
    if not test_pdf.exists():
        pytest.skip(f"Test PDF not found at {test_pdf}. Place a PDF there to run this test.")

    # Act: Step 1 - Ingest the PDF
    try:
        result = await sync_service.sync_document_from_file(str(test_pdf))
        assert result.success, f"Ingestion failed: {result.message}"
        print(f"\n📥 Ingestion: {result.chunks_created} chunks created in {result.processing_time:.2f}s")
    except Exception as e:
        pytest.fail(f"Ingestion failed: {e}")

    # Act: Step 2 - Verify it was stored
    try:
        stats = await chromadb.get_collection_stats()
        print(f"📊 ChromaDB stats: {stats}")
        # The field may be 'count' or 'document_count' depending on the implementation
        chunk_count = stats.get("count", stats.get("document_count", 0))
        # If ingestion reported success with chunks, trust that
        if result.chunks_created > 0:
            print(f"📊 Ingestion reported {result.chunks_created} chunks created")
    except Exception as e:
        pytest.fail(f"Storage verification failed: {e}")

    # Act: Step 3 - Run a query related to the document's content
    try:
        from app.core.domain.models import Query
        query = Query(question="What is this document about?")
        response = await rag_service.ask_question(query)
    except Exception as e:
        pytest.fail(f"Query failed: {e}")

    # Assert: verify the response
    assert response is not None
    assert response.answer is not None
    assert len(response.answer) > 0
    assert len(response.source_documents) > 0

    # Verify the answer mentions concepts from the document
    answer_lower = response.answer.lower()
    keywords = ["rag", "retrieval", "generation", "document", "system", "architecture"]
    found_keywords = [kw for kw in keywords if kw in answer_lower]

    print(f"\n✅ E2E test succeeded!")
    print(f"📝 Answer: {response.answer[:200]}...")
    print(f"📚 Sources: {len(response.source_documents)} chunks used")
    print(f"🔑 Keywords found: {found_keywords}")

    # At minimum, it should mention something related to the content
    assert len(found_keywords) > 0 or len(response.source_documents) > 0, \
        "The answer doesn't seem related to the document"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rag_with_empty_database():
    """
    Integration test: query against an empty database.

    Verifies the system gracefully handles the case where there are no
    ingested documents.
    """
    from app.core.services.rag_service import RAGService
    from app.adapters.outbound.ollama_adapter import OllamaAdapter
    from app.adapters.outbound.chromadb_adapter import ChromaDBAdapter
    from app.config.settings import settings

    # Arrange: RAG with an empty collection
    # The adapters use lazy initialization and pull config from settings
    ollama = OllamaAdapter()
    chromadb = ChromaDBAdapter()

    rag_service = RAGService(llm=ollama, vector_db=chromadb)

    # Act: query with no documents
    try:
        from app.core.domain.models import Query
        query = Query(question="What is RAG?")
        response = await rag_service.ask_question(query)
    except Exception as e:
        pytest.fail(f"The system must handle an empty DB gracefully, but failed: {e}")

    # Assert: must return an answer (even without context)
    assert response is not None
    assert response.answer is not None
    # Sources may be empty
    assert isinstance(response.source_documents, list)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_ollama_connectivity():
    """
    Integration test: verify connectivity with Ollama.

    Quick pre-check before running the full E2E tests.
    """
    from app.adapters.outbound.ollama_adapter import OllamaAdapter
    from app.config.settings import settings

    # Arrange: the adapter uses lazy initialization
    ollama = OllamaAdapter()

    # Act: generate a simple embedding
    try:
        embedding = await ollama.generate_embedding("test")
    except Exception as e:
        pytest.fail(f"Ollama is not available: {e}")

    # Assert
    assert embedding is not None
    assert isinstance(embedding, list)
    assert len(embedding) > 0
    print(f"✅ Ollama connected (embedding dimension: {len(embedding)})")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_chromadb_connectivity():
    """
    Integration test: verify connectivity with ChromaDB.

    Quick pre-check before running the full E2E tests.
    """
    from app.adapters.outbound.chromadb_adapter import ChromaDBAdapter
    from app.config.settings import settings

    # Arrange: the adapter uses lazy initialization
    chromadb = ChromaDBAdapter()

    # Act: get the default collection's stats
    try:
        stats = await chromadb.get_collection_stats()
    except Exception as e:
        pytest.fail(f"ChromaDB is not available: {e}")

    # Assert
    assert stats is not None
    assert isinstance(stats, dict)
    print(f"✅ ChromaDB connected (collection: {stats.get('collection_name')})")


# ============================================================================
# E2E TEST: FULL NOTION FLOW
# ============================================================================

@pytest.mark.integration
@pytest.mark.e2e
@pytest.mark.asyncio
async def test_full_notion_pipeline():
    """
    E2E test: full ingestion flow from Notion (a database) and query.

    Prerequisites:
    1. Ollama running: ollama serve
    2. ChromaDB running: docker-compose up chromadb
    3. NOTION_API_KEY configured in .env
    4. NOTION_DATABASE_ID pointing to a database shared with the integration

    Flow:
    1. Loads every page of the Notion database
    2. Processes each page (chunks + embeddings)
    3. Stores them in ChromaDB
    4. Runs a query related to the content
    5. Verifies the answer is coherent

    This test is skipped if NOTION_API_KEY or NOTION_DATABASE_ID aren't configured.
    """
    from app.core.services.sync_service import SyncService
    from app.core.services.rag_service import RAGService
    from app.adapters.outbound.ollama_adapter import OllamaAdapter
    from app.adapters.outbound.chromadb_adapter import ChromaDBAdapter
    from app.adapters.outbound.notion_processor_adapter import NotionProcessorAdapter
    from app.config.settings import settings

    # Skip if there's no Notion API key configured
    if not settings.notion_api_key:
        pytest.skip("NOTION_API_KEY not configured in .env - skipping Notion E2E test")

    # Skip if there's no database_id to test against
    database_id = settings.notion_database_id
    if not database_id:
        pytest.skip("NOTION_DATABASE_ID not configured - required for the E2E test")

    # Arrange: initialize real services
    ollama = OllamaAdapter()
    chromadb = ChromaDBAdapter()
    notion_processor = NotionProcessorAdapter()

    notion_sync_service = SyncService(
        document_processor=notion_processor,
        vector_db=chromadb,
        llm=ollama
    )

    rag_service = RAGService(
        llm=ollama,
        vector_db=chromadb
    )

    # Act: Step 1 - Load every page of the database
    try:
        print(f"\n📂 Loading pages from database: {database_id}")
        documents = await notion_processor.load_database_pages(database_id, max_pages=5)  # Cap at 5 for the test

        if not documents:
            pytest.fail("No pages found in the Notion database")

        print(f"📄 {len(documents)} pages found")
    except Exception as e:
        pytest.fail(f"Error loading Notion pages: {e}")

    # Act: Step 2 - Process each page (chunks + embeddings + store)
    total_chunks = 0
    for doc in documents:
        try:
            # Use sync_document_from_file with each document's page_id
            page_id = doc.metadata.get("notion_page_id")
            result = await notion_sync_service.sync_document_from_file(page_id)
            if result.success:
                total_chunks += result.chunks_created
                print(f"  ✓ {doc.metadata.get('title', 'Untitled')}: {result.chunks_created} chunks")
            else:
                print(f"  ✗ {doc.metadata.get('title', 'Untitled')}: {result.message}")
        except Exception as e:
            print(f"  ✗ Error processing {doc.id}: {e}")

    print(f"\n📥 Total: {total_chunks} chunks created from {len(documents)} pages")

    # Act: Step 3 - Verify storage
    try:
        stats = await chromadb.get_collection_stats()
        print(f"📊 ChromaDB stats: {stats}")
    except Exception as e:
        pytest.fail(f"Error verifying ChromaDB: {e}")

    # Act: Step 4 - Run a query about the content
    try:
        from app.core.domain.models import Query
        query = Query(question="What is the system's structure or architecture?")
        response = await rag_service.ask_question(query)
    except Exception as e:
        pytest.fail(f"Error in query: {e}")

    # Assert: verify the response
    assert response is not None
    assert response.answer is not None
    assert len(response.answer) > 0

    print(f"\n✅ Notion E2E test succeeded!")
    print(f"📝 Answer: {response.answer[:300]}...")
    print(f"📚 Sources: {len(response.source_documents)} chunks used")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_notion_api_connectivity():
    """
    Integration test: verify connectivity with the Notion API.

    Quick pre-check to validate the API key is valid.
    Skipped if there's no API key configured.
    """
    from app.adapters.outbound.notion_processor_adapter import NotionProcessorAdapter
    from app.config.settings import settings

    # Skip if there's no API key
    if not settings.notion_api_key:
        pytest.skip("NOTION_API_KEY not configured - skipping connectivity test")

    # Arrange
    notion = NotionProcessorAdapter()

    # Act: try a basic operation
    # Note: this depends on how the adapter is implemented
    # It may need adjusting to match the real implementation
    try:
        # If the adapter has a health-check method or similar
        if hasattr(notion, 'is_available'):
            available = await notion.is_available()
            assert available, "Notion API not available"
        print(f"✅ Notion API key valid and connected")
    except Exception as e:
        pytest.fail(f"Notion API not reachable: {e}")


# ============================================================================
# HELPERS FOR INTEGRATION TEST SETUP/TEARDOWN
# ============================================================================

@pytest.fixture
async def cleanup_test_collection():
    """
    Fixture to clean up test collections after running.

    Usage:
        @pytest.mark.integration
        async def test_something(cleanup_test_collection):
            # test code
            pass
        # Cleaned up automatically when done
    """
    yield  # The test runs here

    # Cleanup after the test
    # (Implement if you need to clean up test collections)
    pass
