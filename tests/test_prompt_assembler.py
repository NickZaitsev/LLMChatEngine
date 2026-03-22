"""
Focused tests for PromptAssembler using the current repository and memory APIs.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

import config
from prompt.assembler import PromptAssembler, TokenCounter
from storage.interfaces import Conversation, Message, User


class MockTokenizer:
    """Small deterministic tokenizer for unit tests."""

    def encode(self, text: str):
        return list(range(max(1, len(text) // 4)))

    def count_tokens(self, text: str) -> int:
        if not text:
            return 0
        return max(1, len(text) // 4)


@pytest.fixture
def mock_tokenizer():
    return MockTokenizer()


@pytest.fixture
def sample_conversation():
    return Conversation(
        id=uuid4(),
        user_id=uuid4(),
        persona_id=uuid4(),
        title="Test Conversation",
        extra_data={},
        created_at=datetime.now(timezone.utc),
        summary="The user likes pizza and hiking.",
        last_summarized_message_id=None,
        last_memorized_message_id=None,
    )


@pytest.fixture
def sample_user():
    return User(
        id=uuid4(),
        username="test_user",
        extra_data={},
    )


@pytest.fixture
def sample_messages(sample_conversation):
    return [
        Message(
            id=uuid4(),
            conversation_id=sample_conversation.id,
            role="user",
            content="Hello, how are you?",
            extra_data={},
            token_count=6,
            created_at=datetime.now(timezone.utc),
        ),
        Message(
            id=uuid4(),
            conversation_id=sample_conversation.id,
            role="assistant",
            content="I'm doing great! How can I help you today?",
            extra_data={},
            token_count=12,
            created_at=datetime.now(timezone.utc),
        ),
    ]


@pytest.fixture
def mock_message_repo(sample_messages):
    repo = AsyncMock()
    repo.fetch_active_messages = AsyncMock(return_value=sample_messages)
    repo.get_last_user_message = AsyncMock(return_value=sample_messages[0])
    repo.count_active_messages = AsyncMock(return_value=len(sample_messages))
    return repo


@pytest.fixture
def mock_memory_manager():
    manager = AsyncMock()
    manager.get_context = AsyncMock(
        return_value="User prefers Italian food.\nUser enjoys outdoor activities."
    )
    return manager


@pytest.fixture
def mock_conversation_repo(sample_conversation):
    repo = AsyncMock()
    repo.get_conversation = AsyncMock(return_value=sample_conversation)
    return repo


@pytest.fixture
def mock_user_repo(sample_user):
    repo = AsyncMock()
    repo.get_user = AsyncMock(return_value=sample_user)
    return repo


@pytest.fixture
def prompt_assembler(
    mock_message_repo,
    mock_memory_manager,
    mock_conversation_repo,
    mock_user_repo,
    mock_tokenizer,
):
    return PromptAssembler(
        message_repo=mock_message_repo,
        memory_manager=mock_memory_manager,
        conversation_repo=mock_conversation_repo,
        user_repo=mock_user_repo,
        tokenizer=mock_tokenizer,
        config={
            "max_memory_items": 3,
            "memory_token_budget_ratio": 0.4,
            "truncation_length": 50,
            "include_system_template": True,
        },
    )


class TestTokenCounter:
    def test_token_counter_with_tokenizer(self, mock_tokenizer):
        counter = TokenCounter(mock_tokenizer)
        assert counter.count_tokens("Hello world test") == 4

    def test_token_counter_fallback(self):
        counter = TokenCounter(None, auto_tiktoken=False)
        assert counter.count_tokens("Hello world test") == 4

    def test_token_counter_empty_text(self, mock_tokenizer):
        counter = TokenCounter(mock_tokenizer)
        assert counter.count_tokens("") == 0
        assert counter.count_tokens(None) == 0


class TestPromptAssembler:
    @pytest.mark.asyncio
    async def test_build_prompt_includes_system_summary_memory_and_history(
        self,
        prompt_assembler,
        sample_conversation,
        sample_messages,
    ):
        messages = await prompt_assembler.build_prompt(
            conversation_id=str(sample_conversation.id),
            reply_token_budget=500,
            history_budget=7500,
            user_query="Do you remember what I like?",
        )

        assert messages[0]["role"] == "system"
        assert config.BOT_PERSONALITY in messages[0]["content"]
        assert any("summary of the conversation" in msg["content"] for msg in messages)
        assert any("### Memory Context" in msg["content"] for msg in messages)
        assert messages[-2]["content"] == sample_messages[0].content
        assert messages[-1]["content"] == sample_messages[1].content

        prompt_assembler.memory_manager.get_context.assert_awaited_once()
        prompt_assembler.message_repo.fetch_active_messages.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_build_prompt_and_metadata_tracks_token_buckets(
        self,
        prompt_assembler,
        sample_conversation,
    ):
        messages, metadata = await prompt_assembler.build_prompt_and_metadata(
            conversation_id=str(sample_conversation.id),
            reply_token_budget=300,
            history_budget=100,
            user_query="pizza",
        )

        assert messages
        assert metadata["conversation_id"] == str(sample_conversation.id)
        assert metadata["token_counts"]["reply_reserved"] == 300
        assert metadata["token_counts"]["system_tokens"] > 0
        assert metadata["token_counts"]["memory_tokens"] >= 0
        assert metadata["token_counts"]["history_tokens"] >= 0
        assert metadata["total_tokens"] == sum(metadata["token_counts"].values())

    @pytest.mark.asyncio
    async def test_memory_budget_truncates_context(
        self,
        prompt_assembler,
        sample_conversation,
    ):
        prompt_assembler.memory_manager.get_context.return_value = (
            "alpha\nbeta\ngamma\ndelta\nepsilon\nzeta"
        )

        messages, metadata = await prompt_assembler.build_prompt_and_metadata(
            conversation_id=str(sample_conversation.id),
            history_budget=20,
            user_query="small budget",
        )

        memory_messages = [
            message for message in messages if message["content"].startswith("### Memory Context")
        ]
        assert memory_messages
        assert metadata["token_counts"]["memory_tokens"] <= int(20 * 0.4)

    @pytest.mark.asyncio
    async def test_long_history_messages_are_truncated(
        self,
        prompt_assembler,
        mock_message_repo,
        sample_conversation,
    ):
        long_message = Message(
            id=uuid4(),
            conversation_id=sample_conversation.id,
            role="user",
            content="A" * 200,
            extra_data={},
            token_count=50,
            created_at=datetime.now(timezone.utc),
        )
        mock_message_repo.fetch_active_messages.return_value = [long_message]

        messages, metadata = await prompt_assembler.build_prompt_and_metadata(
            conversation_id=str(sample_conversation.id),
            user_query="hello",
        )

        assert any("(truncated)" in message["content"] for message in messages)
        assert str(long_message.id) in metadata["truncated_message_ids"]

    @pytest.mark.asyncio
    async def test_non_uuid_conversation_ids_are_supported(
        self,
        prompt_assembler,
        mock_conversation_repo,
    ):
        mock_conversation_repo.get_conversation.return_value = None

        messages, metadata = await prompt_assembler.build_prompt_and_metadata(
            conversation_id="external-conversation-key",
        )

        assert messages[0]["role"] == "system"
        assert metadata["conversation_id"] == "external-conversation-key"

    @pytest.mark.asyncio
    async def test_empty_conversation_id_is_rejected(self, prompt_assembler):
        with pytest.raises(ValueError, match="conversation_id cannot be empty"):
            await prompt_assembler.build_prompt("")

    @pytest.mark.asyncio
    async def test_system_template_can_be_disabled(
        self,
        mock_message_repo,
        mock_memory_manager,
        mock_conversation_repo,
        mock_user_repo,
        mock_tokenizer,
        sample_conversation,
    ):
        assembler = PromptAssembler(
            message_repo=mock_message_repo,
            memory_manager=mock_memory_manager,
            conversation_repo=mock_conversation_repo,
            user_repo=mock_user_repo,
            tokenizer=mock_tokenizer,
            config={"include_system_template": False},
        )

        messages, metadata = await assembler.build_prompt_and_metadata(
            conversation_id=str(sample_conversation.id),
            user_query="hello",
        )

        assert not any(
            message["role"] == "system" and config.BOT_PERSONALITY in message["content"]
            for message in messages
        )
        assert metadata["token_counts"]["system_tokens"] >= 0

    @pytest.mark.asyncio
    async def test_missing_conversation_skips_memory_lookup(
        self,
        prompt_assembler,
        mock_conversation_repo,
    ):
        mock_conversation_repo.get_conversation.return_value = None

        messages, metadata = await prompt_assembler.build_prompt_and_metadata(
            conversation_id="conversation-without-db-row",
        )

        assert messages[0]["role"] == "system"
        assert metadata["included_memory_ids"] == []
        prompt_assembler.memory_manager.get_context.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_active_message_count_uses_repositories(
        self,
        prompt_assembler,
        sample_conversation,
    ):
        count = await prompt_assembler.get_active_message_count(str(sample_conversation.id))

        assert count == 2
        prompt_assembler.message_repo.count_active_messages.assert_awaited_once_with(
            str(sample_conversation.id),
            sample_conversation.last_summarized_message_id,
        )
