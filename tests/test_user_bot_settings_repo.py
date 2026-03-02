import pytest
from uuid import uuid4

from storage.repos import PostgresUserBotSettingsRepo


@pytest.mark.asyncio
async def test_get_or_create_user_bot_settings(session_maker, sample_user):
    repo = PostgresUserBotSettingsRepo(session_maker)
    bot_id = str(uuid4())

    settings = await repo.get_or_create_settings(str(sample_user.id), bot_id)
    loaded = await repo.get_settings(str(sample_user.id), bot_id)

    assert settings.bot_id == loaded.bot_id
    assert settings.user_id == loaded.user_id
    assert loaded.settings == {}


@pytest.mark.asyncio
async def test_update_user_bot_settings_merges_values(session_maker, sample_user):
    repo = PostgresUserBotSettingsRepo(session_maker)
    bot_id = str(uuid4())

    await repo.update_settings(str(sample_user.id), bot_id, {"language": "en"})
    updated = await repo.update_settings(str(sample_user.id), bot_id, {"notifications": False})

    assert updated.settings["language"] == "en"
    assert updated.settings["notifications"] is False
