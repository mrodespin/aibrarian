# /api/tests/test_groq_adapter.py
"""
GroqAdapter tests - an LLMPort composed of Groq (generation) + local
embeddings (configurable backend: onnx by default, or
sentence_transformers). See ADR-007 and settings.embedding_backend.

Every external client (AsyncGroq, ONNXMiniLM_L6_V2/SentenceTransformer,
httpx) is mocked: these tests don't call real Groq or download models.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.adapters.outbound.groq_adapter import GroqAdapter


@pytest.fixture
def groq_settings(monkeypatch):
    """Ensures an API key is configured so the adapter doesn't fail when initializing the client."""
    monkeypatch.setattr("app.adapters.outbound.groq_adapter.settings.groq_api_key", "test-key")
    monkeypatch.setattr("app.adapters.outbound.groq_adapter.settings.groq_model", "openai/gpt-oss-120b")
    monkeypatch.setattr("app.adapters.outbound.groq_adapter.settings.embedding_model_name", "all-MiniLM-L6-v2")
    monkeypatch.setattr("app.adapters.outbound.groq_adapter.settings.embedding_backend", "onnx")


@pytest.mark.unit
def test_get_client_requires_api_key(monkeypatch):
    """Without GROQ_API_KEY, the adapter must fail with a clear message (not a raw SDK error)."""
    monkeypatch.setattr("app.adapters.outbound.groq_adapter.settings.groq_api_key", None)
    adapter = GroqAdapter()

    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        adapter._get_client()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_generate_response_uses_context_in_prompt(groq_settings):
    """
    When there's context (retrieved chunks), it must be injected into
    the message sent to Groq along with the anti-hallucination rules,
    the same way OllamaAdapter.generate_response does.
    """
    adapter = GroqAdapter()

    mock_completion = MagicMock()
    mock_completion.choices = [MagicMock(message=MagicMock(content="Simulated answer"))]

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_completion)

    with patch.object(adapter, "_get_client", return_value=mock_client):
        result = await adapter.generate_response(
            prompt="What is RAG?",
            context="RAG combines search with generation.",
        )

    assert result == "Simulated answer"
    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert call_kwargs["model"] == "openai/gpt-oss-120b"
    user_message = call_kwargs["messages"][-1]["content"]
    assert "RAG combines search with generation." in user_message
    assert "What is RAG?" in user_message


@pytest.mark.unit
@pytest.mark.asyncio
async def test_extract_keywords_parses_lines(groq_settings):
    """Every non-empty line in Groq's response becomes a keyword."""
    adapter = GroqAdapter()

    mock_completion = MagicMock()
    mock_completion.choices = [MagicMock(message=MagicMock(content="- Blade Runner 2049\n- director\n"))]

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_completion)

    with patch.object(adapter, "_get_client", return_value=mock_client):
        keywords = await adapter.extract_keywords("Who directed Blade Runner 2049?")

    assert "Blade Runner 2049" in keywords
    assert "director" in keywords


@pytest.mark.unit
@pytest.mark.asyncio
async def test_extract_keywords_returns_empty_on_error(groq_settings):
    """If Groq fails, extract_keywords must not propagate the exception (falls back to pure semantic search)."""
    adapter = GroqAdapter()

    with patch.object(adapter, "_get_client", side_effect=RuntimeError("boom")):
        keywords = await adapter.extract_keywords("any question")

    assert keywords == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_is_catalog_question_true_when_groq_answers_catalog(groq_settings):
    adapter = GroqAdapter()

    mock_completion = MagicMock()
    mock_completion.choices = [MagicMock(message=MagicMock(content="CATALOG"))]
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_completion)

    with patch.object(adapter, "_get_client", return_value=mock_client):
        result = await adapter.is_catalog_question("How many books do you have?")

    assert result is True
    _, kwargs = mock_client.chat.completions.create.call_args
    assert kwargs["temperature"] == 0.0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_is_catalog_question_false_when_groq_answers_content(groq_settings):
    adapter = GroqAdapter()

    mock_completion = MagicMock()
    mock_completion.choices = [MagicMock(message=MagicMock(content="CONTENT"))]
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_completion)

    with patch.object(adapter, "_get_client", return_value=mock_client):
        result = await adapter.is_catalog_question("Who wrote 1984?")

    assert result is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_is_catalog_question_returns_false_on_error(groq_settings):
    """Safe fallback documented in LLMPort: error → False, no exception."""
    adapter = GroqAdapter()

    with patch.object(adapter, "_get_client", side_effect=RuntimeError("boom")):
        result = await adapter.is_catalog_question("any question")

    assert result is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_condense_question_rewrites_using_history(groq_settings):
    adapter = GroqAdapter()

    mock_completion = MagicMock()
    mock_completion.choices = [MagicMock(message=MagicMock(content="What year was 1984 published?"))]
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_completion)

    with patch.object(adapter, "_get_client", return_value=mock_client):
        result = await adapter.condense_question(
            "What year was it published?",
            history="User: tell me about 1984\nAssistant: ...published in 1949...",
        )

    assert result == "What year was 1984 published?"
    _, kwargs = mock_client.chat.completions.create.call_args
    assert kwargs["temperature"] == 0.0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_condense_question_returns_original_on_empty_response(groq_settings):
    adapter = GroqAdapter()

    mock_completion = MagicMock()
    mock_completion.choices = [MagicMock(message=MagicMock(content="   "))]
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_completion)

    with patch.object(adapter, "_get_client", return_value=mock_client):
        result = await adapter.condense_question("How many pages?", history="something")

    assert result == "How many pages?"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_condense_question_returns_original_on_error(groq_settings):
    """Safe fallback documented in LLMPort: error → original question, no exception."""
    adapter = GroqAdapter()

    with patch.object(adapter, "_get_client", side_effect=RuntimeError("boom")):
        result = await adapter.condense_question("How many pages?", history="something")

    assert result == "How many pages?"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_generate_embeddings_batch_uses_onnx_by_default(groq_settings):
    """Embeddings don't call Groq: by default they use ONNXMiniLM_L6_V2 (callable) via an executor."""
    adapter = GroqAdapter()

    fake_vector_1 = MagicMock()
    fake_vector_1.tolist.return_value = [0.1, 0.2]
    fake_vector_2 = MagicMock()
    fake_vector_2.tolist.return_value = [0.3, 0.4]

    mock_embedder = MagicMock(return_value=[fake_vector_1, fake_vector_2])

    with patch.object(adapter, "_get_embedder", return_value=mock_embedder):
        result = await adapter.generate_embeddings_batch(["text one", "text two"])

    assert result == [[0.1, 0.2], [0.3, 0.4]]
    mock_embedder.assert_called_once_with(["text one", "text two"])


@pytest.mark.unit
@pytest.mark.asyncio
async def test_generate_embeddings_batch_uses_sentence_transformers_when_configured(groq_settings, monkeypatch):
    """With EMBEDDING_BACKEND=sentence_transformers, uses .encode(...) instead of calling the embedder directly."""
    monkeypatch.setattr("app.adapters.outbound.groq_adapter.settings.embedding_backend", "sentence_transformers")
    adapter = GroqAdapter()

    fake_vectors = MagicMock()
    fake_vectors.tolist.return_value = [[0.1, 0.2], [0.3, 0.4]]

    mock_embedder = MagicMock()
    mock_embedder.encode.return_value = fake_vectors

    with patch.object(adapter, "_get_embedder", return_value=mock_embedder):
        result = await adapter.generate_embeddings_batch(["text one", "text two"])

    assert result == [[0.1, 0.2], [0.3, 0.4]]
    mock_embedder.encode.assert_called_once()
    assert mock_embedder.encode.call_args.args[0] == ["text one", "text two"]


@pytest.mark.unit
def test_get_embedder_sentence_transformers_requires_package(groq_settings, monkeypatch):
    """If EMBEDDING_BACKEND=sentence_transformers but the package isn't installed, a clear error (not a raw ImportError)."""
    monkeypatch.setattr("app.adapters.outbound.groq_adapter.settings.embedding_backend", "sentence_transformers")
    adapter = GroqAdapter()

    with patch.dict("sys.modules", {"sentence_transformers": None}):
        with pytest.raises(RuntimeError, match="EMBEDDING_BACKEND=sentence_transformers"):
            adapter._get_embedder()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_generate_embedding_single_text(groq_settings):
    """generate_embedding delegates to generate_embeddings_batch and returns the first vector."""
    adapter = GroqAdapter()

    with patch.object(adapter, "generate_embeddings_batch", AsyncMock(return_value=[[0.9, 0.8]])) as mocked:
        result = await adapter.generate_embedding("some text")

    mocked.assert_awaited_once_with(["some text"])
    assert result == [0.9, 0.8]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_is_available_false_without_api_key(monkeypatch):
    monkeypatch.setattr("app.adapters.outbound.groq_adapter.settings.groq_api_key", None)
    adapter = GroqAdapter()

    assert await adapter.is_available() is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_is_available_true_when_groq_ok(groq_settings):
    adapter = GroqAdapter()

    mock_response = MagicMock(status_code=200)
    mock_async_client = MagicMock()
    mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
    mock_async_client.__aexit__ = AsyncMock(return_value=False)
    mock_async_client.get = AsyncMock(return_value=mock_response)

    with patch("app.adapters.outbound.groq_adapter.httpx.AsyncClient", return_value=mock_async_client):
        with patch.object(adapter, "_get_embedder", return_value=MagicMock()) as mock_get_embedder:
            assert await adapter.is_available() is True

    # is_available() must not load the embedding model: it's called
    # during FastAPI's startup and would block opening the port (see
    # is_available's docstring in groq_adapter.py).
    mock_get_embedder.assert_not_called()


@pytest.mark.unit
def test_get_model_info_reports_both_engines(groq_settings):
    adapter = GroqAdapter()
    info = adapter.get_model_info()

    assert info["llm_provider"] == "groq"
    assert info["llm_model"] == "openai/gpt-oss-120b"
    assert info["embedding_model"] == "all-MiniLM-L6-v2"
    assert "onnxruntime" in info["embedding_provider"]


@pytest.mark.unit
def test_get_model_info_reports_sentence_transformers_when_configured(groq_settings, monkeypatch):
    monkeypatch.setattr("app.adapters.outbound.groq_adapter.settings.embedding_backend", "sentence_transformers")
    adapter = GroqAdapter()
    info = adapter.get_model_info()

    assert "sentence-transformers" in info["embedding_provider"]
