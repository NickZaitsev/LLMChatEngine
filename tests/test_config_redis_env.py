import importlib
import sys
from unittest.mock import patch


def test_config_uses_redis_url_fallback(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6380/5")
    monkeypatch.delenv("MESSAGE_QUEUE_REDIS_URL", raising=False)
    monkeypatch.delenv("PROACTIVE_MESSAGING_REDIS_URL", raising=False)
    sys.modules.pop("config", None)
    with patch("dotenv.load_dotenv", return_value=False):
        import config

    assert config.REDIS_URL == "redis://localhost:6380/5"
    assert config.MESSAGE_QUEUE_REDIS_URL == "redis://localhost:6380/5"
    assert config.PROACTIVE_MESSAGING_REDIS_URL == "redis://localhost:6380/5"

    monkeypatch.delenv("REDIS_URL", raising=False)
    sys.modules.pop("config", None)


def test_config_allows_specific_redis_overrides(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6380/5")
    monkeypatch.setenv("MESSAGE_QUEUE_REDIS_URL", "redis://localhost:6380/6")
    monkeypatch.setenv("PROACTIVE_MESSAGING_REDIS_URL", "redis://localhost:6380/7")
    sys.modules.pop("config", None)
    with patch("dotenv.load_dotenv", return_value=False):
        import config

    assert config.MESSAGE_QUEUE_REDIS_URL == "redis://localhost:6380/6"
    assert config.PROACTIVE_MESSAGING_REDIS_URL == "redis://localhost:6380/7"

    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("MESSAGE_QUEUE_REDIS_URL", raising=False)
    monkeypatch.delenv("PROACTIVE_MESSAGING_REDIS_URL", raising=False)
    sys.modules.pop("config", None)
