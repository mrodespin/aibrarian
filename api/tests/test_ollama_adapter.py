# /api/tests/test_ollama_adapter.py
"""
Tests del OllamaAdapter - verifica que los parámetros de generación
(temperature, max_tokens) realmente llegan a Ollama.

Contexto del bug que estos tests cubren:
OllamaLLM._default_params solo expone 4 keys de nivel superior (model, format,
options, keep_alive). ainvoke() únicamente reenvía a Ollama los kwargs que
coincidan con esos nombres — pasar temperature/num_predict sueltos como kwargs
no lanza ningún error, simplemente Ollama los ignora. El fix real es anidarlos
dentro de un dict "options". Estos tests aseguran que no vuelva a pasar.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.adapters.outbound.ollama_adapter import OllamaAdapter


@pytest.mark.unit
@pytest.mark.asyncio
async def test_generate_response_passes_temperature_via_options():
    """generate_response() debe anidar temperature dentro de options={...}."""
    adapter = OllamaAdapter()

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value="respuesta de prueba")

    with patch.object(adapter, "_get_llm", return_value=mock_llm):
        await adapter.generate_response(
            prompt="¿Qué es RAG?",
            context="RAG es Retrieval-Augmented Generation.",
            temperature=0.42
        )

    mock_llm.ainvoke.assert_called_once()
    _, kwargs = mock_llm.ainvoke.call_args
    assert "options" in kwargs
    assert kwargs["options"]["temperature"] == 0.42
    # temperature NO debe ir como kwarg suelto (ese es justo el bug original)
    assert "temperature" not in kwargs


@pytest.mark.unit
@pytest.mark.asyncio
async def test_generate_response_forwards_max_tokens_as_num_predict():
    """max_tokens debe traducirse a options['num_predict'] (nombre real en Ollama)."""
    adapter = OllamaAdapter()

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value="respuesta de prueba")

    with patch.object(adapter, "_get_llm", return_value=mock_llm):
        await adapter.generate_response(
            prompt="¿Qué es RAG?",
            max_tokens=256
        )

    _, kwargs = mock_llm.ainvoke.call_args
    assert kwargs["options"]["num_predict"] == 256


@pytest.mark.unit
@pytest.mark.asyncio
async def test_generate_response_omits_num_predict_when_max_tokens_none():
    """Si max_tokens es None, no debe forzarse num_predict (deja el default de Ollama)."""
    adapter = OllamaAdapter()

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value="respuesta de prueba")

    with patch.object(adapter, "_get_llm", return_value=mock_llm):
        await adapter.generate_response(prompt="¿Qué es RAG?")

    _, kwargs = mock_llm.ainvoke.call_args
    assert "num_predict" not in kwargs["options"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_extract_keywords_passes_temperature_via_options():
    """extract_keywords() debe anidar temperature=0.1 dentro de options={...}."""
    adapter = OllamaAdapter()

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value="Blade Runner\ndirector")

    with patch.object(adapter, "_get_llm", return_value=mock_llm):
        keywords = await adapter.extract_keywords("¿Quién dirigió Blade Runner?")

    _, kwargs = mock_llm.ainvoke.call_args
    assert kwargs["options"] == {"temperature": 0.1}
    assert keywords == ["Blade Runner", "director"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stream_response_yields_chunks_via_astream():
    """stream_response() usa llm.astream() (no ainvoke) y reenvía cada trozo."""
    adapter = OllamaAdapter()

    mock_llm = MagicMock()

    async def mock_astream(prompt, options=None):
        for chunk in ["Do", "cker", " es genial"]:
            yield chunk

    mock_llm.astream = mock_astream

    with patch.object(adapter, "_get_llm", return_value=mock_llm):
        chunks = [
            chunk async for chunk in adapter.stream_response(
                prompt="¿Qué es Docker?",
                context="Docker es una plataforma de contenedores.",
                temperature=0.3
            )
        ]

    assert chunks == ["Do", "cker", " es genial"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stream_response_passes_temperature_and_max_tokens_via_options():
    """stream_response() debe anidar temperature/num_predict igual que generate_response()."""
    adapter = OllamaAdapter()

    mock_llm = MagicMock()
    captured_options = {}

    async def mock_astream(prompt, options=None):
        captured_options.update(options or {})
        yield "chunk"

    mock_llm.astream = mock_astream

    with patch.object(adapter, "_get_llm", return_value=mock_llm):
        async for _ in adapter.stream_response(prompt="¿Qué es RAG?", temperature=0.55, max_tokens=100):
            pass

    assert captured_options["temperature"] == 0.55
    assert captured_options["num_predict"] == 100
