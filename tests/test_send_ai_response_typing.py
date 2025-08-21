"""
Tests for the typing indicator functionality in the send_ai_response function.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import random
from message_manager import send_ai_response, TypingIndicatorManager


class TestSendAIResponseTyping:
    """Test the typing indicator functionality in send_ai_response function"""
    
    @pytest.mark.asyncio
    async def test_typing_indicator_started_and_stopped(self):
        """Test that typing indicator is started and stopped during delays"""
        # Create a multi-part message
        part1 = "Short message."  # 14 characters
        part2 = "This is a longer message with more content to test the typing indicator."  # 68 characters
        multi_part_message = f"{part1}\n\n{part2}"
        
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
            await send_ai_response(chat_id=123, text=multi_part_message, bot=mock_bot, typing_manager=mock_typing_manager)
            
            # Verify the bot's send_message was called twice
            assert mock_bot.send_message.call_count == 2
            
            # Verify that typing indicator was started once (only for the second message)
            mock_typing_manager.start_typing.assert_called_once_with(mock_bot, 123)
            
            # Verify that typing indicator was stopped once (only for the second message)
            mock_typing_manager.stop_typing.assert_called_once_with(123)
    
    @pytest.mark.asyncio
    async def test_no_typing_indicator_without_manager(self):
        """Test that no typing indicator calls are made when no manager is provided"""
        # Create a multi-part message
        part1 = "Short message."  # 14 characters
        part2 = "This is a longer message with more content to test the typing indicator."  # 68 characters
        multi_part_message = f"{part1}\n\n{part2}"
        
        # Create a mock bot
        mock_bot = AsyncMock()
        
        # Patch random functions to return predictable values
        with patch('random.randint', return_value=20), \
             patch('random.uniform', return_value=0.3), \
             patch('asyncio.sleep', new_callable=AsyncMock):
            
            # Call the function without typing manager
            await send_ai_response(chat_id=123, text=multi_part_message, bot=mock_bot)
            
            # Verify the bot's send_message was called twice
            assert mock_bot.send_message.call_count == 2
    
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


if __name__ == "__main__":
    pytest.main([__file__])