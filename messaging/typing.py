"""Typing-indicator lifecycle management for concurrent conversations."""

import asyncio
import logging
from typing import Dict, Optional, Set
from collections.abc import Hashable

from telegram import Bot

logger = logging.getLogger(__name__)


class TypingIndicatorManager:
    """Manages typing indicators for concurrent conversations"""

    def __init__(self):
        self._active_typing_tasks: dict[Hashable, asyncio.Task] = {}
        self._typing_locks: dict[Hashable, asyncio.Lock] = {}
        self._typing_lock_refs: dict[Hashable, int] = {}
        self._typing_chat_ids: dict[Hashable, int] = {}
        self._state_lock = asyncio.Lock()
        self.typing_interval = 3.0  # Send typing action every 3 seconds

    @staticmethod
    def _typing_key(chat_id: int, route_key: Hashable | None = None) -> Hashable:
        """Build a typing key that can isolate concurrent bot routes in one chat."""
        return route_key if route_key is not None else chat_id

    async def _borrow_typing_lock(self, typing_key: Hashable) -> asyncio.Lock:
        async with self._state_lock:
            lock = self._typing_locks.get(typing_key)
            if lock is None:
                lock = asyncio.Lock()
                self._typing_locks[typing_key] = lock
            self._typing_lock_refs[typing_key] = self._typing_lock_refs.get(typing_key, 0) + 1
            return lock

    async def _release_typing_lock(self, typing_key: Hashable) -> None:
        async with self._state_lock:
            ref_count = self._typing_lock_refs.get(typing_key, 0)
            if ref_count <= 1:
                self._typing_lock_refs.pop(typing_key, None)
                self._cleanup_idle_typing_state(typing_key)
            else:
                self._typing_lock_refs[typing_key] = ref_count - 1

    def _cleanup_idle_typing_state(self, typing_key: Hashable) -> None:
        if (
            typing_key not in self._active_typing_tasks
            and typing_key not in self._typing_chat_ids
            and self._typing_lock_refs.get(typing_key, 0) == 0
        ):
            self._typing_locks.pop(typing_key, None)

    async def start_typing(self, bot: Bot, chat_id: int, route_key: Hashable | None = None) -> None:
        """Start typing indicator for a specific chat"""
        typing_key = self._typing_key(chat_id, route_key)
        route_lock = None
        try:
            # Cancel any existing typing task for this chat
            await self.stop_typing(chat_id, route_key=route_key)

            route_lock = await self._borrow_typing_lock(typing_key)
            async with route_lock:
                # Create and start new typing task
                task = asyncio.create_task(
                    self._typing_loop(bot, chat_id, typing_key),
                    name=f"typing_indicator_{typing_key}"
                )
                async with self._state_lock:
                    self._active_typing_tasks[typing_key] = task
                    self._typing_chat_ids[typing_key] = chat_id
                logger.debug("Started typing indicator for chat %s route %s", chat_id, typing_key)

        except Exception as e:
            logger.error("Failed to start typing indicator for chat %s route %s: %s", chat_id, route_key, e)
        finally:
            if route_lock is not None:
                await self._release_typing_lock(typing_key)

    async def stop_typing(self, chat_id: int, route_key: Hashable | None = None) -> None:
        """Stop typing indicator for a specific chat"""
        typing_key = self._typing_key(chat_id, route_key)
        route_lock = None
        try:
            route_lock = await self._borrow_typing_lock(typing_key)
            async with route_lock:
                async with self._state_lock:
                    task = self._active_typing_tasks.pop(typing_key, None)
                    self._typing_chat_ids.pop(typing_key, None)

                if task is None:
                    return

                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

                logger.debug("Stopped typing indicator for chat %s route %s", chat_id, typing_key)

        except Exception as e:
            logger.error("Failed to stop typing indicator for chat %s route %s: %s", chat_id, route_key, e)
        finally:
            if route_lock is not None:
                await self._release_typing_lock(typing_key)

    async def stop_all_typing(self) -> None:
        """Stop all active typing indicators"""
        async with self._state_lock:
            typing_items = [
                (typing_key, self._typing_chat_ids.get(typing_key, 0))
                for typing_key in self._active_typing_tasks.keys()
            ]

        for typing_key, chat_id in typing_items:
            await self.stop_typing(chat_id, route_key=typing_key)

    async def _typing_loop(self, bot: Bot, chat_id: int, typing_key: Hashable) -> None:
        """Internal loop that sends typing action every 3 seconds"""
        try:
            while True:
                try:
                    await bot.send_chat_action(chat_id=chat_id, action="typing")
                    logger.debug("Sent typing action to chat %s route %s", chat_id, typing_key)
                except Exception as e:
                    logger.warning("Failed to send typing action to chat %s route %s: %s", chat_id, typing_key, e)
                    # Continue loop despite individual failures

                # Wait for next typing interval
                await asyncio.sleep(self.typing_interval)

        except asyncio.CancelledError:
            logger.debug("Typing loop cancelled for chat %s route %s", chat_id, typing_key)
            raise
        except Exception as e:
            logger.error("Unexpected error in typing loop for chat %s route %s: %s", chat_id, typing_key, e)

    def is_typing_active(self, chat_id: int, route_key: Hashable | None = None) -> bool:
        """Check if typing is currently active for a chat"""
        if route_key is None:
            return any(
                active_chat_id == chat_id and not self._active_typing_tasks[typing_key].done()
                for typing_key, active_chat_id in self._typing_chat_ids.items()
            )

        typing_key = self._typing_key(chat_id, route_key)
        return (
            typing_key in self._active_typing_tasks and
            not self._active_typing_tasks[typing_key].done()
        )

    def get_active_typing_chats(self) -> set[int]:
        """Get set of chat IDs with active typing indicators"""
        return {
            self._typing_chat_ids[typing_key]
            for typing_key, task in self._active_typing_tasks.items()
            if not task.done() and typing_key in self._typing_chat_ids
        }

    async def cleanup(self) -> None:
        """Cleanup method to stop all typing indicators"""
        await self.stop_all_typing()
        async with self._state_lock:
            self._typing_locks.clear()
            self._typing_lock_refs.clear()
            self._typing_chat_ids.clear()
