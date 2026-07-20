"""Resolve Telegram bot credentials at the delivery boundary."""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from collections.abc import Callable
from typing import Protocol

from token_encryption import decrypt_token


class BotRepository(Protocol):
    async def get_bot(self, bot_id: str): ...


class BotTokenResolver:
    """Resolve and briefly cache decrypted tokens by non-secret bot ID."""

    def __init__(
        self,
        bot_repo: BotRepository,
        *,
        default_token: str | None = None,
        decrypt: Callable[[str], str] = decrypt_token,
        max_cache_size: int = 50,
    ) -> None:
        if max_cache_size < 1:
            raise ValueError("max_cache_size must be positive")
        self._bot_repo = bot_repo
        self._default_token = default_token
        self._decrypt = decrypt
        self._max_cache_size = max_cache_size
        self._cache: OrderedDict[str, str] = OrderedDict()
        self._lock = asyncio.Lock()

    async def resolve(self, bot_id: str | None) -> str:
        """Return a token for a route, rejecting unknown or inactive bot IDs."""
        if bot_id is None:
            if not self._default_token:
                raise LookupError("default bot token is not configured")
            return self._default_token

        cache_key = str(bot_id)
        async with self._lock:
            cached = self._cache.get(cache_key)
            if cached is not None:
                self._cache.move_to_end(cache_key)
                return cached

            bot = await self._bot_repo.get_bot(cache_key)
            if bot is None:
                raise LookupError(f"bot ID {cache_key} was not found")
            if not getattr(bot, "is_active", True):
                raise LookupError(f"bot ID {cache_key} is inactive")

            token = self._decrypt(bot.token_encrypted)
            self._cache[cache_key] = token
            self._cache.move_to_end(cache_key)
            while len(self._cache) > self._max_cache_size:
                self._cache.popitem(last=False)
            return token

    async def invalidate(self, bot_id: str | None = None) -> None:
        """Invalidate one bot after reload/rotation, or all cached bot tokens."""
        async with self._lock:
            if bot_id is None:
                self._cache.clear()
            else:
                self._cache.pop(str(bot_id), None)
