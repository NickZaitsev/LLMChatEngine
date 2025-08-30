"""
Tests for the proactive messaging task revocation functionality.
"""

import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
import sys
import os
import json

# Add the parent directory to the path to import proactive_messaging
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from proactive_messaging import (
    ProactiveMessagingService,
    send_proactive_message,
    schedule_next_message
)


class TestProactiveMessagingTaskRevocation(unittest.TestCase):
    """Test cases for the proactive messaging task revocation functionality."""
    
    def setUp(self):
        """Set up test fixtures before each test method."""
        # Patch Redis client to avoid connecting to a real Redis server
        self.redis_patch = patch('proactive_messaging.redis.from_url')
        self.mock_redis_client = self.redis_patch.start()
        
        # Create a mock Redis instance
        self.mock_redis = MagicMock()
        self.mock_redis_client.return_value = self.mock_redis
        
        # Initialize the service with mocked Redis
        self.service = ProactiveMessagingService()
        
        # Mock the logger to prevent actual logging during tests
        self.service.logger = MagicMock()
    
    def tearDown(self):
        """Clean up after each test method."""
        self.redis_patch.stop()
    
    def test_revoke_user_tasks_by_type(self):
        """Test revoking user tasks by message type."""
        user_id = 12345
        task_ids = [b'task1', b'task2', b'task3']
        
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
            
            # Call the method to revoke tasks
            self.service._revoke_user_tasks(user_id, user_state, "RegularReachout")
            
            # Check that Redis smembers was called with the correct key
            expected_key = f"proactive_messaging:user:{user_id}:tasks:RegularReachout"
            self.mock_redis.smembers.assert_called_once_with(expected_key)
            
            # Check that celery_app.control.revoke was called for each task
            self.assertEqual(mock_celery_app.control.revoke.call_count, len(task_ids))
            for task_id in task_ids:
                task_id_str = task_id.decode('utf-8') if isinstance(task_id, bytes) else task_id
                mock_celery_app.control.revoke.assert_any_call(task_id_str, terminate=True)
            
            # Check that Redis delete was called with the correct key
            self.mock_redis.delete.assert_called_once_with(expected_key)
    
    def test_revoke_user_tasks_no_tasks(self):
        """Test revoking user tasks when no tasks exist."""
        user_id = 12345
        
        # Mock Redis smembers to return empty list
        self.mock_redis.smembers.return_value = []
        
        # Mock user state
        user_state = {
            'cadence': '1h',
            'consecutive_outreaches': 0,
            'last_proactive_message': None,
            'user_replied': False
        }
        
        # Call the method to revoke tasks
        self.service._revoke_user_tasks(user_id, user_state, "RegularReachout")
        
        # Check that Redis smembers was called with the correct key
        expected_key = f"proactive_messaging:user:{user_id}:tasks:RegularReachout"
        self.mock_redis.smembers.assert_called_once_with(expected_key)
        
        # Check that Redis delete was not called since there were no tasks
        self.mock_redis.delete.assert_not_called()
    
    def test_revoke_all_user_tasks(self):
        """Test revoking all user tasks regardless of message type."""
        user_id = 12345
        task_keys = [
            f"proactive_messaging:user:{user_id}:tasks:RegularReachout".encode('utf-8'),
            f"proactive_messaging:user:{user_id}:tasks:Ad".encode('utf-8')
        ]
        task_ids_by_type = {
            task_keys[0]: [b'task1', b'task2'],
            task_keys[1]: [b'task3']
        }
        
        # Mock Redis keys to return task keys
        self.mock_redis.keys.return_value = task_keys
        
        # Mock Redis smembers to return task IDs for each key
        def mock_smembers(key):
            return task_ids_by_type.get(key, [])
        self.mock_redis.smembers.side_effect = mock_smembers
        
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
            
            # Call the method to revoke all tasks
            self.service._revoke_all_user_tasks(user_id, user_state)
            
            # Check that Redis keys was called with the correct pattern
            expected_pattern = f"proactive_messaging:user:{user_id}:tasks:*"
            self.mock_redis.keys.assert_called_once_with(expected_pattern)
            
            # Check that celery_app.control.revoke was called for each task
            expected_total_calls = sum(len(task_ids) for task_ids in task_ids_by_type.values())
            self.assertEqual(mock_celery_app.control.revoke.call_count, expected_total_calls)
            
            # Check that Redis delete was called for each task key
            self.assertEqual(self.mock_redis.delete.call_count, len(task_keys))
            for key in task_keys:
                self.mock_redis.delete.assert_any_call(key)
    
    def test_add_task_id_with_message_type(self):
        """Test adding a task ID with message type."""
        user_id = 12345
        task_id = "task123"
        message_type = "RegularReachout"
        
        # Call the method to add task ID
        self.service._add_task_id(user_id, task_id, message_type)
        
        # Check that Redis sadd was called with the correct key and value
        expected_key = f"proactive_messaging:user:{user_id}:tasks:{message_type}"
        self.mock_redis.sadd.assert_called_once_with(expected_key, task_id)
    
    def test_schedule_proactive_message_stores_task_id(self):
        """Test that scheduling a proactive message stores the task ID."""
        user_id = 12345
        message_type = "RegularReachout"
        
        # Enable proactive messaging
        self.service.enabled = True
        
        # Mock user state in Redis
        user_state = {
            'cadence': '1h',
            'consecutive_outreaches': 0,
            'last_proactive_message': None,
            'user_replied': False
        }
        self.mock_redis.get.return_value = json.dumps(user_state)
        
        # Mock the Celery task
        mock_task = MagicMock()
        mock_task.id = "task123"
        
        with patch('proactive_messaging.send_proactive_message') as mock_send_task:
            mock_send_task.apply_async.return_value = mock_task
            
            # Call the method to schedule a proactive message
            self.service.schedule_proactive_message(user_id, message_type=message_type)
            
            # Check that the task was scheduled
            mock_send_task.apply_async.assert_called_once()
            
            # Check that the task ID was added to Redis
            expected_key = f"proactive_messaging:user:{user_id}:tasks:{message_type}"
            self.mock_redis.sadd.assert_called_once_with(expected_key, mock_task.id)


if __name__ == '__main__':
    unittest.main()