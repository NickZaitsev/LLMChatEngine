"""
Additional tests for the _revoke_user_tasks function in proactive messaging system.
These tests cover edge cases and error handling scenarios.
"""

import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime
import sys
import os
import json

# Add the parent directory to the path to import proactive_messaging
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from proactive_messaging import ProactiveMessagingService


class TestRevokeUserTasksAdditional(unittest.TestCase):
    """Additional test cases for the _revoke_user_tasks function."""
    
    def setUp(self):
        """Set up test fixtures before each test method."""
        # Patch Redis client to avoid connecting to a real Redis server
        self.redis_patch = patch('proactive_messaging.redis.from_url')
        self.mock_redis_client = self.redis_patch.start()
        
        # Patch the module-level logger
        self.logger_patch = patch('proactive_messaging.logger')
        self.mock_logger = self.logger_patch.start()
        
        # Create a mock Redis instance
        self.mock_redis = MagicMock()
        self.mock_redis_client.return_value = self.mock_redis
        
        # Initialize the service with mocked Redis
        self.service = ProactiveMessagingService()
    
    def tearDown(self):
        """Clean up after each test method."""
        self.redis_patch.stop()
        self.logger_patch.stop()
    
    def test_revoke_user_tasks_redis_exception(self):
        """Test _revoke_user_tasks when Redis smembers raises an exception."""
        user_id = 12345
        user_state = {
            'cadence': '1h',
            'consecutive_outreaches': 0,
            'last_proactive_message': None,
            'user_replied': False
        }
        
        # Mock Redis smembers to raise an exception
        self.mock_redis.smembers.side_effect = Exception("Redis error")
        
        # Call the method - should raise an exception
        with self.assertRaises(Exception) as context:
            self.service._revoke_user_tasks(user_id, user_state, "RegularReachout")
        
        # Check that the exception message is correct
        self.assertEqual(str(context.exception), "Redis error")
        
        # Check that logger.error was called with the expected message
        self.mock_logger.error.assert_called_with(
            f"Error revoking RegularReachout tasks for user 12345: Redis error"
        )
    
    def test_revoke_user_tasks_celery_revoke_exception(self):
        """Test _revoke_user_tasks when Celery revoke raises an exception."""
        user_id = 12345
        task_ids = [b'task1', b'task2']
        
        # Mock Redis smembers to return task IDs
        self.mock_redis.smembers.return_value = task_ids
        
        # Mock user state
        user_state = {
            'cadence': '1h',
            'consecutive_outreaches': 0,
            'last_proactive_message': None,
            'user_replied': False
        }
        
        # Mock the celery app control to raise an exception
        with patch('proactive_messaging.celery_app') as mock_celery_app:
            mock_celery_app.control.revoke.side_effect = Exception("Celery error")
            
            # Call the method - should raise an exception
            with self.assertRaises(Exception) as context:
                self.service._revoke_user_tasks(user_id, user_state, "RegularReachout")
            
            # Check that the exception message is correct
            self.assertEqual(str(context.exception), "Celery error")
            
            # Check that logger.error was called with the expected message
            self.mock_logger.error.assert_called_with(
                f"Error revoking RegularReachout tasks for user 12345: Celery error"
            )
    
    def test_revoke_user_tasks_redis_delete_exception(self):
        """Test _revoke_user_tasks when Redis delete raises an exception."""
        user_id = 12345
        task_ids = [b'task1', b'task2']
        
        # Mock Redis smembers to return task IDs
        self.mock_redis.smembers.return_value = task_ids
        
        # Mock Redis delete to raise an exception
        self.mock_redis.delete.side_effect = Exception("Redis delete error")
        
        # Mock user state
        user_state = {
            'cadence': '1h',
            'consecutive_outreaches': 0,
            'last_proactive_message': None,
            'user_replied': False
        }
        
        # Mock the celery app control
        with patch('proactive_messaging.celery_app') as mock_celery_app:
            mock_celery_app.control.revoke = MagicMock()
            
            # Call the method - should raise an exception
            with self.assertRaises(Exception) as context:
                self.service._revoke_user_tasks(user_id, user_state, "RegularReachout")
            
            # Check that the exception message is correct
            self.assertEqual(str(context.exception), "Redis delete error")
            
            # Check that logger.error was called with the expected message
            self.mock_logger.error.assert_called_with(
                f"Error revoking RegularReachout tasks for user 12345: Redis delete error"
            )
    
    def test_revoke_user_tasks_mixed_task_id_types(self):
        """Test _revoke_user_tasks with mixed string and bytes task IDs."""
        user_id = 12345
        task_ids = [b'task1', 'task2', b'task3']
        
        # Mock Redis smembers to return task IDs
        self.mock_redis.smembers.return_value = task_ids
        
        # Mock user state
        user_state = {
            'cadence': '1h',
            'consecutive_outreaches': 0,
            'last_proactive_message': None,
            'user_replied': False
        }
        
        # Mock the celery app control
        with patch('proactive_messaging.celery_app') as mock_celery_app:
            mock_celery_app.control.revoke = MagicMock()
            
            # Call the method
            self.service._revoke_user_tasks(user_id, user_state, "RegularReachout")
            
            # Check that celery_app.control.revoke was called for each task
            self.assertEqual(mock_celery_app.control.revoke.call_count, len(task_ids))
            
            # Check that all task IDs were processed correctly (as strings)
            expected_calls = [
                unittest.mock.call('task1', terminate=True),
                unittest.mock.call('task2', terminate=True),
                unittest.mock.call('task3', terminate=True)
            ]
            mock_celery_app.control.revoke.assert_has_calls(expected_calls, any_order=True)
    
    def test_revoke_user_tasks_different_message_types(self):
        """Test _revoke_user_tasks with different message types."""
        user_id = 12345
        task_ids = [b'task1', b'task2']
        
        # Mock Redis smembers to return task IDs
        self.mock_redis.smembers.return_value = task_ids
        
        # Mock user state
        user_state = {
            'cadence': '1h',
            'consecutive_outreaches': 0,
            'last_proactive_message': None,
            'user_replied': False
        }
        
        # Test with different message types
        message_types = ["RegularReachout", "Ad", "Reminder"]
        
        for message_type in message_types:
            # Reset mock call count
            self.mock_redis.reset_mock()
            
            with patch('proactive_messaging.celery_app') as mock_celery_app:
                mock_celery_app.control.revoke = MagicMock()
                
                # Call the method
                self.service._revoke_user_tasks(user_id, user_state, message_type)
                
                # Check that Redis smembers was called with the correct key
                expected_key = f"proactive_messaging:user:{user_id}:tasks:{message_type}"
                self.mock_redis.smembers.assert_called_once_with(expected_key)
    
    def test_revoke_user_tasks_empty_bytes_task_id(self):
        """Test _revoke_user_tasks with empty bytes task ID."""
        user_id = 12345
        task_ids = [b'', b'task2']
        
        # Mock Redis smembers to return task IDs
        self.mock_redis.smembers.return_value = task_ids
        
        # Mock user state
        user_state = {
            'cadence': '1h',
            'consecutive_outreaches': 0,
            'last_proactive_message': None,
            'user_replied': False
        }
        
        # Mock the celery app control
        with patch('proactive_messaging.celery_app') as mock_celery_app:
            mock_celery_app.control.revoke = MagicMock()
            
            # Call the method
            self.service._revoke_user_tasks(user_id, user_state, "RegularReachout")
            
            # Check that celery_app.control.revoke was called only for non-empty task IDs
            # Empty task IDs should be skipped
            self.assertEqual(mock_celery_app.control.revoke.call_count, 1)
            
            # Check that only the non-empty task ID was processed
            expected_calls = [
                unittest.mock.call('task2', terminate=True)
            ]
            mock_celery_app.control.revoke.assert_has_calls(expected_calls, any_order=True)
    
    def test_revoke_user_tasks_none_task_id(self):
        """Test _revoke_user_tasks with None task ID."""
        user_id = 12345
        task_ids = [None, b'task2']
        
        # Mock Redis smembers to return task IDs
        self.mock_redis.smembers.return_value = task_ids
        
        # Mock user state
        user_state = {
            'cadence': '1h',
            'consecutive_outreaches': 0,
            'last_proactive_message': None,
            'user_replied': False
        }
        
        # Mock the celery app control
        with patch('proactive_messaging.celery_app') as mock_celery_app:
            mock_celery_app.control.revoke = MagicMock()
            
            # Call the method
            self.service._revoke_user_tasks(user_id, user_state, "RegularReachout")
            
            # Check that only the non-None task was processed
            # None values should be skipped
            self.assertEqual(mock_celery_app.control.revoke.call_count, 1)
            
            # Check that the non-None task ID was processed correctly
            expected_calls = [
                unittest.mock.call('task2', terminate=True)
            ]
            mock_celery_app.control.revoke.assert_has_calls(expected_calls, any_order=True)
    
    def test_revoke_user_tasks_non_list_redis_response(self):
        """Test _revoke_user_tasks when Redis returns unexpected data type."""
        user_id = 12345
        
        # Mock Redis smembers to return unexpected data type
        self.mock_redis.smembers.return_value = "not_a_list"
        
        # Mock user state
        user_state = {
            'cadence': '1h',
            'consecutive_outreaches': 0,
            'last_proactive_message': None,
            'user_replied': False
        }
        
        # Mock the celery app control
        with patch('proactive_messaging.celery_app') as mock_celery_app:
            mock_celery_app.control.revoke = MagicMock()
            
            # Call the method - should not raise an exception
            try:
                self.service._revoke_user_tasks(user_id, user_state, "RegularReachout")
                success = True
            except Exception:
                success = False
            
            # Should not raise an exception
            self.assertTrue(success)


if __name__ == '__main__':
    unittest.main()