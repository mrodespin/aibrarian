# /api/tests/test_ollama_adapter.py
"""
OllamaAdapter tests - verify the generation parameters (temperature,
max_tokens) actually reach Ollama.

Context for the bug these tests cover:
OllamaLLM._default_params only exposes 4 top-level keys (model, format,
options, keep_alive). ainvoke() only forwards to Ollama the kwargs that
match those names — passing temperature/num_predict loose as kwargs
doesn't raise any error, Ollama just ignores them. The real fix is
nesting them inside an "options" dict. These tests make sure this
doesn't happen again.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.adapters.outbound.ollama_adapter import OllamaAdapter


@pytest.mark.unit
@pytest.mark.asyncio
async def test_generate_response_passes_temperature_via_options():
    """generate_response() must nest temperature inside options={...}."""
    adapter = OllamaAdapter()

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value="test response")

    with patch.object(adapter, "_get_llm", return_value=mock_llm):
        await adapter.generate_response(
            prompt="What is RAG?",
            context="RAG is Retrieval-Augmented Generation.",
            temperature=0.42
        )

    mock_llm.ainvoke.assert_called_once()
    _, kwargs = mock_llm.ainvoke.call_args
    assert "options" in kwargs
    assert kwargs["options"]["temperature"] == 0.42
    # temperature must NOT go as a loose kwarg (that's exactly the original bug)
    assert "temperature" not in kwargs


@pytest.mark.unit
@pytest.mark.asyncio
async def test_generate_response_forwards_max_tokens_as_num_predict():
    """max_tokens must be translated to options['num_predict'] (Ollama's real name for it)."""
    adapter = OllamaAdapter()

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value="test response")

    with patch.object(adapter, "_get_llm", return_value=mock_llm):
        await adapter.generate_response(
            prompt="What is RAG?",
            max_tokens=256
        )

    _, kwargs = mock_llm.ainvoke.call_args
    assert kwargs["options"]["num_predict"] == 256


@pytest.mark.unit
@pytest.mark.asyncio
async def test_generate_response_omits_num_predict_when_max_tokens_none():
    """If max_tokens is None, num_predict shouldn't be forced (leaves Ollama's default)."""
    adapter = OllamaAdapter()

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value="test response")

    with patch.object(adapter, "_get_llm", return_value=mock_llm):
        await adapter.generate_response(prompt="What is RAG?")

    _, kwargs = mock_llm.ainvoke.call_args
    assert "num_predict" not in kwargs["options"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_extract_keywords_passes_temperature_via_options():
    """extract_keywords() must nest temperature=0.1 inside options={...}."""
    adapter = OllamaAdapter()

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value="Blade Runner\ndirector")

    with patch.object(adapter, "_get_llm", return_value=mock_llm):
        keywords = await adapter.extract_keywords("Who directed Blade Runner?")

    _, kwargs = mock_llm.ainvoke.call_args
    assert kwargs["options"] == {"temperature": 0.1}
    assert keywords == ["Blade Runner", "director"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_is_catalog_question_true_when_llm_answers_catalog():
    adapter = OllamaAdapter()

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value="CATALOG")

    with patch.object(adapter, "_get_llm", return_value=mock_llm):
        result = await adapter.is_catalog_question("How many books do you know?")

    assert result is True
    _, kwargs = mock_llm.ainvoke.call_args
    assert kwargs["options"] == {"temperature": 0.0}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_is_catalog_question_false_when_llm_answers_content():
    adapter = OllamaAdapter()

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value="CONTENT")

    with patch.object(adapter, "_get_llm", return_value=mock_llm):
        result = await adapter.is_catalog_question("Who wrote 1984?")

    assert result is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_is_catalog_question_returns_false_on_error():
    """Safe fallback documented in LLMPort: error → False, no exception."""
    adapter = OllamaAdapter()

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(side_effect=RuntimeError("connection refused"))

    with patch.object(adapter, "_get_llm", return_value=mock_llm):
        result = await adapter.is_catalog_question("How many books do you know?")

    assert result is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_condense_question_rewrites_using_history():
    adapter = OllamaAdapter()

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value="What year was 1984 published?")

    with patch.object(adapter, "_get_llm", return_value=mock_llm):
        result = await adapter.condense_question(
            "What year was it published?",
            history="User: tell me about 1984\nAssistant: ...published in 1949...",
        )

    assert result == "What year was 1984 published?"
    _, kwargs = mock_llm.ainvoke.call_args
    assert kwargs["options"] == {"temperature": 0.0}
    # The history gets interpolated into the prompt sent to ainvoke
    prompt_arg = mock_llm.ainvoke.call_args.args[0]
    assert "published in 1949" in prompt_arg


@pytest.mark.unit
@pytest.mark.asyncio
async def test_condense_question_returns_original_on_empty_response():
    """If the LLM returns something empty/degenerate, better the original than losing it."""
    adapter = OllamaAdapter()

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value="   ")

    with patch.object(adapter, "_get_llm", return_value=mock_llm):
        result = await adapter.condense_question("How many pages does it have?", history="something")

    assert result == "How many pages does it have?"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_condense_question_returns_original_on_error():
    """Safe fallback documented in LLMPort: error → original question, no exception."""
    adapter = OllamaAdapter()

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(side_effect=RuntimeError("connection refused"))

    with patch.object(adapter, "_get_llm", return_value=mock_llm):
        result = await adapter.condense_question("How many pages does it have?", history="something")

    assert result == "How many pages does it have?"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stream_response_yields_chunks_via_astream():
    """stream_response() uses llm.astream() (not ainvoke) and forwards each chunk."""
    adapter = OllamaAdapter()

    mock_llm = MagicMock()

    async def mock_astream(prompt, options=None):
        for chunk in ["Do", "cker", " is great"]:
            yield chunk

    mock_llm.astream = mock_astream

    with patch.object(adapter, "_get_llm", return_value=mock_llm):
        chunks = [
            chunk async for chunk in adapter.stream_response(
                prompt="What is Docker?",
                context="Docker is a container platform.",
                temperature=0.3
            )
        ]

    assert chunks == ["Do", "cker", " is great"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stream_response_passes_temperature_and_max_tokens_via_options():
    """stream_response() must nest temperature/num_predict the same way generate_response() does."""
    adapter = OllamaAdapter()

    mock_llm = MagicMock()
    captured_options = {}

    async def mock_astream(prompt, options=None):
        captured_options.update(options or {})
        yield "chunk"

    mock_llm.astream = mock_astream

    with patch.object(adapter, "_get_llm", return_value=mock_llm):
        async for _ in adapter.stream_response(prompt="What is RAG?", temperature=0.55, max_tokens=100):
            pass

    assert captured_options["temperature"] == 0.55
    assert captured_options["num_predict"] == 100
