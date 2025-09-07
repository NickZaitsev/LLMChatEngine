"""
Tests for the proactive messaging revocation tracking functionality.
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


class TestProactiveMessagingRevocationTracking(unittest.TestCase):
    """Test cases for the proactive messaging revocation tracking functionality."""
    
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
    
    def test_revoke_user_tasks_tracks_revoked_tasks(self):
        """Test that _revoke_user_tasks calls _add_revoked_task for each revoked task."""
        user_id = 12345
        task_ids = [b'task1', b'task2', b'task3']
        message_type = "RegularReachout"
        
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
            
            # Mock _add_revoked_task
            self.service._add_revoked_task = MagicMock()
            
            # Call the method to revoke tasks
            self.service._revoke_user_tasks(user_id, user_state, message_type)
            
            # Check that _add_revoked_task was called for each task
            self.assertEqual(self.service._add_revoked_task.call_count, len(task_ids))
            for task_id_bytes in task_ids:
                task_id = task_id_bytes.decode('utf-8') if isinstance(task_id_bytes, bytes) else task_id_bytes
                self.service._add_revoked_task.assert_any_call(user_id, task_id, message_type)
    
    def test_revoke_all_user_tasks_tracks_revoked_tasks(self):
        """Test that _revoke_all_user_tasks calls _add_revoked_task for each revoked task."""
        user_id = 12345
        task_keys = [
            f"proactive_messaging:user:{user_id}:tasks:RegularReachout".encode('utf-8'),
            f"proactive_messaging:user:{user_id}:tasks:Ad".encode('utf-8')
        ]
        task_ids_by_type = {
            task_keys[0]: [b'task1', b'task2'],
            task_keys[1]: [b'task3']
        }
        message_types = ["RegularReachout", "Ad"]
        
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
            
            # Mock _add_revoked_task
            self.service._add_revoked_task = MagicMock()
            
            # Call the method to revoke all tasks
            self.service._revoke_all_user_tasks(user_id, user_state)
            
            # Check that _add_revoked_task was called for each task
            expected_total_calls = sum(len(task_ids) for task_ids in task_ids_by_type.values())
            self.assertEqual(self.service._add_revoked_task.call_count, expected_total_calls)
            
            # Check calls for each message type
            call_index = 0
            for i, task_key in enumerate(task_keys):
                message_type = message_types[i]
                task_ids = task_ids_by_type[task_key]
                for task_id_bytes in task_ids:
                    task_id = task_id_bytes.decode('utf-8') if isinstance(task_id_bytes, bytes) else task_id_bytes
                    self.service._add_revoked_task.assert_any_call(user_id, task_id, message_type)
    
    def test_is_task_revoked_returns_true_for_revoked_task(self):
        """Test that _is_task_revoked returns True for a revoked task."""
        user_id = 12345
        task_id = "task123"
        message_type = "RegularReachout"
        
        # Mock Redis sismember to return True (task is revoked)
        self.mock_redis.sismember.return_value = True
        
        # Call the method
        result = self.service._is_task_revoked(user_id, task_id, message_type)
        
        # Check that Redis sismember was called with the correct key and value
        expected_key = f"proactive_messaging:user:{user_id}:revoked_tasks:{message_type}"
        self.mock_redis.sismember.assert_called_once_with(expected_key, task_id)
        
        # Check that the result is True
        self.assertTrue(result)
    
    def test_is_task_revoked_returns_false_for_non_revoked_task(self):
        """Test that _is_task_revoked returns False for a non-revoked task."""
        user_id = 12345
        task_id = "task123"
        message_type = "RegularReachout"
        
        # Mock Redis sismember to return False (task is not revoked)
        self.mock_redis.sismember.return_value = False
        
        # Call the method
        result = self.service._is_task_revoked(user_id, task_id, message_type)
        
        # Check that Redis sismember was called with the correct key and value
        expected_key = f"proactive_messaging:user:{user_id}:revoked_tasks:{message_type}"
        self.mock_redis.sismember.assert_called_once_with(expected_key, task_id)
        
        # Check that the result is False
        self.assertFalse(result)
    
    def test_send_proactive_message_skips_revoked_task(self):
        """Test that send_proactive_message skips execution for a revoked task."""
        user_id = 12345
        task_id = "task123"
        
        # Create a mock task instance
        mock_task = MagicMock()
        mock_task.request.id = task_id
        
        # Mock user state
        user_state = {
            'cadence': '1h',
            'consecutive_outreaches': 0,
            'last_proactive_message': None,
            'user_replied': False
        }
        
        # Mock _get_user_state to return the user state
        self.service._get_user_state = MagicMock(return_value=user_state)
        
        # Mock _is_task_revoked to return True (task is revoked)
        self.service._is_task_revoked = MagicMock(return_value=True)
        
        # Mock _set_user_state
        self.service._set_user_state = MagicMock()
        
        # Mock the logger
        self.service.logger = MagicMock()
        
        # Mock Redis srem
        self.service.redis_client.srem = MagicMock()
        
        # Call the task function
        with patch('proactive_messaging.proactive_messaging_service', self.service):
            send_proactive_message(mock_task, user_id)
        
        # Check that _is_task_revoked was called
        self.service._is_task_revoked.assert_called_once_with(user_id, task_id, "RegularReachout")
        
        # Check that the task was skipped (no further processing)
        self.service._set_user_state.assert_not_called()
        
        # Check that Redis srem was called to remove the task
        expected_key = f"proactive_messaging:user:{user_id}:tasks:RegularReachout"
        self.service.redis_client.srem.assert_called_once_with(expected_key, task_id)
        
        # Check that the logger was called with the correct message
        self.service.logger.info.assert_any_call(
            f"Task {task_id} for user {user_id} has been revoked, skipping execution"
        )
    
    def test_send_proactive_message_executes_non_revoked_task(self):
        """Test that send_proactive_message executes for a non-revoked task."""
        user_id = 12345
        task_id = "task123"
        
        # Create a mock task instance
        mock_task = MagicMock()
        mock_task.request.id = task_id
        mock_task.retry = MagicMock()
        
        # Mock user state
        user_state = {
            'cadence': '1h',
            'consecutive_outreaches': 0,
            'last_proactive_message': None,
            'user_replied': False
        }
        
        # Mock _get_user_state to return the user state
        self.service._get_user_state = MagicMock(return_value=user_state)
        
        # Mock _is_task_revoked to return False (task is not revoked)
        self.service._is_task_revoked = MagicMock(return_value=False)
        
        # Mock _set_user_state
        self.service._set_user_state = MagicMock()
        
        # Mock the logger
        self.service.logger = MagicMock()
        
        # Mock Redis srem
        self.service.redis_client.srem = MagicMock()
        
        # Mock the rest of the task execution
        with patch('proactive_messaging.PostgresConversationManager') as mock_conversation_manager, \
             patch('proactive_messaging.MemoryManager') as mock_memory_manager, \
             patch('proactive_messaging.PromptAssembler') as mock_prompt_assembler, \
             patch('proactive_messaging.AIHandler') as mock_ai_handler, \
             patch('proactive_messaging.TypingIndicatorManager') as mock_typing_manager, \
             patch('proactive_messaging.Bot') as mock_bot, \
             patch('proactive_messaging.run_with_timeout') as mock_run_with_timeout, \
             patch('proactive_messaging.clean_ai_response') as mock_clean_ai_response, \
             patch('proactive_messaging.send_ai_response') as mock_send_ai_response:
            
            # Configure mocks
            mock_conversation_manager_instance = MagicMock()
            mock_conversation_manager.return_value = mock_conversation_manager_instance
            mock_conversation_manager_instance.storage.messages = MagicMock()
            mock_conversation_manager_instance.storage.memories = MagicMock()
            mock_conversation_manager_instance.storage.conversations = MagicMock()
            mock_conversation_manager_instance.storage.personas = MagicMock()
            
            mock_memory_manager_instance = MagicMock()
            mock_memory_manager.return_value = mock_memory_manager_instance
            
            mock_prompt_assembler_instance = MagicMock()
            mock_prompt_assembler.return_value = mock_prompt_assembler_instance
            
            mock_ai_handler_instance = MagicMock()
            mock_ai_handler.return_value = mock_ai_handler_instance
            mock_ai_handler_instance.prompt_assembler = mock_prompt_assembler_instance
            
            mock_typing_manager_instance = MagicMock()
            mock_typing_manager.return_value = mock_typing_manager_instance
            
            mock_bot_instance = MagicMock()
            mock_bot.return_value = mock_bot_instance
            
            mock_run_with_timeout.return_value = MagicMock()
            
            mock_clean_ai_response.return_value = "Cleaned response"
            
            # Call the task function
            with patch('proactive_messaging.proactive_messaging_service', self.service):
                send_proactive_message(mock_task, user_id)
            
            # Check that _is_task_revoked was called
            self.service._is_task_revoked.assert_called_once_with(user_id, task_id, "RegularReachout")
            
            # Check that the task continued execution (user state was updated)
            self.service._set_user_state.assert_called()
            
            # Check that Redis srem was not called to remove the task yet (it's called at the end)
            self.service.redis_client.srem.assert_not_called()


if __name__ == '__main__':
    unittest.main()