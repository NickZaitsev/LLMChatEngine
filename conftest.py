import os

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///tests/test_suite.db"

import pytest


pytest_plugins = ("pytest_asyncio",)


def pytest_configure(config):
    os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///tests/test_suite.db")
    os.environ.setdefault("PROACTIVE_MESSAGING_REDIS_URL", "redis://redis:6379/0")
    os.environ.setdefault("MESSAGE_QUEUE_REDIS_URL", "redis://redis:6379/0")
    config.addinivalue_line("markers", "asyncio: mark test as asyncio")
    config.addinivalue_line("markers", "slow: slow test")
