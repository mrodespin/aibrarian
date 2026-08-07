# /api/tests/test_conversation_service.py
"""
ConversationService tests - persisting and formatting conversation
history used as extra context in the LLM's prompt (see
RAGService.ask_question / OllamaAdapter.generate_response).
"""

import pytest

from app.config.settings import settings


@pytest.mark.unit
@pytest.mark.asyncio
async def test_append_turn_stores_both_messages(conversation_service_with_mocks, mock_conversation_repository):
    """append_turn() saves one 'user' message and one 'assistant' message."""
    await conversation_service_with_mocks.append_turn(
        session_id="session-1",
        user_id=1,
        question="What is RAG?",
        answer="RAG combines search with text generation."
    )

    stored = mock_conversation_repository._storage["session-1"]
    assert len(stored) == 2
    assert stored[0].role == "user"
    assert stored[0].content == "What is RAG?"
    assert stored[1].role == "assistant"
    assert stored[1].content == "RAG combines search with text generation."


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_history_prompt_block_empty_when_no_messages(conversation_service_with_mocks):
    """With no previous turns, the history block is an empty string."""
    block = await conversation_service_with_mocks.get_history_prompt_block("new-session", 1)
    assert block == ""


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_history_prompt_block_formats_turns(conversation_service_with_mocks):
    """The history block formats turns as 'User:'/'Assistant:'."""
    await conversation_service_with_mocks.append_turn(
        session_id="session-2",
        user_id=1,
        question="What is RAG?",
        answer="RAG combines search with text generation."
    )

    block = await conversation_service_with_mocks.get_history_prompt_block("session-2", 1)

    assert "User: What is RAG?" in block
    assert "Assistant: RAG combines search with text generation." in block


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_history_prompt_block_respects_turn_limit(conversation_service_with_mocks, monkeypatch):
    """Only the last settings.conversation_history_turns turns are included."""
    monkeypatch.setattr(settings, "conversation_history_turns", 1)

    await conversation_service_with_mocks.append_turn("session-3", 1, "first question", "first answer")
    await conversation_service_with_mocks.append_turn("session-3", 1, "second question", "second answer")

    block = await conversation_service_with_mocks.get_history_prompt_block("session-3", 1)

    assert "second question" in block
    assert "first question" not in block


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_history_prompt_block_disabled_returns_empty_without_querying(
    conversation_service_with_mocks, mock_conversation_repository, monkeypatch
):
    """conversation_history_turns=0 disables history without touching the repository."""
    monkeypatch.setattr(settings, "conversation_history_turns", 0)

    block = await conversation_service_with_mocks.get_history_prompt_block("session-4", 1)

    assert block == ""
    mock_conversation_repository.get_recent_messages.assert_not_called()
