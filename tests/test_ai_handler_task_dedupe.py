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
