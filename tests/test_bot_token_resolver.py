from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from messaging.token_resolver import BotTokenResolver


@pytest.mark.asyncio
async def test_resolver_caches_by_bot_id_and_decrypts_once():
    repo = SimpleNamespace(get_bot=AsyncMock(return_value=SimpleNamespace(token_encrypted="cipher")))
    decrypt = Mock(return_value="plain-token")
    resolver = BotTokenResolver(repo, default_token="default", decrypt=decrypt, max_cache_size=2)

    assert await resolver.resolve("bot-1") == "plain-token"
    assert await resolver.resolve("bot-1") == "plain-token"

    repo.get_bot.assert_awaited_once_with("bot-1")
    decrypt.assert_called_once_with("cipher")


@pytest.mark.asyncio
async def test_resolver_default_route_is_lazy_and_unknown_bot_is_rejected():
    repo = SimpleNamespace(get_bot=AsyncMock(return_value=None))
    resolver = BotTokenResolver(repo, default_token="default-token", decrypt=Mock())

    assert await resolver.resolve(None) == "default-token"
    repo.get_bot.assert_not_awaited()
    with pytest.raises(LookupError, match="not found"):
        await resolver.resolve("missing")


@pytest.mark.asyncio
async def test_resolver_invalidation_forces_reload_after_rotation():
    repo = SimpleNamespace(
        get_bot=AsyncMock(
            side_effect=[
                SimpleNamespace(token_encrypted="old-cipher"),
                SimpleNamespace(token_encrypted="new-cipher"),
            ]
        )
    )
    resolver = BotTokenResolver(repo, decrypt=lambda value: value.replace("cipher", "token"))

    assert await resolver.resolve("bot-1") == "old-token"
    await resolver.invalidate("bot-1")
    assert await resolver.resolve("bot-1") == "new-token"
