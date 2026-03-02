import importlib
import os


def test_celeryconfig_uses_env_urls(monkeypatch):
    monkeypatch.setenv("CELERY_BROKER_URL", "redis://localhost:6380/1")
    monkeypatch.setenv("CELERY_RESULT_BACKEND", "redis://localhost:6380/2")

    import celeryconfig

    importlib.reload(celeryconfig)

    assert celeryconfig.broker_url == "redis://localhost:6380/1"
    assert celeryconfig.result_backend == "redis://localhost:6380/2"

    monkeypatch.delenv("CELERY_BROKER_URL", raising=False)
    monkeypatch.delenv("CELERY_RESULT_BACKEND", raising=False)
    importlib.reload(celeryconfig)
