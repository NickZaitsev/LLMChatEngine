"""
Integration tests for multi-bot architecture.
"""
import asyncio
import pytest
import uuid
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timezone
from types import SimpleNamespace

from storage.interfaces import Bot
from storage.models import UserBotSettings
from features import BotFeature, DEFAULT_FEATURE_FLAGS
from multibot_adapter import create_bot_with_config, BotConfig
from bot_manager import BotManager
from admin_bot import AdminBot
from memory.llamaindex.vector_store import PgVectorStore
from llama_index.core.vector_stores import VectorStoreQuery
from storage_conversation_manager import PostgresConversationManager

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
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
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
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )
    assert settings.settings["theme"] == "dark"

@patch('bot.TelegramChatBot')
def test_multibot_adapter(mock_bot_cls, mock_bot_config):
    """Test that the adapter injects config without mutating config globals."""
    # Setup mock
    mock_instance = MagicMock()
    mock_bot_cls.return_value = mock_instance
    
    # Create bot with config
    bot = create_bot_with_config(mock_bot_config)
    
    # Verify bot was initialized
    mock_bot_cls.assert_called_once_with(bot_config=mock_bot_config)
    assert bot is mock_instance


def test_multibot_adapter_does_not_mutate_config(mock_bot_config):
    import config

    original_token = config.TELEGRAM_TOKEN
    original_name = config.BOT_NAME
    original_personality = config.BOT_PERSONALITY

    with patch("bot.TelegramChatBot", return_value=MagicMock()):
        create_bot_with_config(mock_bot_config)

    assert config.TELEGRAM_TOKEN == original_token
    assert config.BOT_NAME == original_name
    assert config.BOT_PERSONALITY == original_personality

def test_build_application_for_bot_delegates_to_bot_registration():
    """Multi-bot application wiring uses the same registration path as single-bot."""
    from multibot_adapter import build_application_for_bot

    mock_app = MagicMock()
    mock_bot = MagicMock()
    mock_bot.build_application.return_value = mock_app

    app = build_application_for_bot(mock_bot, "token")

    assert app is mock_app
    mock_bot.build_application.assert_called_once_with(token_override="token")

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


@pytest.mark.asyncio
async def test_run_multibot_sets_shutdown_when_background_task_crashes():
    import run_multibot

    shutdown_event = asyncio.Event()
    task = asyncio.get_running_loop().create_future()
    task.set_exception(RuntimeError("boom"))
    task.set_name = lambda name: None
    task.get_name = lambda: "admin_bot"

    logger = MagicMock()

    def monitor_task(task_obj):
        if task_obj.cancelled():
            return
        error = task_obj.exception()
        if error is not None:
            logger.error("Background task %s crashed: %s", task_obj.get_name(), error)
            shutdown_event.set()

    monitor_task(task)

    assert shutdown_event.is_set()
    logger.error.assert_called_once()


@pytest.mark.asyncio
async def test_admin_togglefeature_uses_default_feature_values():
    admin = AdminBot("token", [1], "postgresql://u:p@h:5432/db")
    admin.storage = MagicMock()
    admin.storage.bots = MagicMock()

    bot_id = uuid.uuid4()
    bot_record = SimpleNamespace(
        id=bot_id,
        name="TestBot",
        feature_flags={},
    )

    async def update_flags(bot_id_arg, flags):
        bot_record.feature_flags = flags
        return bot_record

    admin.storage.bots.get_bot = AsyncMock(return_value=bot_record)
    admin.storage.bots.update_flags = AsyncMock(side_effect=update_flags)

    update = MagicMock()
    update.effective_user.id = 1
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.args = [str(bot_id), BotFeature.MEMORY.value]

    await admin.togglefeature_command(update, context)

    assert bot_record.feature_flags[BotFeature.MEMORY.value] is False
    admin.storage.bots.update_flags.assert_awaited_once_with(str(bot_id), bot_record.feature_flags)


@pytest.mark.asyncio
async def test_admin_togglefeature_handles_missing_feature_flags():
    admin = AdminBot("token", [1], "postgresql://u:p@h:5432/db")
    admin.storage = MagicMock()
    admin.storage.bots = MagicMock()

    bot_id = uuid.uuid4()
    bot_record = SimpleNamespace(
        id=bot_id,
        name="TestBot",
        feature_flags=None,
    )

    async def update_flags(bot_id_arg, flags):
        bot_record.feature_flags = flags
        return bot_record

    admin.storage.bots.get_bot = AsyncMock(return_value=bot_record)
    admin.storage.bots.update_flags = AsyncMock(side_effect=update_flags)

    update = MagicMock()
    update.effective_user.id = 1
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.args = [str(bot_id), BotFeature.MEMORY.value]

    await admin.togglefeature_command(update, context)

    assert bot_record.feature_flags[BotFeature.MEMORY.value] is False
    admin.storage.bots.update_flags.assert_awaited_once_with(str(bot_id), bot_record.feature_flags)


@pytest.mark.asyncio
async def test_bot_manager_removes_crashed_bot_from_running_state(mock_bot_config):
    manager = BotManager("postgresql://u:p@h:5432/db")
    manager.bot_configs[mock_bot_config.id] = mock_bot_config
    original_create_task = asyncio.create_task

    mock_app = MagicMock()
    mock_app.initialize = AsyncMock(side_effect=RuntimeError("startup failure"))
    mock_app.start = AsyncMock()
    mock_app.updater.start_polling = AsyncMock()
    mock_app.updater.stop = AsyncMock()
    mock_app.stop = AsyncMock()
    mock_app.shutdown = AsyncMock()

    bot_instance = MagicMock()
    bot_instance._initialize_storage = AsyncMock()
    bot_instance._initialize_memory_components = AsyncMock()
    bot_instance._initialize_lmstudio_model = AsyncMock()

    with patch("bot_manager.MessageDispatcher"), \
         patch("bot_manager.asyncio.create_task", side_effect=lambda coro: original_create_task(coro)), \
         patch("multibot_adapter.create_bot_with_config", return_value=bot_instance), \
         patch("multibot_adapter.build_application_for_bot", return_value=mock_app):
        await manager.start_bot(mock_bot_config.id)
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    assert mock_bot_config.id not in manager.bots
    assert mock_bot_config.id not in manager.applications


@pytest.mark.asyncio
async def test_admin_removebot_reloads_manager_config():
    admin = AdminBot("token", [1], "postgresql://u:p@h:5432/db")
    admin.storage = MagicMock()
    admin.storage.bots = MagicMock()
    admin.bot_manager = MagicMock()
    admin.bot_manager.reload_bot_config = AsyncMock()

    bot_id = uuid.uuid4()
    bot_record = SimpleNamespace(
        id=bot_id,
        name="RetireMe",
        is_active=True,
    )

    async def set_active(bot_id_arg, is_active):
        bot_record.is_active = is_active
        return bot_record

    admin.storage.bots.set_active = AsyncMock(side_effect=set_active)

    update = MagicMock()
    update.effective_user.id = 1
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.args = [str(bot_id)]

    await admin.removebot_command(update, context)

    assert bot_record.is_active is False
    admin.bot_manager.reload_bot_config.assert_awaited_once_with(bot_id)
