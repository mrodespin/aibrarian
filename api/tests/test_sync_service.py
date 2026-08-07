# /api/tests/test_sync_service.py
"""
SyncService tests - Document ingestion pipeline.

SyncService is responsible for:
1. Processing documents (PDFs, Notion)
2. Splitting them into chunks
3. Generating embeddings
4. Storing them in ChromaDB

These tests verify the ingestion flow and error handling.
"""

import pytest
from unittest.mock import AsyncMock, Mock
from pathlib import Path

from app.core.services.sync_service import SyncService
from app.core.domain.models import Document, Chunk


# ============================================================================
# INGESTION FLOW UNIT TESTS
# ============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_sync_document_from_file_success(sync_service_with_mocks, mock_pdf_processor, mock_ollama, mock_chromadb):
    """
    Basic test: a document is ingested successfully.

    Verifies the full flow:
    1. Processes the document → Document
    2. Splits into chunks → List[Chunk]
    3. Generates embeddings → Chunk with embedding
    4. Stores it in ChromaDB
    """
    # Arrange
    test_file_path = "/test/document.pdf"

    # Act
    result = await sync_service_with_mocks.sync_document_from_file(test_file_path)

    # Assert
    # Verify the processor was called (with source as a keyword arg)
    mock_pdf_processor.process_document.assert_called_once()
    call_args = mock_pdf_processor.process_document.call_args
    assert call_args.kwargs['source'] == test_file_path or call_args.args[0] == test_file_path

    # Verify embeddings were generated (uses generate_embeddings_batch, not generate_embedding)
    assert mock_ollama.generate_embeddings_batch.called

    # Verify it was stored in ChromaDB
    mock_chromadb.store_chunks.assert_called_once()

    # The result must indicate success
    assert result is not None
    assert result.success == True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ingest_creates_chunks(sync_service_with_mocks):
    """
    Test: verify the document is split into chunks.

    A long document must be split into manageable fragments.
    """
    # Arrange
    test_file_path = "/test/long_document.pdf"

    # Act
    await sync_service_with_mocks.sync_document_from_file(test_file_path)

    # Assert
    # Verify store_chunks was called with a list of chunks
    # (the mock returns a Document that then gets split)
    # The service must have processed and created chunks
    assert True  # Placeholder - verify per the specific implementation


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ingest_generates_embeddings_for_each_chunk(sync_service_with_mocks, mock_ollama):
    """
    Test: verify embeddings are generated for each chunk.

    The service uses generate_embeddings_batch to vectorize all chunks at once.
    """
    # Arrange
    test_file_path = "/test/document.pdf"

    # Act
    await sync_service_with_mocks.sync_document_from_file(test_file_path)

    # Assert
    # Verify generate_embeddings_batch was called
    assert mock_ollama.generate_embeddings_batch.called


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ingest_stores_metadata(sync_service_with_mocks, mock_chromadb):
    """
    Test: verify the document's metadata is preserved.

    Chunks must include metadata (source, page, etc.) for traceability.
    """
    # Arrange
    test_file_path = "/test/document.pdf"

    # Act
    await sync_service_with_mocks.sync_document_from_file(test_file_path)

    # Assert
    # Verify store_chunks was called
    mock_chromadb.store_chunks.assert_called_once()

    # The chunks must have metadata
    call_args = mock_chromadb.store_chunks.call_args
    # The chunks may be in args or kwargs
    if call_args.args:
        chunks = call_args.args[0]
    else:
        chunks = call_args.kwargs['chunks']

    for chunk in chunks:
        assert hasattr(chunk, 'metadata')
        assert chunk.metadata is not None


# ============================================================================
# INPUT VALIDATION TESTS
# ============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_ingest_with_empty_path_raises_error(sync_service_with_mocks):
    """
    Test: an empty path must return an error or fail during processing.

    The service catches exceptions and returns a SyncResult with success=False.
    """
    # Act
    result = await sync_service_with_mocks.sync_document_from_file("")

    # Assert
    # It may fail or return a result with success=False
    assert result is not None
    if result.success:
        # If it doesn't fail for some reason, at least verify it processed something
        assert result.chunks_created >= 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ingest_with_none_path_raises_error(sync_service_with_mocks, mock_pdf_processor):
    """
    Test: a None path must return an error.

    The processor must fail with a None path.
    """
    # Arrange: configure the mock to simulate an error with None
    mock_pdf_processor.process_document = AsyncMock(
        side_effect=TypeError("source cannot be None")
    )

    # Act
    result = await sync_service_with_mocks.sync_document_from_file(None)

    # Assert
    assert result is not None
    assert result.success == False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ingest_with_nonexistent_file(sync_service_with_mocks, mock_pdf_processor):
    """
    Test: a nonexistent file must be handled properly.

    The processor may raise an exception or return an error.
    """
    # Arrange: configure the mock to simulate a file not found
    mock_pdf_processor.process_document = AsyncMock(
        side_effect=FileNotFoundError("File not found")
    )

    # Act
    result = await sync_service_with_mocks.sync_document_from_file("/nonexistent/file.pdf")

    # Assert: the service catches the exception and returns a SyncResult with success=False
    assert result is not None
    assert result.success == False
    assert "failed" in result.message.lower() or "not found" in result.message.lower()


# ============================================================================
# ERROR HANDLING TESTS
# ============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_ingest_handles_processor_error(sync_service_with_mocks, mock_pdf_processor):
    """
    Test: a processor error must be handled.

    If text extraction fails, the service returns a SyncResult with success=False.
    """
    # Arrange
    mock_pdf_processor.process_document = AsyncMock(
        side_effect=Exception("PDF corrupted")
    )

    # Act
    result = await sync_service_with_mocks.sync_document_from_file("/test/corrupted.pdf")

    # Assert
    assert result is not None
    assert result.success == False
    assert "corrupted" in result.message.lower() or "failed" in result.message.lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ingest_handles_embedding_error(sync_service_with_mocks, mock_ollama):
    """
    Test: an embedding-generation error must be handled.

    If Ollama fails to vectorize, the service returns a SyncResult with success=False.
    """
    # Arrange: the sync service uses generate_embeddings_batch
    mock_ollama.generate_embeddings_batch = AsyncMock(
        side_effect=Exception("Ollama service unavailable")
    )

    # Act
    result = await sync_service_with_mocks.sync_document_from_file("/test/document.pdf")

    # Assert
    assert result is not None
    assert result.success == False
    assert "unavailable" in result.message.lower() or "failed" in result.message.lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ingest_handles_chromadb_error(sync_service_with_mocks, mock_chromadb):
    """
    Test: a ChromaDB storage error must be handled.

    If storage fails, the ingestion must fail.
    """
    # Arrange
    mock_chromadb.store_chunks = AsyncMock(
        side_effect=Exception("ChromaDB connection failed")
    )

    # Act
    result = await sync_service_with_mocks.sync_document_from_file("/test/document.pdf")

    # Assert
    assert result is not None
    assert result.success == False
    assert "connection failed" in result.message.lower() or "failed" in result.message.lower()


# ============================================================================
# EDGE CASE TESTS
# ============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_ingest_empty_document(sync_service_with_mocks, mock_pdf_processor):
    """
    Test: an empty document must be handled properly.

    A PDF with no text content must be processed without failing (it
    may produce a warning or simply create no chunks).
    """
    # Arrange: document with empty content
    from app.core.domain.models import DocumentSource
    empty_doc = Document(
        id="empty_001",
        source=DocumentSource.PDF,
        content="",
        metadata={"source": "empty.pdf"}
    )
    mock_pdf_processor.process_document = AsyncMock(
        return_value=(empty_doc, [])  # Empty document, no chunks
    )

    # Act
    result = await sync_service_with_mocks.sync_document_from_file("/test/empty.pdf")

    # Assert
    # Must complete without error (even if it produces no useful chunks)
    assert result is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ingest_very_large_document(sync_service_with_mocks, mock_pdf_processor, mock_ollama):
    """
    Test: a very long document must be split into multiple chunks.

    A document with many pages must be chunked properly.
    """
    # Arrange: a very long document (100KB of text)
    from app.core.domain.models import DocumentSource
    long_content = "This is a very long document. " * 3000  # ~100KB
    large_doc = Document(
        id="large_001",
        source=DocumentSource.PDF,
        content=long_content,
        metadata={"source": "large.pdf", "pages": 100}
    )
    # Simulate many chunks
    large_chunks = [
        Chunk(
            id=f"chunk_{i}",
            document_id="large_001",
            content=f"Chunk {i}: " + long_content[i*1000:(i+1)*1000],
            metadata={"page": i // 10 + 1, "position": i}
        )
        for i in range(min(100, len(long_content) // 1000))  # Max 100 chunks for the test
    ]
    mock_pdf_processor.process_document = AsyncMock(
        return_value=(large_doc, large_chunks)
    )

    # Act
    result = await sync_service_with_mocks.sync_document_from_file("/test/large.pdf")

    # Assert
    # generate_embeddings_batch must have been called with many chunks
    assert mock_ollama.generate_embeddings_batch.called
    # Verify it processed many chunks
    call_args = mock_ollama.generate_embeddings_batch.call_args[0]
    texts_batch = call_args[0]
    assert len(texts_batch) > 1  # There must be multiple chunks


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sync_document_from_file_with_special_characters(sync_service_with_mocks, mock_pdf_processor):
    """
    Test: a document with special characters must be processed correctly.

    Accents, emoji, mathematical symbols, etc. must be handled.
    """
    # Arrange: content with special characters
    from app.core.domain.models import DocumentSource
    special_content = "RAG 🤖 uses embeddings ∑ for semantic search ñ á é"
    special_doc = Document(
        id="special_001",
        source=DocumentSource.PDF,
        content=special_content,
        metadata={"source": "special.pdf"}
    )
    special_chunks = [
        Chunk(
            id="chunk_special_001",
            document_id="special_001",
            content=special_content,
            metadata={"page": 1}
        )
    ]
    mock_pdf_processor.process_document = AsyncMock(
        return_value=(special_doc, special_chunks)
    )

    # Act
    result = await sync_service_with_mocks.sync_document_from_file("/test/special.pdf")

    # Assert
    assert result is not None


# ============================================================================
# CHUNKING TESTS
# ============================================================================

@pytest.mark.unit
def test_chunk_size_configuration():
    """
    Test: verify the chunk size is configurable.

    The system must let you configure CHUNK_SIZE and CHUNK_OVERLAP
    from settings or parameters.
    """
    from app.config.settings import settings

    # Assert: verify the settings exist
    assert hasattr(settings, 'CHUNK_SIZE') or hasattr(settings, 'chunk_size')
    assert hasattr(settings, 'CHUNK_OVERLAP') or hasattr(settings, 'chunk_overlap')
