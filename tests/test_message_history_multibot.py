import uuid

import pytest


@pytest.mark.asyncio
async def test_message_history_isolated_per_bot(storage):
    user_id = uuid.uuid4()
    bot_a = uuid.uuid4()
    bot_b = uuid.uuid4()

    await storage.message_history.save_message(user_id, "user", "hello-a", bot_id=bot_a)
    await storage.message_history.save_message(user_id, "user", "hello-b", bot_id=bot_b)

    history_a = await storage.message_history.get_user_history(user_id, limit=10, bot_id=bot_a)
    history_b = await storage.message_history.get_user_history(user_id, limit=10, bot_id=bot_b)

    assert [msg.content for msg in history_a] == ["hello-a"]
    assert [msg.content for msg in history_b] == ["hello-b"]

    deleted = await storage.message_history.clear_user_history(user_id, bot_id=bot_a)
    assert deleted == 1

    history_a_after = await storage.message_history.get_user_history(user_id, limit=10, bot_id=bot_a)
    history_b_after = await storage.message_history.get_user_history(user_id, limit=10, bot_id=bot_b)

    assert history_a_after == []
    assert [msg.content for msg in history_b_after] == ["hello-b"]
