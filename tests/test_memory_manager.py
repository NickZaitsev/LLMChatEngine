import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from llama_index.core.schema import TextNode

from memory.manager import LlamaIndexMemoryManager
from storage.interfaces import Message

@pytest.fixture
def mock_vector_store():
    return AsyncMock()

@pytest.fixture
def mock_embedding_model():
    model = AsyncMock()
    model.get_embedding.return_value = [0.1] * 1024
    return model

@pytest.fixture
def mock_summarization_model():
    return AsyncMock()

@pytest.fixture
def mock_message_repo():
    return AsyncMock()

@pytest.fixture
def mock_conversation_repo():
    return AsyncMock()

@pytest.fixture
def mock_user_repo():
    return AsyncMock()

@pytest.fixture
def memory_manager(mock_vector_store, mock_embedding_model, mock_summarization_model, mock_message_repo, mock_conversation_repo, mock_user_repo):
    """Fixture for a fully mocked LlamaIndexMemoryManager."""
    return LlamaIndexMemoryManager(
        vector_store=mock_vector_store,
        embedding_model=mock_embedding_model,
        summarization_model=mock_summarization_model,
        message_repo=mock_message_repo,
        conversation_repo=mock_conversation_repo,
        user_repo=mock_user_repo
    )

@pytest.mark.asyncio
async def test_add_message(memory_manager, mock_embedding_model, mock_vector_store):
    """Test adding a message to the memory."""
    user_id = "user123"
    message = "This is a test message."
    
    await memory_manager.add_message(user_id, message)
    
    mock_embedding_model.get_embedding.assert_called_once_with(message)
    mock_vector_store.upsert.assert_called_once()
    
    # Check the node passed to upsert
    call_args = mock_vector_store.upsert.call_args[0][0]
    assert len(call_args) == 1
    node = call_args[0]
    assert isinstance(node, TextNode)
    assert node.text == message
    assert node.metadata["user_id"] == user_id

@pytest.mark.asyncio
async def test_get_context(memory_manager, mock_embedding_model, mock_vector_store):
    """Test getting context for a query."""
    user_id = "user123"
    query = "What was the test message?"
    
    # Mock the vector store to return some nodes
    mock_nodes = [
        TextNode(text="First part of context."),
        TextNode(text="Second part of context.")
    ]
    mock_vector_store.query.return_value = mock_nodes
    
    context = await memory_manager.get_context(user_id, query, top_k=2)
    
    mock_embedding_model.get_embedding.assert_called_once_with(query)
    mock_vector_store.query.assert_called_once_with([0.1] * 1024, 2, user_id)
    
    assert "First part of context." in context
    assert "Second part of context." in context

@pytest.mark.asyncio
async def test_trigger_summarization(memory_manager, mock_user_repo, mock_conversation_repo, mock_message_repo, mock_summarization_model):
    """Test triggering summarization for a user."""
    user_id = "user123"
    conversation_id = str(uuid4())
    
    # Mock the database repos
    mock_user = MagicMock()
    mock_user.id = str(uuid4())
    mock_user_repo.get_user_by_username.return_value = mock_user
    
    mock_conversation = MagicMock()
    mock_conversation.id = conversation_id
    mock_conversation_repo.list_conversations.return_value = [mock_conversation]
    
    mock_messages = [
        Message(id=uuid4(), conversation_id=conversation_id, role="user", content="Hello", created_at="2023-01-01T12:00:00Z"),
        Message(id=uuid4(), conversation_id=conversation_id, role="assistant", content="Hi there", created_at="2023-01-01T12:01:00Z")
    ]
    mock_message_repo.list_messages.return_value = mock_messages
    
    # Mock the summarizer
    mock_summarization_model.summarize.return_value = "This is a summary."
    
    with patch.object(memory_manager, 'add_message', new_callable=AsyncMock) as mock_add_message:
        await memory_manager.trigger_summarization(user_id, "prompt_template")
        
        mock_summarization_model.summarize.assert_called_once_with(
            "Hello\nHi there", "prompt_template", user_id=user_id
        )
        mock_add_message.assert_called_once_with(user_id, "Summary: This is a summary.")

@pytest.mark.asyncio
async def test_clear_memories(memory_manager, mock_vector_store):
    """Test clearing memories for a user."""
    user_id = "user123"
    
    await memory_manager.clear_memories(user_id)
    
    mock_vector_store.clear.assert_called_once_with(user_id)