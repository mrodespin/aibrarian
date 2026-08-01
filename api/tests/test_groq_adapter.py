# /api/tests/test_groq_adapter.py
"""
Tests de GroqAdapter - LLMPort compuesto por Groq (generación) +
sentence-transformers local (embeddings). Ver ADR-007.

Todos los clientes externos (AsyncGroq, SentenceTransformer, httpx) están
mockeados: estos tests no llaman a Groq real ni descargan modelos.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.adapters.outbound.groq_adapter import GroqAdapter


@pytest.fixture
def groq_settings(monkeypatch):
    """Asegura que hay una API key configurada para que el adapter no falle al inicializar el cliente."""
    monkeypatch.setattr("app.adapters.outbound.groq_adapter.settings.groq_api_key", "test-key")
    monkeypatch.setattr("app.adapters.outbound.groq_adapter.settings.groq_model", "openai/gpt-oss-120b")
    monkeypatch.setattr("app.adapters.outbound.groq_adapter.settings.embedding_model_name", "all-MiniLM-L6-v2")


@pytest.mark.unit
def test_get_client_requires_api_key(monkeypatch):
    """Sin GROQ_API_KEY, el adapter debe fallar con un mensaje claro (no un error crudo del SDK)."""
    monkeypatch.setattr("app.adapters.outbound.groq_adapter.settings.groq_api_key", None)
    adapter = GroqAdapter()

    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        adapter._get_client()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_generate_response_uses_context_in_prompt(groq_settings):
    """
    Cuando hay contexto (chunks recuperados), debe inyectarse en el mensaje
    enviado a Groq junto con las reglas anti-alucinación, igual que hace
    OllamaAdapter.generate_response.
    """
    adapter = GroqAdapter()

    mock_completion = MagicMock()
    mock_completion.choices = [MagicMock(message=MagicMock(content="Respuesta simulada"))]

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_completion)

    with patch.object(adapter, "_get_client", return_value=mock_client):
        result = await adapter.generate_response(
            prompt="¿Qué es RAG?",
            context="RAG combina búsqueda con generación.",
        )

    assert result == "Respuesta simulada"
    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert call_kwargs["model"] == "openai/gpt-oss-120b"
    user_message = call_kwargs["messages"][-1]["content"]
    assert "RAG combina búsqueda con generación." in user_message
    assert "¿Qué es RAG?" in user_message


@pytest.mark.unit
@pytest.mark.asyncio
async def test_extract_keywords_parses_lines(groq_settings):
    """Cada línea no vacía de la respuesta de Groq se convierte en una keyword."""
    adapter = GroqAdapter()

    mock_completion = MagicMock()
    mock_completion.choices = [MagicMock(message=MagicMock(content="- Blade Runner 2049\n- director\n"))]

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_completion)

    with patch.object(adapter, "_get_client", return_value=mock_client):
        keywords = await adapter.extract_keywords("¿Quién dirigió Blade Runner 2049?")

    assert "Blade Runner 2049" in keywords
    assert "director" in keywords


@pytest.mark.unit
@pytest.mark.asyncio
async def test_extract_keywords_returns_empty_on_error(groq_settings):
    """Si Groq falla, extract_keywords no debe propagar la excepción (fallback a búsqueda semántica pura)."""
    adapter = GroqAdapter()

    with patch.object(adapter, "_get_client", side_effect=RuntimeError("boom")):
        keywords = await adapter.extract_keywords("cualquier pregunta")

    assert keywords == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_generate_embeddings_batch_uses_local_model(groq_settings):
    """Los embeddings no llaman a Groq: usan el SentenceTransformer local vía executor."""
    adapter = GroqAdapter()

    fake_vectors = MagicMock()
    fake_vectors.tolist.return_value = [[0.1, 0.2], [0.3, 0.4]]

    mock_embedder = MagicMock()
    mock_embedder.encode.return_value = fake_vectors

    with patch.object(adapter, "_get_embedder", return_value=mock_embedder):
        result = await adapter.generate_embeddings_batch(["texto uno", "texto dos"])

    assert result == [[0.1, 0.2], [0.3, 0.4]]
    mock_embedder.encode.assert_called_once()
    assert mock_embedder.encode.call_args.args[0] == ["texto uno", "texto dos"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_generate_embedding_single_text(groq_settings):
    """generate_embedding delega en generate_embeddings_batch y devuelve el primer vector."""
    adapter = GroqAdapter()

    with patch.object(adapter, "generate_embeddings_batch", AsyncMock(return_value=[[0.9, 0.8]])) as mocked:
        result = await adapter.generate_embedding("un texto")

    mocked.assert_awaited_once_with(["un texto"])
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

    # is_available() no debe cargar el modelo de embeddings: se llama en el
    # startup de FastAPI y bloquearía la apertura del puerto (ver docstring
    # de is_available en groq_adapter.py).
    mock_get_embedder.assert_not_called()


@pytest.mark.unit
def test_get_model_info_reports_both_engines(groq_settings):
    adapter = GroqAdapter()
    info = adapter.get_model_info()

    assert info["llm_provider"] == "groq"
    assert info["llm_model"] == "openai/gpt-oss-120b"
    assert info["embedding_model"] == "all-MiniLM-L6-v2"
    assert "sentence-transformers" in info["embedding_provider"]
