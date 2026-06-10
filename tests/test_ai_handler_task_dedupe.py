from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_handler import AIHandler


@pytest.mark.asyncio
async def test_generate_response_skips_duplicate_summary_scheduling():
    with patch("ai_handler.ModelClient"):
        handler = AIHandler()

    handler.prompt_assembler = MagicMock()
    handler.prompt_assembler.build_prompt = AsyncMock(return_value=[{"role": "system", "content": "persona"}])
    handler.prompt_assembler.get_active_message_count = AsyncMock(return_value=999)
    handler._make_ai_request = AsyncMock(return_value="response")

    with patch("memory.tasks.acquire_task_lock", return_value=False), \
         patch("memory.tasks.create_conversation_summary") as create_conversation_summary:
        response = await handler.generate_response(
            user_message="hello",
            conversation_history=[],
            conversation_id="conv-1",
            role="user",
        )

    assert response == "response"
    create_conversation_summary.delay.assert_not_called()


@pytest.mark.asyncio
async def test_make_ai_request_forwards_generation_params():
    with patch("ai_handler.ModelClient"):
        handler = AIHandler()

    handler.temperature = 0.2
    handler.max_tokens = 123
    handler.model_client = MagicMock()
    handler.model_client.ask = MagicMock(return_value="response")

    response = await handler._make_ai_request([{"role": "user", "content": "hello"}])

    assert response == "response"
    handler.model_client.ask.assert_called_once_with(
        [{"role": "user", "content": "hello"}],
        temperature=0.2,
        max_tokens=123,
    )


@pytest.mark.asyncio
async def test_generate_response_retries_retryable_error():
    with patch("ai_handler.ModelClient"):
        handler = AIHandler()

    handler.max_retries = 2
    handler.base_delay = 0
    handler.max_delay = 0
    handler.request_timeout = 1
    handler._make_ai_request = AsyncMock(side_effect=[RuntimeError("timeout"), "response"])

    response = await handler.generate_response(
        user_message="hello",
        conversation_history=[],
        conversation_id=None,
        role="user",
    )

    assert response == "response"
    assert handler._make_ai_request.await_count == 2
