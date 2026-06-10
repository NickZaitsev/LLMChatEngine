from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from features import BotFeature
from prompt.assembler import PromptAssembler
from settings import AppSettings


class MockTokenizer:
    def count_tokens(self, text: str) -> int:
        return max(1, len(text) // 4) if text else 0

    def encode(self, text: str):
        return list(range(self.count_tokens(text)))


def build_assembler(book_knowledge_manager, feature_flags, app_settings=None):
    conversation_id = uuid4()
    conversation_repo = AsyncMock()
    conversation_repo.get_conversation.return_value = SimpleNamespace(
        id=conversation_id,
        user_id=uuid4(),
        bot_id=uuid4(),
        summary=None,
        last_summarized_message_id=None,
    )
    message_repo = AsyncMock()
    message_repo.get_last_user_message.return_value = None
    message_repo.fetch_active_messages.return_value = []
    memory_manager = AsyncMock()
    memory_manager.get_context.return_value = ""
    user_repo = AsyncMock()
    user_repo.get_user.return_value = SimpleNamespace(username="user123")

    assembler = PromptAssembler(
        message_repo=message_repo,
        memory_manager=memory_manager,
        conversation_repo=conversation_repo,
        user_repo=user_repo,
        book_knowledge_manager=book_knowledge_manager,
        tokenizer=MockTokenizer(),
        config={"include_system_template": True},
        app_settings=app_settings,
    )
    assembler.personality = "System prompt"
    assembler.feature_flags = feature_flags
    return assembler, str(conversation_id), conversation_repo

@pytest.mark.asyncio
async def test_book_context_is_injected_when_feature_enabled():
    book_manager = AsyncMock()
    book_manager.get_context.return_value = "[«Book»]\nRelevant passage."
    assembler, conversation_id, conversation_repo = build_assembler(
        book_manager,
        {BotFeature.BOOK_KNOWLEDGE.value: True},
    )
    bot_id = conversation_repo.get_conversation.return_value.bot_id

    messages, metadata = await assembler.build_prompt_and_metadata(
        conversation_id,
        user_query="What does the author say?",
        history_budget=1000,
    )

    book_messages = [msg for msg in messages if msg["content"].startswith("### Book Context")]
    assert len(book_messages) == 1
    assert "Relevant passage." in book_messages[0]["content"]
    book_manager.get_context.assert_awaited_once_with(
        bot_id=str(bot_id),
        query="What does the author say?",
        top_k=4,
        min_score=0.35,
    )
    assert metadata["token_counts"]["book_tokens"] > 0
    assert metadata["included_book_chunk_ids"] == []
    assert metadata["total_tokens"] == (
        metadata["token_counts"]["system_tokens"]
        + metadata["token_counts"]["memory_tokens"]
        + metadata["token_counts"]["book_tokens"]
        + metadata["token_counts"]["history_tokens"]
    )


@pytest.mark.asyncio
async def test_book_context_uses_injected_settings():
    book_manager = AsyncMock()
    book_manager.get_context.return_value = "Injected settings passage."
    settings = AppSettings(
        TELEGRAM_TOKEN="token",
        DATABASE_URL="postgresql+asyncpg://u:p@localhost/db",
        PROVIDER="lmstudio",
        BOOK_RAG_TOP_K=7,
        BOOK_RAG_MIN_SCORE=0.77,
        BOOK_RAG_TOKEN_BUDGET_RATIO=0.5,
    )
    assembler, conversation_id, conversation_repo = build_assembler(
        book_manager,
        {BotFeature.BOOK_KNOWLEDGE.value: True},
        settings,
    )

    await assembler.build_prompt_and_metadata(
        conversation_id,
        user_query="query",
        history_budget=1000,
    )

    book_manager.get_context.assert_awaited_once_with(
        bot_id=str(conversation_repo.get_conversation.return_value.bot_id),
        query="query",
        top_k=7,
        min_score=0.77,
    )


@pytest.mark.asyncio
async def test_book_context_skips_when_feature_disabled():
    book_manager = AsyncMock()
    book_manager.get_context.return_value = "[«Book»]\nRelevant passage."
    assembler, conversation_id, _ = build_assembler(book_manager, {})

    messages, metadata = await assembler.build_prompt_and_metadata(
        conversation_id,
        user_query="query",
    )

    assert all("### Book Context" not in msg["content"] for msg in messages)
    book_manager.get_context.assert_not_called()
    assert metadata["token_counts"]["book_tokens"] == 0


@pytest.mark.asyncio
async def test_book_context_failure_does_not_break_prompt():
    book_manager = AsyncMock()
    book_manager.get_context.side_effect = RuntimeError("vector store down")
    assembler, conversation_id, _ = build_assembler(
        book_manager,
        {BotFeature.BOOK_KNOWLEDGE.value: True},
    )

    messages, metadata = await assembler.build_prompt_and_metadata(
        conversation_id,
        user_query="query",
    )

    assert messages[0]["content"] == "System prompt"
    assert metadata["token_counts"]["book_tokens"] == 0
