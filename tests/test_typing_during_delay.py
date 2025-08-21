"""
Simple test to verify that typing indicator works during delay.
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from unittest.mock import AsyncMock, MagicMock
from message_manager import send_ai_response, TypingIndicatorManager


async def test_typing_during_delay():
    """Test that typing indicator works during delay"""
    # Create a multi-part message
    part1 = "Short message."  # 14 characters
    part2 = "This is a longer message with more content to test the typing indicator functionality properly." # 82 characters
    multi_part_message = f"{part1}\n\n{part2}"
    
    # Create a mock bot
    mock_bot = AsyncMock()
    mock_bot.send_chat_action = AsyncMock()
    
    # Create a typing manager
    typing_manager = TypingIndicatorManager()
    
    # Calculate expected delay for part2
    message_length = len(part2)
    typing_speed = 20  # Middle of default range 10-30
    random_offset = 0.3  # Middle of default range 0.1-0.5
    expected_delay = message_length / typing_speed + random_offset
    expected_delay = min(expected_delay, 5)  # MAX_DELAY is 5
    
    print(f"Message length: {message_length} characters")
    print(f"Expected delay: {expected_delay} seconds")
    print(f"Typing interval: {typing_manager.typing_interval} seconds")
    print(f"Expected typing actions: {int(expected_delay // typing_manager.typing_interval) + 1}")
    
    # Call the function with typing manager
    print("Starting send_ai_response...")
    await send_ai_response(chat_id=123, text=multi_part_message, bot=mock_bot, typing_manager=typing_manager)
    print("Finished send_ai_response")
    
    # Print out what methods were called
    print(f"send_message called {mock_bot.send_message.call_count} times")
    print(f"send_chat_action called {mock_bot.send_chat_action.call_count} times")
    
    # Print the calls
    print("send_message calls:")
    for call in mock_bot.send_message.call_args_list:
        print(f"  {call}")
        
    print("send_chat_action calls:")
    for call in mock_bot.send_chat_action.call_args_list:
        print(f"  {call}")


if __name__ == "__main__":
    asyncio.run(test_typing_during_delay())