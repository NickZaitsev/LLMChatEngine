from uuid import NAMESPACE_OID, uuid4, uuid5

import pytest

from storage.repos import PostgresMessageHistoryRepo
from storage_conversation_manager import PostgresConversationManager


@pytest.mark.asyncio
async def test_message_history_repo_derives_uuid_for_telegram_user(session_maker):
    repo = PostgresMessageHistoryRepo(session_maker)

    message = await repo.save_message(123456, "user", "hello")

    assert message.user_id == uuid5(NAMESPACE_OID, "telegram_user_123456")
    assert message.role == "user"
    assert message.content == "hello"


@pytest.mark.asyncio
async def test_message_history_repo_accepts_existing_uuid_for_legacy_callers(session_maker):
    repo = PostgresMessageHistoryRepo(session_maker)
    user_id = uuid4()

    message = await repo.save_message(user_id, "assistant", "hello")

    assert message.user_id == user_id


@pytest.mark.asyncio
async def test_conversation_manager_passes_raw_telegram_id_to_message_history():
    manager = PostgresConversationManager("sqlite+aiosqlite:///:memory:", use_pgvector=False)
    message_history = type(
        "MessageHistory",
        (),
        {"save_message": None},
    )()

    calls = []

    async def save_message(user_id, role, content, bot_id=None):
        calls.append((user_id, role, content, bot_id))
        return None

    message_history.save_message = save_message
    manager.storage = type("Storage", (), {"message_history": message_history})()
    bot_id = uuid4()

    await manager.save_message_to_history(123456, "user", "hello", bot_id=bot_id)

    assert calls == [(123456, "user", "hello", bot_id)]
