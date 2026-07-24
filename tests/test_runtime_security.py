from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import yaml

from core.utils import mask_url
from messaging import MessageDispatcher, MessageQueueManager
from service_container import ServiceContainer


def test_mask_url_redacts_passwords_and_sensitive_query_values():
    assert mask_url("redis://alice:s3cr%40t@redis:6379/0") == "redis://alice:***@redis:6379/0"
    assert mask_url("postgresql+asyncpg://db:pw@postgres:5432/app") == (
        "postgresql+asyncpg://db:***@postgres:5432/app"
    )
    masked = mask_url("https://example.test/path?token=secret&mode=safe")
    assert "secret" not in masked
    assert "token=%2A%2A%2A" in masked
    assert "mode=safe" in masked


def test_queue_initialization_logs_do_not_expose_redis_credentials(caplog):
    redis_client = SimpleNamespace(register_script=lambda source: AsyncMock())
    secret_url = "redis://alice:redis-password@redis:6379/0"
    with patch("messaging.queue.redis_async.from_url", return_value=redis_client):
        MessageQueueManager(secret_url)
        MessageDispatcher(secret_url)
    assert "redis-password" not in caplog.text


@pytest.mark.asyncio
async def test_container_close_releases_every_owned_resource_exactly_once():
    container = ServiceContainer.__new__(ServiceContainer)
    container.message_dispatcher = SimpleNamespace(close=AsyncMock())
    container.message_queue_manager = SimpleNamespace(close=AsyncMock())
    container.typing_manager = SimpleNamespace(cleanup=AsyncMock())
    container.memory_vector_store = SimpleNamespace(close=AsyncMock())
    container.book_vector_store = SimpleNamespace(close=AsyncMock())
    container.storage = SimpleNamespace(close=AsyncMock())
    container._initialized = True
    container._closed = False

    await container.close()
    await container.close()

    container.message_dispatcher.close.assert_awaited_once()
    container.message_queue_manager.close.assert_awaited_once()
    container.typing_manager.cleanup.assert_awaited_once()
    container.memory_vector_store.close.assert_awaited_once()
    container.book_vector_store.close.assert_awaited_once()
    container.storage.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_dispatcher_close_closes_each_telegram_client_and_redis_once():
    redis_client = SimpleNamespace(register_script=lambda source: AsyncMock(), aclose=AsyncMock())
    bot_a = SimpleNamespace(shutdown=AsyncMock())
    bot_b = SimpleNamespace(shutdown=AsyncMock())
    with patch("messaging.queue.redis_async.from_url", return_value=redis_client):
        dispatcher = MessageDispatcher("redis://redis:6379/0")
    dispatcher._bot_cache["a"] = ("token-a", bot_a)
    dispatcher._bot_cache["b"] = ("token-b", bot_b)

    await dispatcher.close()
    await dispatcher.close()

    bot_a.shutdown.assert_awaited_once()
    bot_b.shutdown.assert_awaited_once()
    redis_client.aclose.assert_awaited_once()


def test_compose_keeps_datastores_internal_and_waits_for_health():
    compose = yaml.safe_load(Path("docker-compose.yml").read_text(encoding="utf-8"))
    services = compose["services"]
    assert "ports" not in services["postgres"]
    assert "ports" not in services["redis"]
    assert "healthcheck" in services["postgres"]
    assert "healthcheck" in services["redis"]

    # Every service that reads or writes the database waits both for a healthy
    # Postgres and for the one-shot migration to finish, so tables always exist.
    for name in ("llm-chat-engine", "celery-worker", "celery-memory"):
        dependencies = services[name]["depends_on"]
        assert dependencies["postgres"]["condition"] == "service_healthy"
        assert dependencies["redis"]["condition"] == "service_healthy"
        assert dependencies["migrate"]["condition"] == "service_completed_successfully"

    # The scheduler only pushes envelopes to Redis; it must not depend on the DB.
    assert set(services["celery-beat"]["depends_on"]) == {"redis"}


def test_compose_scopes_secrets_per_service():
    compose = yaml.safe_load(Path("docker-compose.yml").read_text(encoding="utf-8"))
    services = compose["services"]

    def env_keys(name):
        env = services[name].get("environment", {})
        if isinstance(env, list):
            return {item.split("=", 1)[0] for item in env}
        return set(env)

    # The scheduler and the migration one-shot must not receive delivery secrets.
    for name in ("celery-beat", "migrate"):
        keys = env_keys(name)
        assert "TOKEN_ENCRYPTION_KEY" not in keys
        assert "ADMIN_BOT_TOKEN" not in keys
        assert "TELEGRAM_TOKEN" not in keys

    # Only the bot handles admin/Telegram credentials; workers never see them.
    for name in ("celery-worker", "celery-memory"):
        keys = env_keys(name)
        assert "ADMIN_BOT_TOKEN" not in keys
        assert "TELEGRAM_TOKEN" not in keys

    # No service uses the whole-file env_file dump.
    for name, service in services.items():
        assert "env_file" not in service, f"{name} must not mount the whole .env"


def test_docker_image_prepares_book_volume_for_non_root_runtime() -> None:
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")

    create_storage = "mkdir -p /app/book_files"
    switch_to_bot = "USER bot"
    assert create_storage in dockerfile
    assert dockerfile.index(create_storage) < dockerfile.index(switch_to_bot)
