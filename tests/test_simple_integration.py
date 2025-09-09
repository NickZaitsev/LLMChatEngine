import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import json
from unittest.mock import Mock, patch, MagicMock
import redis

from message_manager import MessageQueueManager, MessageDispatcher

async def test_basic_integration():
    """Test basic integration between MessageQueueManager and MessageDispatcher with mocked Redis"""
    redis_url = "redis://localhost:6379/15"  # Use database 15 for testing
    user_id = 12345
    chat_id = 67890
    test_message = "Hello, this is a test message!"
    
    try:
        with patch('redis.Redis.ping') as mock_ping, \
             patch('redis.Redis.rpush') as mock_rpush, \
             patch('redis.Redis.sadd') as mock_sadd, \
             patch('redis.Redis.llen') as mock_llen, \
             patch('redis.Redis.sismember') as mock_sismember, \
             patch('redis.Redis.set') as mock_set, \
             patch('redis.Redis.get') as mock_get, \
             patch('redis.Redis.delete') as mock_delete, \
             patch('redis.Redis.register_script') as mock_register_script:
            
            # Mock Redis methods
            mock_ping.return_value = True
            mock_rpush.return_value = 1
            mock_sadd.return_value = 1
            mock_llen.return_value = 1
            mock_sismember.return_value = True
            mock_set.return_value = True
            mock_get.return_value = None
            mock_delete.return_value = 1
            
            # Mock Lua scripts
            mock_script = Mock()
            mock_script.return_value = 1  # 1 for success, 0 for failure
            mock_register_script.return_value = mock_script
            
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
            
            print("[PASS] Message enqueued successfully")
            
            # Verify user was added to active users set
            # We can't directly test this with our current mock setup, but we know rpush and sadd were called
            mock_sadd.assert_called_once_with("dispatcher:active_users", user_id)
            
            print("[PASS] User added to active users set")
            
            # Test acquiring lock
            lock_acquired = dispatcher.acquire_lock(user_id)
            assert lock_acquired, "Should be able to acquire lock"
            
            print("[PASS] Lock acquired successfully")
            
            # Test releasing lock
            lock_released = dispatcher.release_lock(user_id)
            assert lock_released, "Should be able to release lock"
            
            print("[PASS] Lock released successfully")
            
            
            
            print("[SUCCESS] Basic integration test passed!")
            
    except Exception as e:
        print(f"[FAIL] Basic integration test failed: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(test_basic_integration())