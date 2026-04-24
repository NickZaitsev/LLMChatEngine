"""
Tests for the typing indicator functionality in the send_ai_response function.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from message_manager import send_ai_response, generate_ai_response


class TestSendAIResponseTyping:
    """Test the typing indicator functionality in send_ai_response function"""
    
    @pytest.mark.asyncio
    async def test_typing_indicator_started_and_stopped(self):
        """Test that typing indicator is started and stopped during delayed sends."""
        delayed_message = "This is a longer message with more content to test the typing indicator."
        
        # Create a mock bot
        mock_bot = AsyncMock()
        
        # Create a mock typing manager
        mock_typing_manager = MagicMock()
        mock_typing_manager.start_typing = AsyncMock()
        mock_typing_manager.stop_typing = AsyncMock()
        
        # Patch random functions to return predictable values
        with patch('random.randint', return_value=20), \
            patch('random.uniform', return_value=0.3), \
            patch('asyncio.sleep', new_callable=AsyncMock):
            
            # Call the function with typing manager
            await send_ai_response(
                chat_id=123,
                text=delayed_message,
                bot=mock_bot,
                typing_manager=mock_typing_manager,
                is_first_message=False,
            )
            
            # Verify the bot's send_message was called once
            mock_bot.send_message.assert_awaited_once_with(chat_id=123, text=delayed_message)
            
            # Verify that typing indicator was started once for the delayed part
            mock_typing_manager.start_typing.assert_awaited_once_with(mock_bot, 123, route_key=None)
            
            # Verify that typing indicator was stopped once for the delayed part
            mock_typing_manager.stop_typing.assert_awaited_once_with(123, route_key=None)
    
    @pytest.mark.asyncio
    async def test_no_typing_indicator_without_manager(self):
        """Test that no typing indicator calls are made when no manager is provided."""
        delayed_message = "This is a longer message with more content to test the typing indicator."
        
        # Create a mock bot
        mock_bot = AsyncMock()
        
        # Patch random functions to return predictable values
        with patch('random.randint', return_value=20), \
            patch('random.uniform', return_value=0.3), \
            patch('asyncio.sleep', new_callable=AsyncMock):
            
            # Call the function without typing manager
            await send_ai_response(chat_id=123, text=delayed_message, bot=mock_bot, is_first_message=False)
            
            # Verify the bot's send_message was called once
            mock_bot.send_message.assert_awaited_once_with(chat_id=123, text=delayed_message)
    
    @pytest.mark.asyncio
    async def test_typing_indicator_not_called_for_single_message(self):
        """Test that typing indicator is not called for single message"""
        # Create a single short message
        single_message = "This is a single message."
        
        # Create a mock bot
        mock_bot = AsyncMock()
        
        # Create a mock typing manager
        mock_typing_manager = MagicMock()
        mock_typing_manager.start_typing = AsyncMock()
        mock_typing_manager.stop_typing = AsyncMock()
        
        # Call the function with typing manager
        await send_ai_response(chat_id=123, text=single_message, bot=mock_bot, typing_manager=mock_typing_manager)
        
        # Verify the bot's send_message was called exactly once
        mock_bot.send_message.assert_called_once_with(chat_id=123, text=single_message)
        
        # Verify that typing indicator was never started or stopped
        mock_typing_manager.start_typing.assert_not_called()
        mock_typing_manager.stop_typing.assert_not_called()

    @pytest.mark.asyncio
    async def test_generate_ai_response_stops_typing_after_success(self):
        """Typing started for AI generation must be stopped in the shared helper."""
        mock_bot = AsyncMock()
        mock_typing_manager = MagicMock()
        mock_typing_manager.start_typing = AsyncMock()
        mock_typing_manager.stop_typing = AsyncMock()
        mock_ai_handler = MagicMock()
        mock_ai_handler.generate_response = AsyncMock(return_value="ok")

        response = await generate_ai_response(
            ai_handler=mock_ai_handler,
            typing_manager=mock_typing_manager,
            bot=mock_bot,
            chat_id=123,
            additional_prompt="hello",
            conversation_history=[],
            route_key="123:bot-a",
        )

        assert response == "ok"
        mock_typing_manager.start_typing.assert_awaited_once_with(mock_bot, 123, route_key="123:bot-a")
        mock_typing_manager.stop_typing.assert_awaited_once_with(123, route_key="123:bot-a")

    @pytest.mark.asyncio
    async def test_generate_ai_response_stops_typing_after_failure(self):
        """Typing cleanup must still happen when the AI request fails."""
        mock_bot = AsyncMock()
        mock_typing_manager = MagicMock()
        mock_typing_manager.start_typing = AsyncMock()
        mock_typing_manager.stop_typing = AsyncMock()
        mock_ai_handler = MagicMock()
        mock_ai_handler.generate_response = AsyncMock(side_effect=RuntimeError("boom"))

        response = await generate_ai_response(
            ai_handler=mock_ai_handler,
            typing_manager=mock_typing_manager,
            bot=mock_bot,
            chat_id=123,
            additional_prompt="hello",
            conversation_history=[],
            route_key="123:bot-a",
        )

        assert response is None
        mock_typing_manager.start_typing.assert_awaited_once_with(mock_bot, 123, route_key="123:bot-a")
        mock_typing_manager.stop_typing.assert_awaited_once_with(123, route_key="123:bot-a")


if __name__ == "__main__":
    pytest.main([__file__])
