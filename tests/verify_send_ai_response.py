"""
Simple test script to verify that the send_ai_response function properly handles:

1. Short messages (under 4000 characters) - should be sent as a single message
2. Long messages (over 4000 characters) - should be split into multiple messages
3. Messages with multiple paragraphs - should be split by paragraphs when possible
4. Very long paragraphs - should be chunked appropriately without breaking words

This script can be run independently to verify the function works correctly.
"""

import asyncio
import sys
import os
import textwrap

# Add the parent directory to the path so we can import ai_handler
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from ai_handler import send_ai_response


class MockBot:
    """A mock bot class to simulate Telegram bot behavior for testing"""
    
    def __init__(self):
        self.sent_messages = []
    
    async def send_message(self, chat_id, text):
        """Simulate sending a message"""
        self.sent_messages.append({
            'chat_id': chat_id,
            'text': text
        })
        print(f"Sending message to chat {chat_id}: {len(text)} characters")
        # Simulate network delay
        await asyncio.sleep(0.01)


def simulate_send_ai_response(text):
    """
    Simulate the send_ai_response function to generate expected results for testing
    """
    # Split by paragraphs
    parts = text.split("\n\n")
    
    # Chunk long parts
    safe_parts = []
    for part in parts:
        chunks = textwrap.wrap(part, width=4000, break_long_words=False, break_on_hyphens=False)
        safe_parts.extend(chunks)
    
    return safe_parts


async def test_short_message():
    """Test that short messages (under 4000 characters) are sent as a single message"""
    print("\n=== Testing Short Message ===")
    short_message = "This is a short message that should be sent in one piece."
    assert len(short_message) < 4000
    
    mock_bot = MockBot()
    await send_ai_response(chat_id=123, text=short_message, bot=mock_bot)
    
    # Verify the bot's send_message was called exactly once with the entire message
    assert len(mock_bot.sent_messages) == 1
    assert mock_bot.sent_messages[0]['text'] == short_message
    assert mock_bot.sent_messages[0]['chat_id'] == 123
    print("[PASS] Short message test passed")


async def test_long_message():
    """Test that long messages (over 4000 characters) are split into multiple messages"""
    print("\n=== Testing Long Message ===")
    # Create a long message with multiple words that can be split
    long_message = "This is a long message with multiple words that should be split into multiple parts. " * 100
    print(f"Original message length: {len(long_message)}")
    assert len(long_message) > 4000
    
    mock_bot = MockBot()
    await send_ai_response(chat_id=123, text=long_message, bot=mock_bot)
    
    # Verify the bot's send_message was called multiple times
    assert len(mock_bot.sent_messages) > 1
    print(f"Message split into {len(mock_bot.sent_messages)} parts")
    
    # Generate expected results using our simulation
    expected_parts = simulate_send_ai_response(long_message)
    
    # Verify that the number of messages matches expected
    assert len(mock_bot.sent_messages) == len(expected_parts)
    
    # Verify that each message matches the expected parts
    for i, (actual, expected) in enumerate(zip(mock_bot.sent_messages, expected_parts)):
        assert actual['text'] == expected, f"Message {i} does not match expected"
    
    # Verify that each individual message is under or equal to 4000 characters
    for msg in mock_bot.sent_messages:
        assert len(msg['text']) <= 4000
    
    print("[PASS] Long message test passed")


async def test_paragraph_splitting():
    """Test that messages with multiple paragraphs are split by paragraphs when possible"""
    print("\n=== Testing Paragraph Splitting ===")
    paragraph1 = "This is the first paragraph.\nIt has multiple sentences."
    paragraph2 = "This is the second paragraph.\nIt also has multiple sentences."
    paragraph3 = "This is the third paragraph.\nIt is the last one."
    
    multi_paragraph_message = f"{paragraph1}\n\n{paragraph2}\n\n{paragraph3}"
    
    mock_bot = MockBot()
    await send_ai_response(chat_id=123, text=multi_paragraph_message, bot=mock_bot)
    
    # Generate expected results using our simulation
    expected_parts = simulate_send_ai_response(multi_paragraph_message)
    
    # Verify that the number of messages matches expected
    assert len(mock_bot.sent_messages) == len(expected_parts)
    
    # Verify that each message matches the expected parts
    for i, (actual, expected) in enumerate(zip(mock_bot.sent_messages, expected_parts)):
        assert actual['text'] == expected, f"Message {i} does not match expected"
    
    print(f"Message split into {len(mock_bot.sent_messages)} parts")
    print("[PASS] Paragraph splitting test passed")


async def test_long_paragraph_chunking():
    """Test that very long paragraphs are chunked appropriately without breaking words"""
    print("\n=== Testing Long Paragraph Chunking ===")
    # Create a message with a very long paragraph (over 4000 characters)
    long_paragraph = "This is a very long paragraph without any paragraph breaks. " * 100
    assert len(long_paragraph) > 4000
    
    mock_bot = MockBot()
    await send_ai_response(chat_id=123, text=long_paragraph, bot=mock_bot)
    
    # Generate expected results using our simulation
    expected_parts = simulate_send_ai_response(long_paragraph)
    
    # Verify that the number of messages matches expected
    assert len(mock_bot.sent_messages) == len(expected_parts)
    
    # Verify that each message matches the expected parts
    for i, (actual, expected) in enumerate(zip(mock_bot.sent_messages, expected_parts)):
        assert actual['text'] == expected, f"Message {i} does not match expected"
    
    # Verify that each individual message is under or equal to 4000 characters
    for msg in mock_bot.sent_messages:
        assert len(msg['text']) <= 4000
    
    print(f"Message split into {len(mock_bot.sent_messages)} parts")
    print("[PASS] Long paragraph chunking test passed")


async def test_exact_4000_char_boundary():
    """Test behavior when message length is exactly at the 4000 character boundary"""
    print("\n=== Testing Exact 4000 Character Boundary ===")
    # Create a message that is exactly 4000 characters
    exact_length_message = "A" * 4000
    assert len(exact_length_message) == 4000
    
    mock_bot = MockBot()
    await send_ai_response(chat_id=123, text=exact_length_message, bot=mock_bot)
    
    # Generate expected results using our simulation
    expected_parts = simulate_send_ai_response(exact_length_message)
    
    # Verify that the number of messages matches expected
    assert len(mock_bot.sent_messages) == len(expected_parts)
    
    # Verify that each message matches the expected parts
    for i, (actual, expected) in enumerate(zip(mock_bot.sent_messages, expected_parts)):
        assert actual['text'] == expected, f"Message {i} does not match expected"
    
    print(f"Message processed as {len(mock_bot.sent_messages)} parts")
    print("[PASS] Exact 4000 character boundary test passed")


async def test_empty_message():
    """Test behavior with an empty message"""
    print("\n=== Testing Empty Message ===")
    empty_message = ""
    
    mock_bot = MockBot()
    await send_ai_response(chat_id=123, text=empty_message, bot=mock_bot)
    
    # Generate expected results using our simulation
    expected_parts = simulate_send_ai_response(empty_message)
    
    # Verify that the number of messages matches expected
    assert len(mock_bot.sent_messages) == len(expected_parts)
    
    # Verify that each message matches the expected parts
    for i, (actual, expected) in enumerate(zip(mock_bot.sent_messages, expected_parts)):
        assert actual['text'] == expected, f"Message {i} does not match expected"
    
    print("[PASS] Empty message test passed")


async def main():
    """Run all tests"""
    print("Testing send_ai_response function...")
    
    await test_short_message()
    await test_long_message()
    await test_paragraph_splitting()
    await test_long_paragraph_chunking()
    await test_exact_4000_char_boundary()
    await test_empty_message()
    
    print("\n[SUCCESS] All tests passed!")


if __name__ == "__main__":
    asyncio.run(main())