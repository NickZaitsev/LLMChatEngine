import pytest


@pytest.mark.asyncio
async def test_bot_repo_crud_and_status_updates(storage):
    bot = await storage.bots.create_bot(
        token_encrypted="encrypted-token",
        name="TestBot",
        personality="Initial personality",
        feature_flags={"memory": True},
        llm_config={"temperature": 0.4},
    )

    loaded = await storage.bots.get_bot(str(bot.id))
    assert loaded is not None
    assert loaded.name == "TestBot"
    assert loaded.feature_flags == {"memory": True}
    assert loaded.llm_config == {"temperature": 0.4}

    active_bots = await storage.bots.list_bots(is_active=True)
    assert [active.id for active in active_bots] == [bot.id]

    updated = await storage.bots.update_personality(str(bot.id), "Updated personality")
    assert updated.personality == "Updated personality"

    flagged = await storage.bots.update_flags(str(bot.id), {"memory": False, "voice_messages": True})
    assert flagged.feature_flags["memory"] is False
    assert flagged.feature_flags["voice_messages"] is True

    settings = await storage.bots.get_personality_and_flags(str(bot.id))
    assert settings == ("Updated personality", {"memory": False, "voice_messages": True})

    inactive = await storage.bots.set_active(str(bot.id), False)
    assert inactive.is_active is False
    assert await storage.bots.list_bots(is_active=True) == []


@pytest.mark.asyncio
async def test_bot_repo_delete_deactivates_bot(storage):
    bot = await storage.bots.create_bot(
        token_encrypted="encrypted-token",
        name="DeleteMe",
        personality="Personality",
    )

    assert await storage.bots.delete_bot(str(bot.id)) is True

    loaded = await storage.bots.get_bot(str(bot.id))
    assert loaded is not None
    assert loaded.is_active is False
