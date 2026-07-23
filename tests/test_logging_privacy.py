"""Privacy logging guarantees for the highest-risk runtime paths.

User message text and retrieved memory content are personal chat data and must
never reach INFO-level logs. They may appear only at DEBUG, truncated.
"""

import logging

import pytest

from ai_handler import AIHandler
from memory.manager import LlamaIndexMemoryManager


class _FakeNode:
    def __init__(self, content: str, metadata: dict):
        self._content = content
        self.metadata = metadata
        self.score = 0.9

    def get_content(self) -> str:
        return self._content


class _FakeEmbeddingModel:
    async def get_embedding(self, text: str):
        return [0.1, 0.2, 0.3]


class _FakeVectorStore:
    def __init__(self, nodes):
        self._nodes = nodes

    async def query(self, *args, **kwargs):
        return self._nodes


@pytest.mark.asyncio
async def test_memory_context_content_is_not_logged_at_info(caplog):
    secret = "SECRET_MEMORY_CONFESSION_12345"
    store = _FakeVectorStore([_FakeNode(secret, {"conversation_id": "c1"})])
    manager = LlamaIndexMemoryManager(
        vector_store=store,
        embedding_model=_FakeEmbeddingModel(),
        expand_neighbors=0,
    )

    with caplog.at_level(logging.INFO, logger="memory.manager"):
        context = await manager.get_context("user-1", "any query", top_k=3)

    # The manager still returns the content to the caller...
    assert secret in context
    # ...but it must not have written that content into INFO-level logs.
    info_text = "\n".join(
        record.getMessage()
        for record in caplog.records
        if record.levelno >= logging.INFO
    )
    assert secret not in info_text


@pytest.mark.asyncio
async def test_generate_response_does_not_log_user_message_at_info(caplog):
    handler = AIHandler(prompt_assembler=None)
    handler.model_client = None  # short-circuit before any provider call

    secret = "SECRET_USER_MESSAGE_98765"
    with caplog.at_level(logging.INFO):
        result = await handler.generate_response(secret, [])

    assert result is None
    info_text = "\n".join(
        record.getMessage()
        for record in caplog.records
        if record.levelno >= logging.INFO
    )
    assert secret not in info_text
