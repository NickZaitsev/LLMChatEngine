import pytest
from pydantic import ValidationError

from settings import AppSettings


def test_app_settings_groups_flat_environment_values():
    settings = AppSettings(
        DATABASE_URL="postgresql+asyncpg://u:p@localhost/db",
        REDIS_URL="redis://localhost:6380/5",
        ADMIN_USER_IDS="1, 2",
        MAX_CONTEXT_TOKENS=1200,
        RESERVED_TOKENS=200,
        PROMPT_HISTORY_BUDGET=1000,
        PROACTIVE_MESSAGING_INTERVAL_1H=111,
        PROACTIVE_MESSAGING_JITTER_1H=7,
    )

    assert settings.db.url == "postgresql+asyncpg://u:p@localhost/db"
    assert settings.redis.message_queue_url == "redis://localhost:6380/5"
    assert settings.redis.proactive_url == "redis://localhost:6380/5"
    assert settings.admin.user_ids == [1, 2]
    assert settings.prompts.history_budget == 1000
    assert settings.proactive.cadences[0].as_dict() == {
        "name": "1h",
        "interval": 111,
        "jitter": 7,
    }
    assert settings.books.chunk_target_tokens == 400


def test_app_settings_specific_redis_overrides():
    settings = AppSettings(
        REDIS_URL="redis://localhost:6380/5",
        MESSAGE_QUEUE_REDIS_URL="redis://localhost:6380/6",
        PROACTIVE_MESSAGING_REDIS_URL="redis://localhost:6380/7",
    )

    assert settings.queue.redis_url == "redis://localhost:6380/6"
    assert settings.proactive.redis_url == "redis://localhost:6380/7"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("PROMPT_MEMORY_TOKEN_BUDGET_RATIO", -0.01),
        ("BOOK_RAG_MIN_SCORE", 1.01),
        ("BOOK_RAG_TOKEN_BUDGET_RATIO", 2.0),
        ("MAX_CONTEXT_TOKENS", 0),
        ("RESERVED_TOKENS", -1),
        ("MEMORY_EMBED_DIM", 0),
        ("MEMORY_CHUNK_MAX_MESSAGES", 0),
        ("BOOK_RAG_TOP_K", 0),
        ("BOOK_EMBED_BATCH_SIZE", 0),
        ("MESSAGE_QUEUE_LOCK_TIMEOUT", 0),
        ("MESSAGE_QUEUE_DISPATCHER_INTERVAL", 0),
    ],
)
def test_app_settings_reject_invalid_ratios_limits_batches_and_dimensions(field, value):
    with pytest.raises(ValidationError):
        AppSettings(**{field: value})


def test_app_settings_reject_incoherent_overlaps_budgets_and_lock_refresh():
    invalid_settings = [
        {"BOOK_CHUNK_TARGET_TOKENS": 100, "BOOK_CHUNK_OVERLAP_TOKENS": 100},
        {"MAX_CONTEXT_TOKENS": 100, "RESERVED_TOKENS": 100},
        {"MESSAGE_QUEUE_LOCK_TIMEOUT": 10, "MESSAGE_QUEUE_LOCK_REFRESH_INTERVAL": 10},
    ]
    for values in invalid_settings:
        with pytest.raises(ValidationError):
            AppSettings(**values)
