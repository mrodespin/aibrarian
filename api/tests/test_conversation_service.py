# /api/tests/test_conversation_service.py
"""
Tests de ConversationService - persistencia y formateo del historial de
conversación usado como contexto extra en el prompt del LLM (ver
RAGService.ask_question / OllamaAdapter.generate_response).
"""

import pytest

from app.config.settings import settings


@pytest.mark.unit
@pytest.mark.asyncio
async def test_append_turn_stores_both_messages(conversation_service_with_mocks, mock_conversation_repository):
    """append_turn() guarda un mensaje 'user' y otro 'assistant'."""
    await conversation_service_with_mocks.append_turn(
        session_id="session-1",
        user_id=1,
        question="¿Qué es RAG?",
        answer="RAG combina búsqueda con generación de texto."
    )

    stored = mock_conversation_repository._storage["session-1"]
    assert len(stored) == 2
    assert stored[0].role == "user"
    assert stored[0].content == "¿Qué es RAG?"
    assert stored[1].role == "assistant"
    assert stored[1].content == "RAG combina búsqueda con generación de texto."


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_history_prompt_block_empty_when_no_messages(conversation_service_with_mocks):
    """Sin turnos previos, el bloque de historial es una cadena vacía."""
    block = await conversation_service_with_mocks.get_history_prompt_block("session-nueva", 1)
    assert block == ""


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_history_prompt_block_formats_turns(conversation_service_with_mocks):
    """El bloque de historial formatea los turnos como 'Usuario:'/'Asistente:'."""
    await conversation_service_with_mocks.append_turn(
        session_id="session-2",
        user_id=1,
        question="¿Qué es RAG?",
        answer="RAG combina búsqueda con generación de texto."
    )

    block = await conversation_service_with_mocks.get_history_prompt_block("session-2", 1)

    assert "Usuario: ¿Qué es RAG?" in block
    assert "Asistente: RAG combina búsqueda con generación de texto." in block


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_history_prompt_block_respects_turn_limit(conversation_service_with_mocks, monkeypatch):
    """Solo se incluyen los últimos settings.conversation_history_turns turnos."""
    monkeypatch.setattr(settings, "conversation_history_turns", 1)

    await conversation_service_with_mocks.append_turn("session-3", 1, "primera pregunta", "primera respuesta")
    await conversation_service_with_mocks.append_turn("session-3", 1, "segunda pregunta", "segunda respuesta")

    block = await conversation_service_with_mocks.get_history_prompt_block("session-3", 1)

    assert "segunda pregunta" in block
    assert "primera pregunta" not in block


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_history_prompt_block_disabled_returns_empty_without_querying(
    conversation_service_with_mocks, mock_conversation_repository, monkeypatch
):
    """conversation_history_turns=0 desactiva el historial sin tocar el repositorio."""
    monkeypatch.setattr(settings, "conversation_history_turns", 0)

    block = await conversation_service_with_mocks.get_history_prompt_block("session-4", 1)

    assert block == ""
    mock_conversation_repository.get_recent_messages.assert_not_called()
