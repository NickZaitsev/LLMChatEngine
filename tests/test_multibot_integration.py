"""
Integration tests for multi-bot architecture.
"""
import pytest
import uuid
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime

from storage.models import Bot, UserBotSettings
from features import BotFeature, DEFAULT_FEATURE_FLAGS
from multibot_adapter import create_bot_with_config, BotConfig
from memory.llamaindex.vector_store import PgVectorStore
from llama_index.core.vector_stores import VectorStoreQuery

@pytest.fixture
def mock_bot_config():
    return BotConfig(
        id=uuid.uuid4(),
        token="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
        name="TestBot",
        personality="You are a test bot.",
        is_active=True,
        feature_flags=DEFAULT_FEATURE_FLAGS,
        llm_config={}
    )

def test_bot_model_creation():
    """Test creating a Bot model instance."""
    bot = Bot(
        id=uuid.uuid4(),
        token_encrypted="encrypted_token",
        name="TestBot",
        personality="System prompt",
        is_active=True,
        feature_flags={"feature": True},
        llm_config={"model": "gpt-4"},
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    assert bot.name == "TestBot"
    assert bot.is_active is True
    assert bot.feature_flags["feature"] is True

def test_user_bot_settings_model_creation():
    """Test creating a UserBotSettings model instance."""
    settings = UserBotSettings(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        bot_id=uuid.uuid4(),
        settings={"theme": "dark"},
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    assert settings.settings["theme"] == "dark"

@patch('config.TELEGRAM_TOKEN', 'original_token')
@patch('config.BOT_NAME', 'OriginalBot')
@patch('bot.AIGirlfriendBot')
def test_multibot_adapter(mock_bot_cls, mock_bot_config):
    """Test that the adapter correctly patches config and creates bot."""
    # Setup mock
    mock_instance = MagicMock()
    mock_bot_cls.return_value = mock_instance
    
    # Create bot with config
    bot = create_bot_with_config(mock_bot_config)
    
    # Verify bot was initialized
    assert mock_bot_cls.called
    
    # Verify attributes were set on the instance
    assert bot.bot_config == mock_bot_config
    assert bot.bot_id == mock_bot_config.id
    assert bot.feature_flags == mock_bot_config.feature_flags
    
    # Verify AI handler personality update was called
    if hasattr(bot, 'ai_handler'):
        bot.ai_handler.update_personality.assert_called_with(mock_bot_config.personality)

@pytest.mark.asyncio
async def test_vector_store_query_isolation():
    """Test that PgVectorStore adds bot_id to query filters."""
    # Mock dependencies
    mock_store = MagicMock()
    mock_store.query.return_value = MagicMock(nodes=[])
    
    with patch('llama_index.vector_stores.postgres.PGVectorStore.from_params', return_value=mock_store):
        store = PgVectorStore("postgresql://u:p@h:5432/db", "table", 1536)
        
        # Test query with bot_id
        user_id = "user123"
        bot_id = "bot456"
        query_embedding = [0.1] * 1536
        
        await store.query(query_embedding, top_k=5, user_id=user_id, bot_id=bot_id)
        
        # Verify query was called with correct filters
        call_args = mock_store.query.call_args
        query_obj = call_args[0][0]
        
        # Check filters
        filters = query_obj.filters.filters
        assert len(filters) == 2
        assert any(f.key == "user_id" and f.value == user_id for f in filters)
        assert any(f.key == "bot_id" and f.value == bot_id for f in filters)

@pytest.mark.asyncio
async def test_vector_store_query_no_bot_id():
    """Test that PgVectorStore works without bot_id (backward compatibility)."""
    # Mock dependencies
    mock_store = MagicMock()
    mock_store.query.return_value = MagicMock(nodes=[])
    
    with patch('llama_index.vector_stores.postgres.PGVectorStore.from_params', return_value=mock_store):
        store = PgVectorStore("postgresql://u:p@h:5432/db", "table", 1536)
        
        # Test query without bot_id
        user_id = "user123"
        query_embedding = [0.1] * 1536
        
        await store.query(query_embedding, top_k=5, user_id=user_id)
        
        # Verify query was called with correct filters
        call_args = mock_store.query.call_args
        query_obj = call_args[0][0]
        
        # Check filters
        filters = query_obj.filters.filters
        assert len(filters) == 1
        assert filters[0].key == "user_id"
        assert filters[0].value == user_id
