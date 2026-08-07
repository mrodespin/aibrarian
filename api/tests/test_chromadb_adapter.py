# /api/tests/test_chromadb_adapter.py
"""
Unit tests for ChromaDBAdapter.list_documents().

There was no test file for ChromaDBAdapter's own logic (only for
ChromaCloudAdapter, which reuses all of this logic and only changes
_get_client — see test_chromadb_cloud_adapter.py). Here,
_get_or_create_collection() is mocked directly instead of the full HTTP
client, because list_documents() is pure processing of whatever
collection.get() returns — no need to simulate the transport layer.
"""

import pytest
from unittest.mock import MagicMock, patch

from app.adapters.outbound.chromadb_adapter import ChromaDBAdapter


def _mock_collection(ids, metadatas):
    """Creates a fake collection whose .get() returns ChromaDB's shape."""
    collection = MagicMock()
    collection.get.return_value = {"ids": ids, "metadatas": metadatas}
    return collection


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_documents_groups_chunks_by_document_id():
    """3 chunks from 2 distinct documents → 2 DocumentSummary with the right chunk_count."""
    adapter = ChromaDBAdapter()
    collection = _mock_collection(
        ids=["notion_a_chunk_0", "notion_a_chunk_1", "pdf_b_chunk_0"],
        metadatas=[
            {"document_id": "notion_a", "title": "1984"},
            {"document_id": "notion_a", "title": "1984"},
            {"document_id": "pdf_b", "filename": "manual.pdf"},
        ],
    )

    with patch.object(adapter, "_get_or_create_collection", return_value=collection):
        summaries = await adapter.list_documents("docs")

    by_id = {s.document_id: s for s in summaries}
    assert len(summaries) == 2
    assert by_id["notion_a"].chunk_count == 2
    assert by_id["notion_a"].title == "1984"
    assert by_id["notion_a"].source == "notion"
    assert by_id["pdf_b"].chunk_count == 1
    assert by_id["pdf_b"].title == "manual.pdf"
    assert by_id["pdf_b"].source == "pdf"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_documents_falls_back_to_filename_when_title_is_untitled():
    """"Untitled" title (a _extract_title bug already fixed, but just in case) falls back to filename."""
    adapter = ChromaDBAdapter()
    collection = _mock_collection(
        ids=["notion_x_chunk_0"],
        metadatas=[{"document_id": "notion_x", "title": "Untitled", "filename": "fallback.pdf"}],
    )

    with patch.object(adapter, "_get_or_create_collection", return_value=collection):
        summaries = await adapter.list_documents("docs")

    assert summaries[0].title == "fallback.pdf"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_documents_falls_back_to_document_id_when_no_title_or_filename():
    adapter = ChromaDBAdapter()
    collection = _mock_collection(
        ids=["notion_y_chunk_0"],
        metadatas=[{"document_id": "notion_y"}],
    )

    with patch.object(adapter, "_get_or_create_collection", return_value=collection):
        summaries = await adapter.list_documents("docs")

    assert summaries[0].title == "notion_y"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_documents_sorted_alphabetically_by_title():
    adapter = ChromaDBAdapter()
    collection = _mock_collection(
        ids=["notion_z_chunk_0", "notion_a_chunk_0"],
        metadatas=[
            {"document_id": "notion_z", "title": "Zorba the Greek"},
            {"document_id": "notion_a", "title": "1984"},
        ],
    )

    with patch.object(adapter, "_get_or_create_collection", return_value=collection):
        summaries = await adapter.list_documents("docs")

    assert [s.title for s in summaries] == ["1984", "Zorba the Greek"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_documents_empty_collection_returns_empty_list():
    adapter = ChromaDBAdapter()
    collection = _mock_collection(ids=[], metadatas=[])

    with patch.object(adapter, "_get_or_create_collection", return_value=collection):
        summaries = await adapter.list_documents("docs")

    assert summaries == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_documents_returns_empty_list_on_error():
    """Same contract as get_collection_stats/similarity_search: never raises, degrades to empty."""
    adapter = ChromaDBAdapter()

    with patch.object(adapter, "_get_or_create_collection", side_effect=RuntimeError("boom")):
        summaries = await adapter.list_documents("docs")

    assert summaries == []
