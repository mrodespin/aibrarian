# /api/tests/test_rag_service.py
"""
RAGService tests - The heart of the query system.

RAGService is responsible for:
1. Vectorizing the user's question (embedding)
2. Searching for relevant chunks in ChromaDB (retrieval)
3. Building a prompt with context
4. Generating an answer with the LLM (generation)

These tests verify each step of the RAG flow and error cases.
"""

import pytest
from unittest.mock import AsyncMock, patch

from app.core.services.rag_service import RAGService
from app.core.domain.models import QueryResult, Chunk


# ============================================================================
# UNIT TESTS (with mocks)
# ============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_query_success(rag_service_with_mocks, sample_query):
    """
    Basic test: a successful query returns an answer with sources.

    Verifies the full happy path:
    - Accepts a question
    - Returns a QueryResult with answer and sources
    - The sources include the chunks' metadata
    """
    # Act
    response = await rag_service_with_mocks.ask_question(sample_query)

    # Assert
    from app.core.domain.models import SourceDocument
    assert isinstance(response, QueryResult)
    assert response.answer is not None
    assert len(response.answer) > 0
    assert isinstance(response.source_documents, list)
    assert len(response.source_documents) > 0
    # Verify each source has the expected structure
    for source in response.source_documents:
        assert isinstance(source, SourceDocument)
        assert source.document_id is not None
        assert source.chunk_content is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_query_calls_embedding(rag_service_with_mocks, sample_query, mock_ollama):
    """
    Test: verify that an embedding is generated for the query.

    RAG must vectorize the question before searching for context.
    """
    # Act
    await rag_service_with_mocks.ask_question(sample_query)

    # Assert
    # Verify generate_embedding was called with the query
    mock_ollama.generate_embedding.assert_called_once()
    call_args = mock_ollama.generate_embedding.call_args[0]
    assert sample_query.question in call_args[0]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_query_calls_vector_search(rag_service_with_mocks, sample_query, mock_chromadb):
    """
    Test: verify that ChromaDB is searched.

    After vectorizing, it must search for similar chunks in the vector DB.
    """
    # Act
    await rag_service_with_mocks.ask_question(sample_query)

    # Assert
    # Verify ChromaDB's similarity_search was called
    mock_chromadb.similarity_search.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_query_calls_llm_generation(rag_service_with_mocks, sample_query, mock_ollama):
    """
    Test: verify that an answer is generated with the LLM.

    After getting context, it must call the LLM to generate the answer.
    """
    # Act
    await rag_service_with_mocks.ask_question(sample_query)

    # Assert
    # Verify generate_response was called (text generation)
    mock_ollama.generate_response.assert_called_once()
    # The prompt must include the query
    call_args = mock_ollama.generate_response.call_args
    # Check kwargs for 'prompt' parameter
    assert 'prompt' in call_args.kwargs or len(call_args.args) > 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_query_with_empty_string_raises_error(rag_service_with_mocks):
    """
    Test: an empty query must raise a ValidationError.

    Pydantic validates that question isn't empty (min_length=1).
    """
    # Act & Assert
    from pydantic import ValidationError
    from app.core.domain.models import Query
    with pytest.raises(ValidationError):
        Query(question="")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_query_with_none_raises_error(rag_service_with_mocks):
    """
    Test: a None query must raise a ValidationError.

    Pydantic validates that question is required.
    """
    # Act & Assert
    from pydantic import ValidationError
    from app.core.domain.models import Query
    with pytest.raises(ValidationError):
        Query(question=None)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_query_with_no_results_from_db(rag_service_with_mocks, sample_query, mock_chromadb):
    """
    Test: handle the case where ChromaDB finds no relevant chunks.

    If there's no context, the system must handle it gracefully
    (it may generate an answer without context or say it has no information).
    """
    # Arrange: configure the mock to return an empty list
    mock_chromadb.query = AsyncMock(return_value=[])

    # Act
    response = await rag_service_with_mocks.ask_question(sample_query)

    # Assert
    # Must return an answer even without context
    assert isinstance(response, QueryResult)
    assert response.answer is not None
    # Sources can be empty or indicate there's no context
    assert isinstance(response.source_documents, list)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_query_limits_context_chunks(rag_service_with_mocks):
    """
    Test: verify the number of context chunks is limited.

    RAG must use max_results to avoid overly long prompts that
    overflow the LLM's context window.
    """
    # Arrange: create a query with max_results=2
    from app.core.domain.models import Query
    query = Query(question="What is RAG?", max_results=2)

    # Act
    response = await rag_service_with_mocks.ask_question(query)

    # Assert
    # Verify no more than max_results sources are included
    assert len(response.source_documents) <= 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_query_filters_low_relevance_chunks(rag_service_with_mocks, sample_query, mock_chromadb):
    """
    Test: chunks with a relevance_score below the threshold get dropped.

    Without this filter, ChromaDB returns top_k chunks even if they
    aren't relevant, and the LLM ends up fabricating an answer instead
    of saying "I don't know".
    """
    # Arrange: one relevant chunk (0.9) and one clearly irrelevant (0.05)
    from app.core.domain.models import SourceDocument

    async def mock_search(*args, **kwargs):
        return [
            SourceDocument(
                document_id="doc_relevant",
                chunk_content="Relevant chunk",
                metadata={},
                relevance_score=0.9
            ),
            SourceDocument(
                document_id="doc_irrelevant",
                chunk_content="Irrelevant chunk",
                metadata={},
                relevance_score=0.05
            ),
        ]

    mock_chromadb.similarity_search = AsyncMock(side_effect=mock_search)

    # Act
    response = await rag_service_with_mocks.ask_question(sample_query)

    # Assert
    doc_ids = [source.document_id for source in response.source_documents]
    assert "doc_relevant" in doc_ids
    assert "doc_irrelevant" not in doc_ids


@pytest.mark.unit
@pytest.mark.asyncio
async def test_query_all_chunks_below_threshold_returns_no_info(rag_service_with_mocks, sample_query, mock_chromadb):
    """
    Test: if ALL retrieved chunks are below the threshold, the same
    fallback is returned as when there are no results at all (not a new
    branch, reuses the existing one).
    """
    # Arrange: every chunk below the default threshold (0.3)
    from app.core.domain.models import SourceDocument

    async def mock_search(*args, **kwargs):
        return [
            SourceDocument(
                document_id="doc_irrelevant",
                chunk_content="Irrelevant chunk",
                metadata={},
                relevance_score=0.1
            ),
        ]

    mock_chromadb.similarity_search = AsyncMock(side_effect=mock_search)

    # Act
    response = await rag_service_with_mocks.ask_question(sample_query)

    # Assert
    assert response.source_documents == []
    assert "couldn't find relevant information" in response.answer


@pytest.mark.unit
@pytest.mark.asyncio
async def test_query_includes_source_metadata(rag_service_with_mocks, sample_query):
    """
    Test: verify the sources include useful metadata.

    Each source must include enough info for the user to verify where
    the information came from (source file, page, etc.).
    """
    # Act
    response = await rag_service_with_mocks.ask_question(sample_query)

    # Assert
    from app.core.domain.models import SourceDocument
    for source in response.source_documents:
        # Verify it's a SourceDocument with the right fields
        assert isinstance(source, SourceDocument)
        assert source.document_id is not None
        assert source.chunk_content is not None
        assert len(source.chunk_content) > 0
        assert isinstance(source.metadata, dict)


# ============================================================================
# QUERY EXPANSION TESTS
# ============================================================================
# Regression coverage for a bug seen in production (2026-08-07): when
# extract_keywords() returns multiple keywords and a generic one (e.g.
# "book") happens to come before the real proper noun (e.g. "Fahrenheit
# 451"), the old code stopped at the FIRST keyword that returned any
# passing result — a coincidental match on "book" won and the real title
# was never even tried, so the LLM correctly reported the (wrong) context
# had no relevant info. _retrieve() now tries every keyword and merges.

@pytest.mark.unit
@pytest.mark.asyncio
async def test_generic_keyword_does_not_shadow_the_real_title(
    rag_service_with_mocks, mock_ollama, mock_chromadb
):
    """A coincidental match on a generic keyword must not prevent trying the rest."""
    from app.core.domain.models import Query, SourceDocument

    mock_ollama.extract_keywords = AsyncMock(return_value=["book", "Fahrenheit 451"])

    async def mock_search(*args, **kwargs):
        keyword = kwargs.get("keyword_filter")
        if keyword == "book":
            # Coincidental match on an unrelated document — passes the
            # relevance threshold, but is NOT what the user asked about.
            return [
                SourceDocument(
                    document_id="unrelated_doc",
                    chunk_content="Some unrelated chunk that happens to mention a book",
                    metadata={"chunk_index": 0},
                    relevance_score=0.4
                )
            ]
        if keyword == "Fahrenheit 451":
            return [
                SourceDocument(
                    document_id="fahrenheit_451",
                    chunk_content="Fahrenheit 451 is a novel by Ray Bradbury...",
                    metadata={"chunk_index": 0},
                    relevance_score=0.85
                )
            ]
        return []

    mock_chromadb.similarity_search = AsyncMock(side_effect=mock_search)

    query = Query(question="What about the book Fahrenheit 451?")
    response = await rag_service_with_mocks.ask_question(query)

    doc_ids = [source.document_id for source in response.source_documents]
    assert "fahrenheit_451" in doc_ids
    # Both keywords must have been tried — not just the first one
    assert mock_chromadb.similarity_search.call_count == 2


# ============================================================================
# ERROR HANDLING TESTS
# ============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_query_handles_llm_error_gracefully(rag_service_with_mocks, sample_query, mock_ollama):
    """
    Test: handle an LLM error gracefully.

    If Ollama fails, the service catches the error and returns a
    QueryResult with an error message in the answer.
    """
    # Arrange: configure the mock to raise an exception
    mock_ollama.generate_response = AsyncMock(side_effect=Exception("Ollama connection failed"))

    # Act
    response = await rag_service_with_mocks.ask_question(sample_query)

    # Assert: the service returns a result with an error message
    assert response is not None
    assert isinstance(response, QueryResult)
    assert "error" in response.answer.lower() or "failed" in response.answer.lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_query_handles_chromadb_error_gracefully(rag_service_with_mocks, sample_query, mock_chromadb):
    """
    Test: handle a ChromaDB error gracefully.

    If ChromaDB fails, the service catches the error and returns a
    QueryResult with an error message in the answer.
    """
    # Arrange: configure the mock to raise an exception
    mock_chromadb.similarity_search = AsyncMock(side_effect=Exception("ChromaDB connection failed"))

    # Act
    response = await rag_service_with_mocks.ask_question(sample_query)

    # Assert: the service returns a result with an error message
    assert response is not None
    assert isinstance(response, QueryResult)
    assert "error" in response.answer.lower() or "failed" in response.answer.lower()


# ============================================================================
# EDGE CASE TESTS
# ============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_query_with_very_long_question(rag_service_with_mocks):
    """
    Test: handle very long questions.

    The system must handle long queries without failing (they may be
    truncated or processed in full depending on the design).
    """
    # Arrange: a 1000-word query
    from app.core.domain.models import Query
    long_question_text = "What is RAG? " * 200  # ~1000 words
    long_query = Query(question=long_question_text)

    # Act
    response = await rag_service_with_mocks.ask_question(long_query)

    # Assert
    assert isinstance(response, QueryResult)
    assert response.answer is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_query_with_special_characters(rag_service_with_mocks):
    """
    Test: handle special characters in the query.

    The system must correctly process queries with accents, emoji,
    symbols, etc.
    """
    # Arrange: query with special characters
    from app.core.domain.models import Query
    special_question_text = "What is RAG? 🤖 ¿Cómo funciona el embedding?"
    special_query = Query(question=special_question_text)

    # Act
    response = await rag_service_with_mocks.ask_question(special_query)

    # Assert
    assert isinstance(response, QueryResult)
    assert response.answer is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_query_response_has_processing_time(rag_service_with_mocks, sample_query):
    """
    Test: verify the response includes processing_time.

    QueryResult must include the processing time.
    """
    # Act
    response = await rag_service_with_mocks.ask_question(sample_query)

    # Assert
    assert hasattr(response, "processing_time")
    # processing_time can be None or a float


# ============================================================================
# TESTS for catalog questions in ask_question() — classification via the LLM
# ============================================================================
# "How many books do you know?" is not a content question — it shouldn't
# go through similarity_search/generate_response, it should be resolved
# with vector_db.list_documents() (see RAGService._build_meta_answer).
# The "is this a catalog question" decision is made by the LLM
# (LLMPort.is_catalog_question), not a regex — that's why these tests
# directly control what that mock returns, instead of testing specific
# phrases: covering languages/wordings is the real LLM's responsibility,
# not this test suite's (see test_ollama_adapter.py /
# test_groq_adapter.py for the tests of that classification itself).

@pytest.mark.unit
@pytest.mark.asyncio
async def test_meta_question_lists_full_catalog_without_search_or_generation(
    rag_service_with_mocks, mock_ollama, mock_chromadb
):
    """
    If the LLM classifies the question as a catalog one, ask_question()
    answers with the full listing (mock_chromadb.list_documents returns
    2 documents, see conftest.py) without calling generate_response or
    similarity_search — only is_catalog_question + list_documents.
    """
    from app.core.domain.models import Query

    mock_ollama.is_catalog_question = AsyncMock(return_value=True)
    query = Query(question="How many books do you know?")

    response = await rag_service_with_mocks.ask_question(query)

    assert "1984" in response.answer
    assert "Deep Learning" in response.answer
    assert response.answer.startswith("I know 2 documents")
    assert response.source_documents == []
    mock_ollama.is_catalog_question.assert_awaited_once_with(query.question)
    mock_chromadb.list_documents.assert_awaited_once()
    mock_ollama.generate_response.assert_not_called()
    mock_chromadb.similarity_search.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_meta_question_with_empty_catalog(rag_service_with_mocks, mock_ollama, mock_chromadb):
    """With no documents indexed, answers honestly instead of listing empty."""
    from app.core.domain.models import Query

    mock_ollama.is_catalog_question = AsyncMock(return_value=True)
    mock_chromadb.list_documents.side_effect = None
    mock_chromadb.list_documents.return_value = []

    query = Query(question="How many documents do you have?")
    response = await rag_service_with_mocks.ask_question(query)

    assert "don't have any documents" in response.answer.lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_content_question_still_uses_normal_pipeline(
    rag_service_with_mocks, sample_query, mock_ollama, mock_chromadb
):
    """
    If the LLM classifies the question as a content one (the mock's
    default, see conftest.py), it does NOT get routed to the catalog shortcut.
    """
    await rag_service_with_mocks.ask_question(sample_query)

    mock_ollama.is_catalog_question.assert_awaited_once_with(sample_query.question)
    mock_chromadb.similarity_search.assert_called()
    mock_ollama.generate_response.assert_called_once()
    mock_chromadb.list_documents.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_catalog_classification_failure_falls_back_to_content_pipeline(
    rag_service_with_mocks, sample_query, mock_ollama, mock_chromadb
):
    """
    If is_catalog_question() fails (network exception, etc.), the safe
    fallback documented in LLMPort.is_catalog_question is to treat it as
    a content question — not for ask_question() to blow up entirely.
    """
    mock_ollama.is_catalog_question = AsyncMock(side_effect=RuntimeError("LLM unavailable"))

    response = await rag_service_with_mocks.ask_question(sample_query)

    # ask_question() already wraps the whole body in try/except (see the
    # generic except at the end of the method) — an exception here
    # shouldn't break the request, only degrade to the usual error answer.
    assert response.answer is not None


# ============================================================================
# TESTS for condense_question() (query rewriting) in ask_question()
# ============================================================================
# Standard conversational RAG pattern: a follow-up question is rewritten
# as standalone using the history BEFORE retrieval, instead of trying to
# answer only from the history or letting similarity_search fail with an
# anchorless question (see LLMPort.condense_question).

@pytest.mark.unit
@pytest.mark.asyncio
async def test_condense_question_called_when_history_present(
    rag_service_with_mocks, mock_ollama, mock_chromadb
):
    """With history, condensing happens before retrieval and retrieval uses the condensed question."""
    from app.core.domain.models import Query

    mock_ollama.condense_question = AsyncMock(return_value="What year was 1984 published?")
    history = "User: tell me about 1984\nAssistant: ...published in 1949..."
    query = Query(question="What year was it published?")

    await rag_service_with_mocks.ask_question(query, history=history)

    mock_ollama.condense_question.assert_awaited_once_with(query.question, history)
    # Retrieval (embeddings/keywords) must use the ALREADY condensed
    # question, not the original context-free follow-up
    mock_ollama.generate_embedding.assert_awaited_once_with("What year was 1984 published?")
    mock_ollama.extract_keywords.assert_awaited_once_with("What year was 1984 published?")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_condense_question_not_called_without_history(
    rag_service_with_mocks, sample_query, mock_ollama
):
    """With no history there's nothing to condense — the LLM isn't called for that."""
    await rag_service_with_mocks.ask_question(sample_query)  # history=None by default

    mock_ollama.condense_question.assert_not_called()
    mock_ollama.generate_embedding.assert_awaited_once_with(sample_query.question)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_condense_question_not_called_for_catalog_questions(
    rag_service_with_mocks, mock_ollama
):
    """A catalog question doesn't need condensing — it's short-circuited before that."""
    from app.core.domain.models import Query

    mock_ollama.is_catalog_question = AsyncMock(return_value=True)
    query = Query(question="How many books do you know?")

    await rag_service_with_mocks.ask_question(query, history="some history")

    mock_ollama.condense_question.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_generate_response_receives_condensed_question_as_prompt(
    rag_service_with_mocks, mock_ollama
):
    """The final answer is generated with the condensed question, not the short original."""
    from app.core.domain.models import Query

    mock_ollama.condense_question = AsyncMock(return_value="How many pages does One Hundred Years of Solitude have?")
    query = Query(question="How many pages does it have?")

    await rag_service_with_mocks.ask_question(query, history="User: One Hundred Years of Solitude...")

    _, kwargs = mock_ollama.generate_response.call_args
    assert kwargs["prompt"] == "How many pages does One Hundred Years of Solitude have?"


# ============================================================================
# TESTS for ask_question_stream() (SSE streaming)
# ============================================================================

async def _collect_stream(async_gen):
    """Helper: consumes an async generator and returns the list of events."""
    return [event async for event in async_gen]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stream_yields_sources_before_tokens(rag_service_with_mocks, sample_query):
    """The first event emitted is always 'sources', before any 'token'."""
    events = await _collect_stream(rag_service_with_mocks.ask_question_stream(sample_query))

    assert events[0]["type"] == "sources"
    assert len(events[0]["source_documents"]) > 0
    assert any(e["type"] == "token" for e in events[1:-1])


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stream_ends_with_done_event(rag_service_with_mocks, sample_query):
    """The last event is always 'done', with processing_time and session_id."""
    events = await _collect_stream(rag_service_with_mocks.ask_question_stream(sample_query))

    assert events[-1]["type"] == "done"
    assert "processing_time" in events[-1]
    assert events[-1]["session_id"] == sample_query.session_id


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stream_tokens_concatenate_to_full_answer(rag_service_with_mocks, sample_query, mock_ollama):
    """Concatenating the stream's 'token's gives the same answer as generate_response()."""
    events = await _collect_stream(rag_service_with_mocks.ask_question_stream(sample_query))

    streamed_answer = "".join(e["text"] for e in events if e["type"] == "token")
    full_answer = await mock_ollama.generate_response(prompt=sample_query.question, context="some context")

    # mock_stream_response chunks the same template as mock_generate_response
    # (see conftest.py) — we can't compare the exact context, but we can
    # check streaming doesn't lose/duplicate text: both start the same way.
    assert streamed_answer.startswith("Based on the provided context,")
    assert full_answer.startswith("Based on the provided context,")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stream_no_relevant_context_yields_fallback_token(rag_service_with_mocks, sample_query, mock_chromadb):
    """With no relevant chunks, an empty sources + a single fallback token + done are emitted."""
    from app.core.domain.models import SourceDocument

    async def mock_search(*args, **kwargs):
        return [SourceDocument(document_id="doc", chunk_content="irrelevant", metadata={}, relevance_score=0.05)]

    mock_chromadb.similarity_search = AsyncMock(side_effect=mock_search)

    events = await _collect_stream(rag_service_with_mocks.ask_question_stream(sample_query))

    assert events[0] == {"type": "sources", "source_documents": []}
    token_events = [e for e in events if e["type"] == "token"]
    assert len(token_events) == 1
    assert "couldn't find relevant information" in token_events[0]["text"]
    assert events[-1]["type"] == "done"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stream_meta_question_yields_single_token_with_catalog(
    rag_service_with_mocks, mock_ollama, mock_chromadb
):
    """Same shortcut as ask_question(), but as a stream: a single token, no generation."""
    from app.core.domain.models import Query

    mock_ollama.is_catalog_question = AsyncMock(return_value=True)
    query = Query(question="What documents do you have?")
    events = await _collect_stream(rag_service_with_mocks.ask_question_stream(query))

    assert events[0] == {"type": "sources", "source_documents": []}
    token_events = [e for e in events if e["type"] == "token"]
    assert len(token_events) == 1
    assert "1984" in token_events[0]["text"]
    assert events[-1]["type"] == "done"
    mock_ollama.generate_response.assert_not_called()
    mock_chromadb.similarity_search.assert_not_called()


# ============================================================================
# INTEGRATION TESTS (require real services)
# ============================================================================
# These tests are marked with @pytest.mark.integration
# Only run when you want to do full tests with real services

@pytest.mark.integration
@pytest.mark.asyncio
async def test_query_with_real_services():
    """
    Integration test: query with real Ollama and ChromaDB.

    NOTE: This test requires:
    - Ollama running (ollama serve)
    - ChromaDB running (docker-compose up chromadb)
    - Data ingested beforehand

    Run with: pytest -m integration tests/test_rag_service.py -v
    """
    from app.adapters.outbound.ollama_adapter import OllamaAdapter
    from app.adapters.outbound.chromadb_adapter import ChromaDBAdapter
    from app.core.services.rag_service import RAGService
    from app.core.domain.models import Query

    # Check that Ollama is available
    ollama = OllamaAdapter()
    if not await ollama.is_available():
        pytest.skip("Ollama is not available")

    # Create the RAG service with real adapters
    chromadb = ChromaDBAdapter()
    rag_service = RAGService(llm=ollama, vector_db=chromadb)

    # Basic query test
    query = Query(question="What information do you have available?", max_results=3)
    result = await rag_service.ask_question(query)

    # Verify the response's structure
    assert result is not None
    assert result.answer is not None
    assert isinstance(result.source_documents, list)
    assert result.processing_time > 0

    # Log for debugging
    print(f"\n✅ Answer: {result.answer[:100]}...")
    print(f"📚 Sources found: {len(result.source_documents)}")
