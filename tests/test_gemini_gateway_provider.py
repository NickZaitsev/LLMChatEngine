from __future__ import annotations

from typing import Any

import ai_handler
import pytest
from ai_handler import ModelClient
from settings import AppSettings


class FakeGatewayConfig:
    def __init__(self, **kwargs: Any) -> None:
        self.values = kwargs


class FakeGateway:
    instances: list["FakeGateway"] = []

    def __init__(self, config: FakeGatewayConfig) -> None:
        self.config = config
        self.calls: list[tuple[str, int | None]] = []
        self.instances.append(self)

    def generate_text(self, prompt: str, *, max_output_tokens: int | None = None) -> str:
        self.calls.append((prompt, max_output_tokens))
        return "gateway response"


def install_fake_gateway(monkeypatch) -> None:
    FakeGateway.instances.clear()
    monkeypatch.setattr(ai_handler, "GEMINI_GATEWAY_AVAILABLE", True, raising=False)
    monkeypatch.setattr(ai_handler, "GeminiGatewayConfig", FakeGatewayConfig, raising=False)
    monkeypatch.setattr(ai_handler, "GeminiGateway", FakeGateway, raising=False)


def test_model_client_routes_chat_messages_through_gemini_gateway(monkeypatch) -> None:
    install_fake_gateway(monkeypatch)

    client = ModelClient(
        provider="gemini_gateway",
        llm_config={
            "gemini_api_keys": "key-1, key-2",
            "gemini_model": "gemini-test",
            "temperature": 0.25,
        },
    )

    result = client.ask(
        [
            {"role": "system", "content": "Be concise."},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
            {"role": "user", "content": "Status?"},
        ],
        max_tokens=321,
    )

    gateway = FakeGateway.instances[0]
    assert result == "gateway response"
    assert gateway.config.values["api_keys"] == ("key-1", "key-2")
    assert gateway.config.values["model"] == "gemini-test"
    assert gateway.config.values["temperature"] == 0.25
    assert gateway.calls == [
        (
            '[{"role": "system", "content": "Be concise."}, '
            '{"role": "user", "content": "Hello"}, '
            '{"role": "assistant", "content": "Hi"}, '
            '{"role": "user", "content": "Status?"}]',
            321,
        )
    ]


def test_model_client_rejects_gemini_gateway_without_api_keys(monkeypatch) -> None:
    install_fake_gateway(monkeypatch)

    try:
        ModelClient(
            provider="gemini_gateway",
            llm_config={"gemini_api_keys": " , ", "gemini_model": "gemini-test"},
        )
    except ValueError as exc:
        assert "GEMINI_API_KEY" in str(exc)
    else:
        raise AssertionError("ModelClient accepted an empty Gemini gateway key list")


def test_app_settings_groups_gemini_gateway_configuration() -> None:
    settings = AppSettings(
        PROVIDER="gemini_gateway",
        GEMINI_API_KEYS="key-1,key-2",
        GEMINI_MODEL="gemini-test",
        GEMINI_RPM=12,
        GEMINI_TPM=123_000,
        GEMINI_RPD=456,
        GEMINI_TIMEOUT_MS=45_000,
        GEMINI_MAX_RETRIES=2,
    )

    assert settings.llm.provider == "gemini_gateway"
    assert settings.llm.gemini_api_keys == "key-1,key-2"
    assert settings.llm.gemini_rpm == 12
    assert settings.llm.gemini_tpm == 123_000
    assert settings.llm.gemini_rpd == 456
    assert settings.llm.gemini_timeout_ms == 45_000
    assert settings.llm.gemini_max_retries == 2


def test_gemini_gateway_parses_false_retry_override(monkeypatch: Any) -> None:
    install_fake_gateway(monkeypatch)

    ModelClient(
        provider="gemini_gateway",
        llm_config={
            "gemini_api_key": "key-1",
            "gemini_model": "gemini-test",
            "gemini_retry_capacity_errors_indefinitely": "false",
        },
    )

    gateway = FakeGateway.instances[0]
    assert gateway.config.values["retry_capacity_errors_indefinitely"] is False


def test_gemini_gateway_rejects_unsupported_per_call_temperature(
    monkeypatch: Any,
) -> None:
    install_fake_gateway(monkeypatch)
    client = ModelClient(
        provider="gemini_gateway",
        llm_config={
            "gemini_api_key": "key-1",
            "gemini_model": "gemini-test",
            "temperature": 0.4,
        },
    )

    with pytest.raises(ValueError, match="per-call temperature"):
        client.ask([{"role": "user", "content": "hello"}], temperature=0.2)


@pytest.mark.asyncio
async def test_ai_handler_defers_timeout_and_retries_to_gateway(
    monkeypatch: Any,
) -> None:
    handler = ai_handler.AIHandler.__new__(ai_handler.AIHandler)
    handler.model_client = type("GatewayClient", (), {"provider": "gemini_gateway"})()
    handler.prompt_assembler = None
    handler.personality = "Be concise."
    handler.max_retries = 3
    handler.request_timeout = 1
    handler.base_delay = 0
    handler.max_delay = 0

    calls = 0

    async def make_request(messages: list[dict[str, str]]) -> str:
        nonlocal calls
        calls += 1
        return "ok"

    async def unexpected_wait_for(*args: Any, **kwargs: Any) -> str:
        raise AssertionError("outer wait_for must not wrap Gemini Gateway retries")

    handler._make_ai_request = make_request
    monkeypatch.setattr(ai_handler.asyncio, "wait_for", unexpected_wait_for)
    monkeypatch.setattr(ai_handler, "MEMORY_ENABLED", False)

    response = await handler.generate_response("hello", [], conversation_id=None)

    assert response == "ok"
    assert calls == 1
