"""Shared Celery worker event-loop helpers."""

from __future__ import annotations

import asyncio
from typing import Any
from collections.abc import Coroutine

from celery.signals import worker_process_init, worker_process_shutdown

_worker_loop: asyncio.AbstractEventLoop | None = None


@worker_process_init.connect
def init_worker_loop(**kwargs) -> None:
    """Create one event loop per Celery worker process."""
    global _worker_loop
    _worker_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_worker_loop)


@worker_process_shutdown.connect
def shutdown_worker_loop(**kwargs) -> None:
    """Close the worker event loop during process shutdown."""
    global _worker_loop
    if _worker_loop and not _worker_loop.is_closed():
        _worker_loop.close()
    _worker_loop = None


def run_coroutine(coro: Coroutine[Any, Any, Any]) -> Any:
    """Run an async task body on the worker process event loop."""
    global _worker_loop
    if _worker_loop is None or _worker_loop.is_closed():
        _worker_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_worker_loop)
    return _worker_loop.run_until_complete(coro)
