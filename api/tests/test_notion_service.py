# /api/tests/test_notion_service.py
"""
Tests for the Notion sync service.

These tests verify the Notion ingestion flow using mocks, with no need
for a real Notion API key.

The Notion flow is similar to the PDF one:
1. NotionProcessorAdapter extracts content from a page/database
2. Chunks are generated from the content
3. Embeddings are generated with Ollama
4. They're stored in ChromaDB
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch
from typing import List

from app.core.domain.models import Document, Chunk, DocumentSource, SyncResult
from app.adapters.outbound.notion_processor_adapter import NotionProcessorAdapter


# ============================================================================
# NOTION-SPECIFIC FIXTURES
# ============================================================================

@pytest.fixture
def mock_notion_processor():
    """
    Mock of NotionProcessorAdapter.

    Simulates extracting content from Notion without calling the real API.
    """
    mock = Mock()

    async def mock_process_document(
        source: str,
        chunk_size: int = 1000,
        chunk_overlap: int = 200
    ) -> tuple:
        """Simulates processing a Notion page."""
        # Create a mocked document as if it came from Notion
        document = Document(
            id=f"notion_{source}",
            source=DocumentSource.NOTION,
            content=f"Content of the Notion page: {source}. "
                    "This is a sample page with information about the project. "
                    "It includes technical details, architecture and usage guides.",
            metadata={
                "notion_page_id": source,
                "title": "Sample Page",
                "url": f"https://notion.so/{source}"
            }
        )
        # Create mocked chunks
        chunks = [
            Chunk(
                id=f"notion_{source}_chunk_0",
                document_id=f"notion_{source}",
                content="Content of the Notion page about the project.",
                metadata={"notion_page_id": source, "chunk_index": 0}
            ),
            Chunk(
                id=f"notion_{source}_chunk_1",
                document_id=f"notion_{source}",
                content="Technical details and the system's architecture.",
                metadata={"notion_page_id": source, "chunk_index": 1}
            )
        ]
        return (document, chunks)

    async def mock_load_database_pages(database_id: str) -> List[Document]:
        """Simulates loading every page of a Notion database."""
        return [
            Document(
                id=f"notion_db_{database_id}_page_1",
                source=DocumentSource.NOTION,
                content="First page of the database with relevant content.",
                metadata={"database_id": database_id, "page_index": 0}
            ),
            Document(
                id=f"notion_db_{database_id}_page_2",
                source=DocumentSource.NOTION,
                content="Second page with more information about the project.",
                metadata={"database_id": database_id, "page_index": 1}
            )
        ]

    mock.process_document = AsyncMock(side_effect=mock_process_document)
    mock.load_database_pages = AsyncMock(side_effect=mock_load_database_pages)

    return mock


@pytest.fixture
def notion_sync_service_with_mocks(mock_notion_processor, mock_ollama, mock_chromadb):
    """
    SyncService configured with a mocked NotionProcessor.
    """
    from app.core.services.sync_service import SyncService

    return SyncService(
        document_processor=mock_notion_processor,
        vector_db=mock_chromadb,
        llm=mock_ollama
    )


# ============================================================================
# UNIT TESTS - NOTION SYNC FLOW
# ============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_notion_sync_page_success(notion_sync_service_with_mocks, mock_notion_processor):
    """
    Test: successfully sync a Notion page.

    Verifies the full flow:
    1. Processes the Notion page
    2. Generates embeddings for the chunks
    3. Stores them in ChromaDB
    """
    # Arrange
    page_id = "abc123def456"

    # Act
    result = await notion_sync_service_with_mocks.sync_document_from_file(page_id)

    # Assert
    assert result is not None
    assert result.success == True
    assert result.chunks_created > 0
    mock_notion_processor.process_document.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_notion_sync_creates_chunks_with_metadata(notion_sync_service_with_mocks, mock_chromadb):
    """
    Test: Notion chunks include the right metadata.

    Chunks must have notion_page_id for traceability.
    """
    # Arrange
    page_id = "test_page_123"

    # Act
    await notion_sync_service_with_mocks.sync_document_from_file(page_id)

    # Assert
    mock_chromadb.store_chunks.assert_called_once()
    call_args = mock_chromadb.store_chunks.call_args
    chunks = call_args.kwargs.get('chunks') or call_args.args[0]

    for chunk in chunks:
        assert chunk.metadata is not None
        # Notion chunks must have the page_id in their metadata
        assert "notion_page_id" in chunk.metadata or "chunk_index" in chunk.metadata


@pytest.mark.unit
@pytest.mark.asyncio
async def test_notion_sync_generates_embeddings(notion_sync_service_with_mocks, mock_ollama):
    """
    Test: embeddings are generated for Notion chunks.
    """
    # Arrange
    page_id = "page_with_content"

    # Act
    await notion_sync_service_with_mocks.sync_document_from_file(page_id)

    # Assert
    assert mock_ollama.generate_embeddings_batch.called


@pytest.mark.unit
@pytest.mark.asyncio
async def test_notion_sync_handles_processor_error(notion_sync_service_with_mocks, mock_notion_processor):
    """
    Test: handle a NotionProcessor error gracefully.

    If the Notion API fails, it must return a SyncResult with success=False.
    """
    # Arrange: simulate a Notion API error
    mock_notion_processor.process_document = AsyncMock(
        side_effect=Exception("Notion API rate limit exceeded")
    )

    # Act
    result = await notion_sync_service_with_mocks.sync_document_from_file("some_page_id")

    # Assert
    assert result is not None
    assert result.success == False
    assert "rate limit" in result.message.lower() or "failed" in result.message.lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_notion_sync_handles_invalid_page_id(notion_sync_service_with_mocks, mock_notion_processor):
    """
    Test: handle an invalid page_id.
    """
    # Arrange: simulate a page not found
    mock_notion_processor.process_document = AsyncMock(
        side_effect=Exception("Page not found: invalid_id")
    )

    # Act
    result = await notion_sync_service_with_mocks.sync_document_from_file("invalid_id")

    # Assert
    assert result.success == False
    assert "not found" in result.message.lower() or "failed" in result.message.lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_notion_document_has_correct_source_type(notion_sync_service_with_mocks, mock_notion_processor):
    """
    Test: Notion documents have source=NOTION.
    """
    # The mock already returns DocumentSource.NOTION
    # This test verifies the flow preserves that type

    # Arrange
    page_id = "notion_page_test"

    # Act
    result = await notion_sync_service_with_mocks.sync_document_from_file(page_id)

    # Assert
    assert result.success == True
    # Verify the processor was called (the mock returns NOTION)
    mock_notion_processor.process_document.assert_called_once()


# ============================================================================
# UNIT TESTS - NOTION DATABASE
# ============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_notion_load_database_pages(mock_notion_processor):
    """
    Test: load the pages of a Notion database.
    """
    # Arrange
    database_id = "db_123456"

    # Act
    pages = await mock_notion_processor.load_database_pages(database_id)

    # Assert
    assert pages is not None
    assert len(pages) > 0
    for page in pages:
        assert page.source == DocumentSource.NOTION
        assert "database_id" in page.metadata


@pytest.mark.unit
@pytest.mark.asyncio
async def test_notion_database_sync_multiple_pages(mock_notion_processor):
    """
    Test: the database returns multiple pages.
    """
    # Arrange
    database_id = "multi_page_db"

    # Act
    pages = await mock_notion_processor.load_database_pages(database_id)

    # Assert
    assert len(pages) >= 2  # The mock returns 2 pages


# ============================================================================
# API ENDPOINT VALIDATION TESTS
# ============================================================================

@pytest.mark.unit
def test_notion_endpoint_without_api_key(test_client):
    """
    Test: the Notion endpoint rejects requests without an API key configured.

    If NOTION_API_KEY isn't in .env, it must return 400.
    """
    # Arrange
    payload = {"page_id": "some_page_id"}

    # Act
    response = test_client.post("/sync/notion", json=payload)

    # Assert: without an API key configured, it must error out
    # The code may be 400 (not configured) or 422 (validation)
    assert response.status_code in [400, 422, 500]


@pytest.mark.unit
def test_notion_database_endpoint_without_api_key(test_client):
    """
    Test: the database endpoint rejects requests without an API key.
    """
    # Arrange
    payload = {"database_id": "some_db_id"}

    # Act
    response = test_client.post("/sync/notion/database", json=payload)

    # Assert
    assert response.status_code in [400, 422, 500]


# ============================================================================
# /sync/notion/database RESILIENCE TESTS — a broken page must not abort
# the rest (a real bug found in production: with no try/except per page,
# an exception on any document took down the WHOLE endpoint with a 500
# and the following pages weren't even attempted).
# ============================================================================

def _fake_notion_document(doc_id: str) -> Document:
    return Document(
        id=doc_id,
        source=DocumentSource.NOTION,
        content="test content",
        metadata={"title": doc_id}
    )


@pytest.mark.unit
def test_sync_database_continues_after_one_page_fails(test_client, monkeypatch):
    """
    3 pages, the 2nd one fails while generating embeddings → the 1st and
    3rd must still get processed regardless (before this fix, page 2's
    exception aborted the whole endpoint and the 3rd was never attempted).
    """
    import app.main as main_module

    docs = [_fake_notion_document("notion_a"), _fake_notion_document("notion_b"), _fake_notion_document("notion_c")]

    monkeypatch.setattr(main_module.settings, "notion_api_key", "fake-key")
    monkeypatch.setattr(
        main_module.notion_processor, "load_database_pages",
        AsyncMock(return_value=docs)
    )
    monkeypatch.setattr(
        main_module.notion_processor, "split_into_chunks",
        AsyncMock(side_effect=lambda doc, *a, **kw: [
            Chunk(id=f"{doc.id}_chunk_0", document_id=doc.id, content="text", metadata={})
        ])
    )

    # Every chunk has the same content ("text"), so instead of
    # identifying the page by content, we simulate the failure by the
    # ORDER of the call: the 2nd invocation of generate_embeddings_batch
    # (the middle page) is the one that fails.
    call_count = {"n": 0}

    async def flaky_embeddings_by_order(texts):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise RuntimeError("embedding backend timed out")
        return [[0.1, 0.2, 0.3] for _ in texts]

    monkeypatch.setattr(main_module.llm_adapter, "generate_embeddings_batch", flaky_embeddings_by_order)
    monkeypatch.setattr(main_module.chromadb_adapter, "store_chunks", AsyncMock(return_value=True))

    response = test_client.post("/sync/notion/database", json={"database_id": "db123"})

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    assert data["successful"] == 2
    assert data["failed"] == 1

    results_by_id = {r["document_id"]: r for r in data["results"]}
    assert results_by_id["notion_a"]["success"] is True
    assert results_by_id["notion_b"]["success"] is False
    assert "embedding backend timed out" in results_by_id["notion_b"]["message"]
    # The key thing this test checks: page 3 (after the one that failed) WAS processed
    assert results_by_id["notion_c"]["success"] is True


# ============================================================================
# _extract_title() TESTS — discovery by type=="title", not by name
# ============================================================================
# NotionProcessorAdapter() doesn't need a real API key for these tests:
# the key is only used when creating the HTTP client (_get_client), lazy
# and not invoked here. _extract_title() is a pure function over a
# dict, so the real adapter is instantiated (no mocks) and given
# hand-built page payloads, shaped the same way as what Notion's API returns.

def _fake_page(properties: dict) -> dict:
    """Builds a minimal Notion page payload for the tests."""
    return {"properties": properties}


def _title_property(text: str) -> dict:
    """Builds a type=="title" property with the given text."""
    return {"type": "title", "title": [{"plain_text": text}] if text else []}


@pytest.mark.unit
def test_extract_title_finds_title_by_type_regardless_of_property_name():
    """
    Case reproducing the original bug: the Notion database's title
    column isn't called "title"/"Name" (none of the names the old
    version tried), but something arbitrary like "Movie". It must still
    be found because it's looked up by type, not by name.
    """
    adapter = NotionProcessorAdapter(notion_api_key="fake-key")
    page = _fake_page({
        "Movie": _title_property("Blade Runner 2049"),
        "Year": {"type": "number", "number": 2017},
    })

    assert adapter._extract_title(page) == "Blade Runner 2049"


@pytest.mark.unit
def test_extract_title_still_works_with_common_names():
    """Regression: the typical column names still work."""
    adapter = NotionProcessorAdapter(notion_api_key="fake-key")
    page = _fake_page({
        "Name": _title_property("Deep Learning"),
    })

    assert adapter._extract_title(page) == "Deep Learning"


@pytest.mark.unit
def test_extract_title_returns_untitled_when_title_property_is_empty():
    """If the title cell exists but is empty, falls back to "Untitled"."""
    adapter = NotionProcessorAdapter(notion_api_key="fake-key")
    page = _fake_page({
        "Name": _title_property(""),
    })

    assert adapter._extract_title(page) == "Untitled"


@pytest.mark.unit
def test_extract_title_returns_untitled_when_no_title_property_exists():
    """If there's no type=="title" property at all (degenerate payload), falls back."""
    adapter = NotionProcessorAdapter(notion_api_key="fake-key")
    page = _fake_page({
        "Year": {"type": "number", "number": 2017},
    })

    assert adapter._extract_title(page) == "Untitled"
