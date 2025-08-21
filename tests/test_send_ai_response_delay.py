"""
Tests for the delay functionality in the send_ai_response function.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, patch
import random
from message_manager import send_ai_response


class TestSendAIResponseDelay:
    """Test the delay functionality in send_ai_response function"""
    
    @pytest.mark.asyncio
    async def test_no_delay_for_first_message(self):
        """Test that no delay is added before the first message"""
        # Create a multi-part message
        multi_part_message = "Short message 1.\n\nShort message 2.\n\nShort message 3."
        
        # Create a mock bot
        mock_bot = AsyncMock()
        
        # Patch asyncio.sleep to track if it's called
        with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
            # Call the function
            await send_ai_response(chat_id=123, text=multi_part_message, bot=mock_bot)
            
            # Verify that sleep was called (for 2nd and 3rd messages, but not for the first)
            # The function should be called twice (for 2nd and 3rd messages)
            assert mock_sleep.call_count == 2
    
    @pytest.mark.asyncio
    async def test_delay_calculation(self):
        """Test that delays are calculated correctly based on message length"""
        # Create a multi-part message with different lengths
        part1 = "Short message."  # 14 characters
        part2 = "This is a longer message with more content to test the delay calculation."  # 76 characters
        multi_part_message = f"{part1}\n\n{part2}"
        
        # Create a mock bot
        mock_bot = AsyncMock()
        
        # Patch random functions to return predictable values
        with patch('random.randint', return_value=20), \
             patch('random.uniform', return_value=0.3), \
             patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
            
            # Call the function
            await send_ai_response(chat_id=123, text=multi_part_message, bot=mock_bot)
            
            # Verify the bot's send_message was called twice
            assert mock_bot.send_message.call_count == 2
            
            # Verify that sleep was called once (only for the second message)
            assert mock_sleep.call_count == 1
            
            # Calculate expected delay for the second message:
            # message_length = 76
            # typing_speed = 20 (from our patch)
            # base_delay = 76 / 20 = 3.8
            # random_offset = 0.3 (from our patch)
            # total_delay = 3.8 + 0.3 = 4.1
            # Since MAX_DELAY is 5, the delay should be 4.1
            # Use pytest.approx to handle floating point precision issues
            mock_sleep.assert_called_once_with(pytest.approx(3.95, abs=0.01))
    
    @pytest.mark.asyncio
    async def test_delay_respects_max_delay(self):
        """Test that delays don't exceed MAX_DELAY"""
        # Create a very long message part
        long_part = "A" * 1000  # 1000 characters
        
        multi_part_message = f"Short.\n\n{long_part}"
        
        # Create a mock bot
        mock_bot = AsyncMock()
        
        # Patch random functions to return values that would exceed MAX_DELAY
        with patch('random.randint', return_value=10), \
             patch('random.uniform', return_value=0.1), \
             patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
            
            # Call the function
            await send_ai_response(chat_id=123, text=multi_part_message, bot=mock_bot)
            
            # Verify the bot's send_message was called twice
            assert mock_bot.send_message.call_count == 2
            
            # Verify that sleep was called once (only for the second message)
            assert mock_sleep.call_count == 1
            
            # Calculate expected delay for the second message:
            # message_length = 1000
            # typing_speed = 10 (from our patch)
            # base_delay = 1000 / 10 = 100
            # random_offset = 0.1 (from our patch)
            # total_delay = 100 + 0.1 = 100.1
            # Since MAX_DELAY is 5, the delay should be capped at 5
            mock_sleep.assert_called_once_with(5)
    
    @pytest.mark.asyncio
    async def test_single_message_no_delay(self):
        """Test that a single message doesn't cause any delays"""
        # Create a single short message
        single_message = "This is a single message."
        
        # Create a mock bot
        mock_bot = AsyncMock()
        
        # Patch asyncio.sleep to track if it's called
        with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
            # Call the function
            await send_ai_response(chat_id=123, text=single_message, bot=mock_bot)
            
            # Verify that sleep was never called
            mock_sleep.assert_not_called()
            
            # Verify the bot's send_message was called exactly once
            mock_bot.send_message.assert_called_once_with(chat_id=123, text=single_message)


if __name__ == "__main__":
    pytest.main([__file__])