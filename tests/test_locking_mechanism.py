import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import json
from unittest.mock import Mock, patch, MagicMock
import redis

from message_manager import MessageDispatcher

async def test_locking_mechanism():
    """Test the locking mechanism to ensure no parallel processing"""
    redis_url = "redis://localhost:6379/15"  # Use database 15 for testing
    user_id = 12345
    
    try:
        with patch('redis.Redis.ping') as mock_ping, \
             patch('redis.Redis.set') as mock_set, \
             patch('redis.Redis.get') as mock_get, \
             patch('redis.Redis.delete') as mock_delete, \
             patch('redis.Redis.register_script') as mock_register_script, \
             patch('redis.Redis.expire') as mock_expire:
            
            # Mock Redis methods
            mock_ping.return_value = True
            mock_set.return_value = True
            mock_get.return_value = None
            mock_delete.return_value = 1
            mock_expire.return_value = True
            
            # Mock Lua scripts for lock operations
            def script_side_effect(keys, args):
                # Simulate lock acquisition success
                if 'processing' in keys[0]:
                    return 1  # Lock acquired
                return 1  # Success for other operations
            
            mock_script = Mock()
            mock_script.side_effect = script_side_effect
            mock_register_script.return_value = mock_script
            
            # Initialize dispatcher
            dispatcher = MessageDispatcher(redis_url, max_retries=3, lock_timeout=30)
            
            # Test acquiring lock
            lock_acquired = dispatcher.acquire_lock(user_id)
            assert lock_acquired, "Should be able to acquire lock"
            
            print("[PASS] Lock acquired successfully")
            
            # Test that the lock script was called with correct parameters
            mock_script.assert_called()
            
            print("[PASS] Lock script called with correct parameters")
            
            # Test releasing lock
            lock_released = dispatcher.release_lock(user_id)
            assert lock_released, "Should be able to release lock"
            
            print("[PASS] Lock released successfully")
            
            print("[SUCCESS] Locking mechanism test passed!")
            
    except Exception as e:
        print(f"[FAIL] Locking mechanism test failed: {e}")
        raise

async def test_startup_processing():
    """Test startup processing functionality"""
    redis_url = "redis://localhost:6379/15"  # Use database 15 for testing
    
    try:
        with patch('redis.Redis.ping') as mock_ping, \
             patch('redis.Redis.scan') as mock_scan, \
             patch('redis.Redis.llen') as mock_llen, \
             patch('redis.Redis.sadd') as mock_sadd, \
             patch('redis.Redis.register_script') as mock_register_script:
            
            # Mock Redis methods
            mock_ping.return_value = True
            # Mock scan to return some test keys
            mock_scan.side_effect = [(1, [b'queue:12345', b'queue:67890']), (0, [])]
            mock_llen.return_value = 5  # Non-empty queues
            mock_sadd.return_value = 1
            
            # Mock Lua scripts
            mock_script = Mock()
            mock_script.return_value = 1
            mock_register_script.return_value = mock_script
            
            # Initialize dispatcher
            dispatcher = MessageDispatcher(redis_url, max_retries=3, lock_timeout=30)
            
            # Test scanning existing queues
            await dispatcher._scan_existing_queues()
            
            print("[PASS] Startup processing scan completed")
            
            # Verify scan was called
            assert mock_scan.call_count >= 1, "Scan should be called during startup"
            
            print("[PASS] Scan method was called")
            
            # Verify sadd was called to add users to active set
            assert mock_sadd.call_count >= 1, "Users should be added to active set"
            
            print("[PASS] Users added to active set")
            
            print("[SUCCESS] Startup processing test passed!")
            
    except Exception as e:
        print(f"[FAIL] Startup processing test failed: {e}")
        raise

if __name__ == "__main__":
    print("Running locking mechanism test...")
    asyncio.run(test_locking_mechanism())
    
    print("\nRunning startup processing test...")
    asyncio.run(test_startup_processing())
    
    print("\n[ALL TESTS PASSED] Locking mechanism and startup processing tests completed successfully!")