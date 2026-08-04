# /api/tests/test_chromadb_adapter.py
"""
Tests unitarios de ChromaDBAdapter.list_documents().

No existía un test file para la lógica propia de ChromaDBAdapter (solo
para ChromaCloudAdapter, que reutiliza toda esta lógica y solo cambia
_get_client — ver test_chromadb_cloud_adapter.py). Aquí se mockea
_get_or_create_collection() directamente en vez del cliente HTTP completo,
porque list_documents() es puro procesamiento de lo que devuelve
collection.get() — no hace falta simular la capa de transporte.
"""

import pytest
from unittest.mock import MagicMock, patch

from app.adapters.outbound.chromadb_adapter import ChromaDBAdapter


def _mock_collection(ids, metadatas):
    """Crea una colección falsa cuyo .get() devuelve el shape de ChromaDB."""
    collection = MagicMock()
    collection.get.return_value = {"ids": ids, "metadatas": metadatas}
    return collection


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_documents_groups_chunks_by_document_id():
    """3 chunks de 2 documentos distintos → 2 DocumentSummary con chunk_count correcto."""
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
    """Título "Untitled" (bug de _extract_title ya arreglado, pero por si acaso) usa filename."""
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
            {"document_id": "notion_z", "title": "Zorba el Griego"},
            {"document_id": "notion_a", "title": "1984"},
        ],
    )

    with patch.object(adapter, "_get_or_create_collection", return_value=collection):
        summaries = await adapter.list_documents("docs")

    assert [s.title for s in summaries] == ["1984", "Zorba el Griego"]


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
    """Mismo contrato que get_collection_stats/similarity_search: nunca lanza, degrada a vacío."""
    adapter = ChromaDBAdapter()

    with patch.object(adapter, "_get_or_create_collection", side_effect=RuntimeError("boom")):
        summaries = await adapter.list_documents("docs")

    assert summaries == []
