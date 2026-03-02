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
from bot_manager import BotManager
from admin_bot import AdminBot
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
    assert bot.bot_name == mock_bot_config.name
    assert bot.bot_token == mock_bot_config.token
    assert bot.feature_flags == mock_bot_config.feature_flags
    
    # Verify AI handler personality update was called
    if hasattr(bot, 'ai_handler'):
        bot.ai_handler.update_personality.assert_called_with(mock_bot_config.personality)
        bot.ai_handler.apply_llm_config.assert_called_once_with(mock_bot_config.llm_config)

@patch('telegram.ext.filters')
@patch('telegram.ext.CallbackQueryHandler')
@patch('telegram.ext.MessageHandler')
@patch('telegram.ext.CommandHandler')
@patch('telegram.ext.Application.builder')
def test_build_application_for_bot_registers_clear_watcher(
    mock_builder,
    mock_command_handler,
    mock_message_handler,
    mock_callback_handler,
    mock_filters,
):
    """Test that multi-bot application wiring includes the /clear confirmation watcher."""
    from multibot_adapter import build_application_for_bot

    mock_app = MagicMock()
    mock_builder.return_value.token.return_value.build.return_value = mock_app

    mock_filters.ALL = MagicMock(name="ALL")
    mock_filters.TEXT = MagicMock(name="TEXT")
    mock_filters.COMMAND = MagicMock(name="COMMAND")
    mock_filters.PHOTO = MagicMock(name="PHOTO")
    mock_filters.VOICE = MagicMock(name="VOICE")
    mock_filters.TEXT.__and__.return_value = mock_filters.TEXT
    mock_filters.TEXT.__invert__.return_value = mock_filters.COMMAND

    class StubBot:
        def __init__(self):
            self._monitor_pending_clear = MagicMock()
            self.start_command = MagicMock()
            self.help_command = MagicMock()
            self.clear_command = MagicMock()
            self.ok_command = MagicMock()
            self.stats_command = MagicMock()
            self.debug_command = MagicMock()
            self.status_command = MagicMock()
            self.personality_command = MagicMock()
            self.stop_command = MagicMock()
            self.reset_command = MagicMock()
            self.ping_command = MagicMock()
            self.deps_command = MagicMock()
            self.handle_callback_query = MagicMock()
            self.handle_message = MagicMock()
            self.handle_photo = MagicMock()
            self.handle_voice = MagicMock()
            self.error_handler = MagicMock()

    mock_bot = StubBot()

    build_application_for_bot(mock_bot, "token")

    first_add_handler_call = mock_app.add_handler.call_args_list[0]
    assert first_add_handler_call.kwargs["group"] == -1
    mock_message_handler.assert_any_call(mock_filters.ALL, mock_bot._monitor_pending_clear)

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

@pytest.mark.asyncio
async def test_bot_manager_reload_updates_runtime_fields_without_restart(mock_bot_config):
    """Test that non-token config changes update the running bot in place."""
    manager = BotManager("postgresql://u:p@h:5432/db")
    running_bot = MagicMock()
    manager.bots[mock_bot_config.id] = running_bot
    manager.bot_configs[mock_bot_config.id] = mock_bot_config

    updated = BotConfig(
        id=mock_bot_config.id,
        token=mock_bot_config.token,
        name="RenamedBot",
        personality="Updated personality",
        is_active=True,
        feature_flags={"memory": True},
        llm_config={"provider": "azure"}
    )

    manager._load_single_bot_config = AsyncMock(side_effect=lambda bot_id: manager.bot_configs.__setitem__(bot_id, updated))
    manager.stop_bot = AsyncMock()
    manager.start_bot = AsyncMock()

    await manager.reload_bot_config(mock_bot_config.id)

    assert running_bot.bot_name == "RenamedBot"
    assert running_bot.bot_token == mock_bot_config.token
    assert running_bot.feature_flags == {"memory": True}
    running_bot.ai_handler.update_personality.assert_called_once_with("Updated personality")
    running_bot.ai_handler.apply_llm_config.assert_called_once_with({"provider": "azure"})
    manager.stop_bot.assert_not_called()
    manager.start_bot.assert_not_called()

@pytest.mark.asyncio
async def test_bot_manager_reload_restarts_when_token_changes(mock_bot_config):
    """Test that token changes trigger a full bot restart."""
    manager = BotManager("postgresql://u:p@h:5432/db")
    running_bot = MagicMock()
    manager.bots[mock_bot_config.id] = running_bot
    manager.bot_configs[mock_bot_config.id] = mock_bot_config

    updated = BotConfig(
        id=mock_bot_config.id,
        token="new-token",
        name=mock_bot_config.name,
        personality="Updated personality",
        is_active=True,
        feature_flags=mock_bot_config.feature_flags,
        llm_config={}
    )

    manager._load_single_bot_config = AsyncMock(side_effect=lambda bot_id: manager.bot_configs.__setitem__(bot_id, updated))
    manager.stop_bot = AsyncMock()
    manager.start_bot = AsyncMock()

    await manager.reload_bot_config(mock_bot_config.id)

    manager.stop_bot.assert_awaited_once_with(mock_bot_config.id)
    manager.start_bot.assert_awaited_once_with(mock_bot_config.id)

def test_admin_bot_pending_data_is_scoped_per_chat():
    """Test that admin pending state is isolated by chat, not only by user."""
    admin = AdminBot("token", [1], "postgresql://u:p@h:5432/db")

    update_a = MagicMock()
    update_a.effective_user.id = 1
    update_a.effective_chat.id = 100

    update_b = MagicMock()
    update_b.effective_user.id = 1
    update_b.effective_chat.id = 200

    admin._pending_bot_data[admin._session_key(update_a)] = {"flow": "addbot"}
    admin._pending_bot_data[admin._session_key(update_b)] = {"flow": "setprompt"}

    assert admin._pending_bot_data[(1, 100)] == {"flow": "addbot"}
    assert admin._pending_bot_data[(1, 200)] == {"flow": "setprompt"}
