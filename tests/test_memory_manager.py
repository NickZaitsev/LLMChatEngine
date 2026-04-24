import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from datetime import datetime
from llama_index.core.schema import TextNode

from memory.manager import LlamaIndexMemoryManager
from memory.adaptive_chunker import AdaptiveChunker, ConversationChunk
from storage.interfaces import Message


@pytest.fixture
def mock_vector_store():
    store = AsyncMock()
    store.query.return_value = []
    store.fetch_neighbors = AsyncMock(return_value=[])
    return store


@pytest.fixture
def mock_embedding_model():
    model = AsyncMock()
    model.get_embedding.return_value = [0.1] * 1024
    model.get_embeddings.return_value = [[0.1] * 1024, [0.2] * 1024]
    return model


@pytest.fixture
def memory_manager(mock_vector_store, mock_embedding_model):
    """Fixture for a fully mocked LlamaIndexMemoryManager."""
    return LlamaIndexMemoryManager(
        vector_store=mock_vector_store,
        embedding_model=mock_embedding_model,
        expand_neighbors=1,
    )


# -----------------------------------------------------------------------
# AdaptiveChunker Tests
# -----------------------------------------------------------------------

def _make_message(role, content, token_count=0, msg_id=None, created_at=None):
    """Helper to create Message-like objects for testing."""
    return Message(
        id=msg_id or uuid4(),
        conversation_id=uuid4(),
        role=role,
        content=content,
        extra_data={},
        token_count=token_count,
        created_at=created_at or datetime.now(),
    )


def test_adaptive_chunker_basic():
    """Test that a simple user+assistant pair creates one chunk."""
    chunker = AdaptiveChunker(max_messages=4, target_tokens=300)
    messages = [
        _make_message("user", "Hello!", token_count=5),
        _make_message("assistant", "Hi there!", token_count=5),
    ]
    chunks = chunker.create_chunks(messages)

    assert len(chunks) == 1
    assert "user: Hello!" in chunks[0].text
    assert "assistant: Hi there!" in chunks[0].text
    assert len(chunks[0].message_ids) == 2


def test_adaptive_chunker_max_messages():
    """Test that chunks respect max_messages limit."""
    chunker = AdaptiveChunker(max_messages=4, target_tokens=9999)
    messages = [
        _make_message("user", "Message 1", token_count=10),
        _make_message("assistant", "Reply 1", token_count=10),
        _make_message("user", "Message 2", token_count=10),
        _make_message("assistant", "Reply 2", token_count=10),
        _make_message("user", "Message 3", token_count=10),
        _make_message("assistant", "Reply 3", token_count=10),
    ]
    chunks = chunker.create_chunks(messages)

    # 6 messages = 3 turns; max 4 messages = 2 turns per chunk
    assert len(chunks) == 2
    assert len(chunks[0].message_ids) == 4  # 2 turns
    assert len(chunks[1].message_ids) == 2  # 1 turn


def test_adaptive_chunker_token_limit():
    """Test that chunks respect target_tokens limit."""
    chunker = AdaptiveChunker(max_messages=10, target_tokens=50)
    messages = [
        _make_message("user", "Short", token_count=10),
        _make_message("assistant", "Short reply", token_count=10),
        _make_message("user", "Another short", token_count=10),
        _make_message("assistant", "Another reply", token_count=10),
        _make_message("user", "Third", token_count=10),
        _make_message("assistant", "Third reply", token_count=10),
    ]
    chunks = chunker.create_chunks(messages)

    # Each turn = 20 tokens; target = 50; so 2 turns per chunk
    assert len(chunks) >= 2  # At least 2 chunks


def test_adaptive_chunker_oversized_turn():
    """Test that a single oversized turn gets its own chunk."""
    chunker = AdaptiveChunker(max_messages=4, target_tokens=100)
    messages = [
        _make_message("user", "x" * 1000, token_count=300),
        _make_message("assistant", "y" * 1000, token_count=300),
    ]
    chunks = chunker.create_chunks(messages)

    # Single oversized turn should still be a valid chunk
    assert len(chunks) == 1
    assert chunks[0].token_count == 600


def test_adaptive_chunker_orphan_messages():
    """Test that unpaired messages are skipped."""
    chunker = AdaptiveChunker(max_messages=4, target_tokens=300)
    messages = [
        _make_message("user", "Hello!"),
        # Missing assistant reply
        _make_message("user", "Are you there?"),
        _make_message("assistant", "Yes, I'm here!"),
    ]
    chunks = chunker.create_chunks(messages)

    # Only the second user+assistant pair should form a chunk
    assert len(chunks) == 1
    assert "Are you there?" in chunks[0].text
    assert "Yes, I'm here!" in chunks[0].text


def test_adaptive_chunker_empty():
    """Test with no messages."""
    chunker = AdaptiveChunker(max_messages=4, target_tokens=300)
    assert chunker.create_chunks([]) == []


# -----------------------------------------------------------------------
# LlamaIndexMemoryManager Tests
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_store_conversation_chunks(memory_manager, mock_embedding_model, mock_vector_store):
    """Test storing conversation chunks with batch embedding."""
    now = datetime.now()
    chunks = [
        ConversationChunk(
            text="user: Hello\nassistant: Hi",
            message_ids=["id1", "id2"],
            token_count=10,
            chunk_index=0,
            first_timestamp=now,
            last_timestamp=now,
        ),
        ConversationChunk(
            text="user: How are you?\nassistant: Good!",
            message_ids=["id3", "id4"],
            token_count=15,
            chunk_index=1,
            first_timestamp=now,
            last_timestamp=now,
        ),
    ]

    stored = await memory_manager.store_conversation_chunks(
        user_id="user123",
        chunks=chunks,
        conversation_id="conv123",
    )

    assert stored == 2
    mock_embedding_model.get_embeddings.assert_called_once()
    mock_vector_store.upsert.assert_called_once()

    # Check the nodes passed to upsert
    nodes = mock_vector_store.upsert.call_args[0][0]
    assert len(nodes) == 2
    assert nodes[0].metadata["user_id"] == "user123"
    assert nodes[0].metadata["conversation_id"] == "conv123"
    assert nodes[0].metadata["chunk_index"] == "0"


@pytest.mark.asyncio
async def test_get_context(memory_manager, mock_embedding_model, mock_vector_store):
    """Test getting context for a query."""
    user_id = "user123"
    query = "What was the test message?"

    # Mock the vector store to return nodes without conversation metadata
    # (simulates old-format entries)
    mock_nodes = [
        TextNode(text="First part of context.", metadata={}),
        TextNode(text="Second part of context.", metadata={})
    ]
    mock_vector_store.query.return_value = mock_nodes

    context = await memory_manager.get_context(user_id, query, top_k=2)

    mock_embedding_model.get_embedding.assert_called_once_with(query)

    assert "First part of context." in context
    assert "Second part of context." in context


@pytest.mark.asyncio
async def test_get_context_with_neighbor_expansion(memory_manager, mock_embedding_model, mock_vector_store):
    """Test that neighbor expansion fetches adjacent chunks."""
    user_id = "user123"
    query = "pizza"

    # Matched node has conversation metadata
    mock_nodes = [
        TextNode(
            text="user: I love pizza\nassistant: What kind?",
            metadata={"conversation_id": "conv1", "chunk_index": "1", "first_timestamp": "2024-01-01"},
        ),
    ]
    mock_vector_store.query.return_value = mock_nodes

    # Neighbors return expanded context
    mock_vector_store.fetch_neighbors.return_value = [
        {"text": "user: Hi\nassistant: Hello!", "first_timestamp": "2024-01-01T00:00"},
        {"text": "user: I love pizza\nassistant: What kind?", "first_timestamp": "2024-01-01T00:01"},
        {"text": "user: Margherita\nassistant: Great choice!", "first_timestamp": "2024-01-01T00:02"},
    ]

    context = await memory_manager.get_context(user_id, query, top_k=1)

    mock_vector_store.fetch_neighbors.assert_called_once_with(
        conversation_id="conv1",
        chunk_index=1,
        user_id="user123",
        radius=1,
    )
    assert "pizza" in context
    assert "Margherita" in context


@pytest.mark.asyncio
async def test_clear_memories(memory_manager, mock_vector_store):
    """Test clearing memories for a user."""
    user_id = "user123"

    await memory_manager.clear_memories(user_id)

    mock_vector_store.clear.assert_called_once_with(user_id, bot_id=None)