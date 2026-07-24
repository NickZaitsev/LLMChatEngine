from uuid import NAMESPACE_OID, uuid4, uuid5

import pytest

from storage.repos import PostgresMessageHistoryRepo


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
