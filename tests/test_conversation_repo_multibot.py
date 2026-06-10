import uuid

import pytest


@pytest.mark.asyncio
async def test_get_conversation_preserves_bot_and_last_memorized_fields(
    conversation_repo,
    sample_user,
    sample_persona,
):
    bot_id = uuid.uuid4()
    conversation = await conversation_repo.create_conversation(
        user_id=str(sample_user.id),
        persona_id=str(sample_persona.id),
        bot_id=str(bot_id),
        title="Bot scoped conversation",
    )
    memorized_message_id = uuid.uuid4()

    await conversation_repo.update_conversation(
        str(conversation.id),
        last_memorized_message_id=memorized_message_id,
    )
    updated = await conversation_repo.update_conversation(
        str(conversation.id),
        summary="updated summary",
    )

    loaded = await conversation_repo.get_conversation(str(conversation.id))

    assert updated is not None
    assert updated.bot_id == bot_id
    assert loaded is not None
    assert loaded.bot_id == bot_id
    assert loaded.last_memorized_message_id == memorized_message_id


@pytest.mark.asyncio
async def test_count_users_for_bot_counts_distinct_conversation_users(
    conversation_repo,
    sample_user,
    sample_persona,
    user_repo,
):
    bot_id = uuid.uuid4()
    second_user = await user_repo.create_user("second-user")

    await conversation_repo.create_conversation(
        user_id=str(sample_user.id),
        persona_id=str(sample_persona.id),
        bot_id=str(bot_id),
    )
    await conversation_repo.create_conversation(
        user_id=str(sample_user.id),
        persona_id=str(sample_persona.id),
        bot_id=str(bot_id),
    )
    await conversation_repo.create_conversation(
        user_id=str(second_user.id),
        persona_id=str(sample_persona.id),
        bot_id=str(bot_id),
    )
    await conversation_repo.create_conversation(
        user_id=str(second_user.id),
        persona_id=str(sample_persona.id),
        bot_id=str(uuid.uuid4()),
    )

    assert await conversation_repo.count_users_for_bot(str(bot_id)) == 2
