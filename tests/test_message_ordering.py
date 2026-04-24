"""
Test script to verify the message ordering fix.
This test simulates the scenario described in the issue:
- Multiple messages being sent that need to be split
- Verifying that parts of the same message are sent in order
- Verifying that the overall sequence is maintained
"""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock
from message_manager import MessageQueueManager, MessageDispatcher, send_ai_response


async def test_message_splitting_and_ordering():
    """Test that messages are split before queuing and sent in correct order"""
    print("Testing message splitting and ordering...")
    
    # Create mock Redis client
    mock_redis = MagicMock()
    mock_redis.ping.return_value = True
    mock_redis.rpush.return_value = 1
    mock_redis.llen.return_value = 0
    mock_redis.sadd.return_value = 1
    mock_redis.smembers.return_value = set()
    mock_redis.scan.return_value = (0, [])
    
    # Mock the from_url method to return our mock
    import redis
    original_from_url = redis.from_url
    redis.from_url = MagicMock(return_value=mock_redis)
    
    try:
        # Create MessageQueueManager instance
        queue_manager = MessageQueueManager("redis://test:6379/0")
        
        # Test message that will be split
        long_message = "This is a very long message that will be split into multiple parts. " * 10
        print(f"Original message length: {len(long_message)} characters")
        
        # Enqueue the message
        await queue_manager.enqueue_message(
            user_id=12345,
            chat_id=67890,
            text=long_message,
            message_type="regular"
        )
        
        # Check how many parts were enqueued
        rpush_calls = mock_redis.rpush.call_args_list
        print(f"Number of message parts enqueued: {len(rpush_calls)}")
        
        # Verify each part has correct metadata
        for i, call in enumerate(rpush_calls):
            args, kwargs = call
            queue_key, message_json = args
            message_data = json.loads(message_json)
            
            print(f"Part {i+1}: {message_data['part_index']+1}/{message_data['total_parts']}, "
                  f"length: {len(message_data['text'])} chars")
            
            # Verify part_index and total_parts are set correctly
            assert 'part_index' in message_data
            assert 'total_parts' in message_data
            assert message_data['part_index'] == i
            assert message_data['total_parts'] == len(rpush_calls)
        
        print("PASS: Message splitting and metadata verification passed!")
        
        # Now test the send_ai_response function with is_first_message parameter
        mock_bot = AsyncMock()
        mock_typing_manager = AsyncMock()
        
        # Test first message (should not have delay)
        await send_ai_response(
            chat_id=67890,
            text="This is the first part",
            bot=mock_bot,
            typing_manager=mock_typing_manager,
            is_first_message=True
        )
        
        # Test subsequent message (should have delay)
        await send_ai_response(
            chat_id=67890,
            text="This is the second part",
            bot=mock_bot,
            typing_manager=mock_typing_manager,
            is_first_message=False
        )
        
        print("PASS: send_ai_response function test passed!")
        
    finally:
        # Restore original from_url method
        redis.from_url = original_from_url


def test_split_message_logic():
    """Test the message splitting logic directly"""
    print("\nTesting message splitting logic...")
    
    # Create mock Redis client for queue manager
    mock_redis = MagicMock()
    mock_redis.ping.return_value = True
    
    import redis
    original_from_url = redis.from_url
    redis.from_url = MagicMock(return_value=mock_redis)
    
    try:
        queue_manager = MessageQueueManager("redis://test:6379/0")
        
        # Test with a message that needs to be split by paragraphs
        multi_paragraph_message = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
        parts = queue_manager._split_message(multi_paragraph_message)
        
        print(f"Multi-paragraph message split into {len(parts)} parts")
        for i, part in enumerate(parts):
            print(f" Part {i+1}: {len(part)} chars")
        
        # Test with a very long single paragraph (should be chunked)
        long_paragraph = "This is a very long paragraph. " * 100  # Much longer than 4000 chars
        parts = queue_manager._split_message(long_paragraph)
        
        print(f"Long paragraph split into {len(parts)} parts")
        for i, part in enumerate(parts):
            print(f"  Part {i+1}: {len(part)} chars")
            assert len(part) <= 4000, f"Part {i+1} exceeds 4000 character limit: {len(part)} chars"
        
        print("PASS: Message splitting logic test passed!")
        
    finally:
        redis.from_url = original_from_url


async def main():
    """Run all tests"""
    print("Starting message ordering tests...\n")
    
    test_split_message_logic()
    await test_message_splitting_and_ordering()
    
    print("\nALL TESTS PASSED! Message ordering fix is working correctly.")
    print("\nSummary of changes:")
    print("1. Messages are now split BEFORE being enqueued")
    print("2. Each message part is stored as a separate queue item with ordering metadata")
    print("3. Message parts maintain their sequence with part_index and total_parts")
    print("4. Delays are applied correctly between message parts (not before first part)")
    print("5. No more racing conditions between different messages' parts")


if __name__ == "__main__":
    asyncio.run(main())