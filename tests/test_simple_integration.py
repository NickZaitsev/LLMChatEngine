import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from unittest.mock import Mock, patch

from messaging import MessageQueueManager, MessageDispatcher

async def test_basic_integration():
    """Test basic integration between MessageQueueManager and MessageDispatcher with mocked Redis"""
    redis_url = "redis://localhost:6379/15"  # Use database 15 for testing
    user_id = 12345
    chat_id = 67890
    test_message = "Hello, this is a test message!"
    
    try:
        mock_redis = Mock()
        with patch('messaging.queue.redis_async.from_url', return_value=mock_redis):
            
            # Mock Redis methods
            mock_redis.rpush.return_value = 1
            mock_redis.sadd.return_value = 1
            mock_redis.llen.return_value = 1
            mock_redis.sismember.return_value = True
            mock_redis.set.return_value = True
            mock_redis.get.return_value = None
            mock_redis.delete.return_value = 1
            
            # Mock Lua scripts
            mock_script = Mock()
            mock_script.return_value = 1  # 1 for success, 0 for failure
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
            
            print("[PASS] Message enqueued successfully")
            
            queue_manager.enqueue_script.assert_called_once()
            enqueue_call = queue_manager.enqueue_script.call_args.kwargs
            assert enqueue_call["keys"] == [f"queue:{user_id}:default", "dispatcher:active_users"]
            assert enqueue_call["args"][0] == f"{user_id}:default"
            
            print("[PASS] User added to active users set")
            
            # Test acquiring lock
            lock_acquired = await dispatcher.acquire_lock(user_id)
            assert lock_acquired, "Should be able to acquire lock"
            
            print("[PASS] Lock acquired successfully")
            
            # Test releasing lock
            lock_released = await dispatcher.release_lock(user_id)
            assert lock_released, "Should be able to release lock"
            
            print("[PASS] Lock released successfully")
            
            
            
            print("[SUCCESS] Basic integration test passed!")
            
    except Exception as e:
        print(f"[FAIL] Basic integration test failed: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(test_basic_integration())
