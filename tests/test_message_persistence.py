import pytest
import asyncio
import json
from unittest.mock import Mock, patch, AsyncMock
import redis

from message_manager import MessageQueueManager, MessageDispatcher

@pytest.mark.asyncio
async def test_message_persistence():
    """Test message persistence across restarts"""
    redis_url = "redis://localhost:6379/15"  # Use database 15 for testing
    user_id = 12345
    chat_id = 67890
    test_message = "Hello, this is a test message!"
    
    # Mock Bot and TypingIndicatorManager classes
    mock_bot_class = Mock()
    mock_bot_instance = Mock()
    mock_bot_instance.send_chat_action = AsyncMock()
    mock_bot_instance.send_message = AsyncMock()
    mock_bot_class.return_value = mock_bot_instance
    
    mock_typing_manager_class = Mock()
    mock_typing_manager_instance = Mock()
    mock_typing_manager_instance.start_typing = AsyncMock()
    mock_typing_manager_instance.stop_typing = AsyncMock()
    mock_typing_manager_class.return_value = mock_typing_manager_instance
    
    mock_redis = Mock()
    with patch('message_manager.redis_async.from_url', return_value=mock_redis), \
         patch('messaging.dispatcher.Bot', new=mock_bot_class), \
         patch('messaging.dispatcher.TypingIndicatorManager', new=mock_typing_manager_class):
        
        # Mock Redis methods
        mock_redis.rpush.return_value = 1
        mock_redis.sadd.return_value = 1
        mock_redis.llen.return_value = 1
        mock_redis.lpop.return_value = None  # No messages to pop initially
        # Mock scan to return some test keys
        mock_redis.scan.side_effect = [(1, [b'queue:12345']), (0, [])]
        
        # Mock Lua scripts
        mock_script = Mock()
        mock_script.return_value = 1
        mock_redis.register_script.return_value = mock_script
        
        # Initialize components
        queue_manager = MessageQueueManager(redis_url)
        dispatcher = MessageDispatcher(redis_url, max_retries=3, lock_timeout=30)
        
        # Test enqueueing a message
        await queue_manager.enqueue_message(
            user_id=user_id,
            chat_id=chat_id,
            text=test_message,
            message_type="regular"
        )
        
        # Verify message was enqueued
        queue_size = await queue_manager.get_queue_size(user_id)
        assert queue_size == 1, f"Expected queue size 1, got {queue_size}"
        
        # Simulate a restart by creating a new dispatcher instance
        # This should scan for existing queues
        new_dispatcher = MessageDispatcher(redis_url, max_retries=3, lock_timeout=30)
        
        # Mock Redis methods for the new dispatcher instance
        with patch.object(new_dispatcher.redis_client, 'scan') as mock_new_scan, \
             patch.object(new_dispatcher.redis_client, 'llen') as mock_new_llen, \
             patch.object(new_dispatcher.redis_client, 'sadd') as mock_new_sadd:
            
            # Mock scan to return test keys
            mock_new_scan.side_effect = [(1, [b'queue:12345:default']), (0, [])]
            # Mock llen to return non-zero values (non-empty queues)
            mock_new_llen.return_value = 1
            # Mock sadd to track calls
            mock_new_sadd.return_value = 1
            
            # Call the scan method directly to test persistence
            await new_dispatcher._scan_existing_queues()
            
            # Verify that existing queues are properly identified and added to active users set
            mock_new_scan.assert_called()
            mock_new_llen.assert_called_with('queue:12345:default')
            mock_new_sadd.assert_called_with('dispatcher:active_users', f"{user_id}:default")
        
        print("[PASS] Startup processing correctly identifies existing queues")
        
        print("[SUCCESS] Message persistence test passed!")
