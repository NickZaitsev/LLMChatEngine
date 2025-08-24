"""
Tests for the proactive messaging system.
"""

import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
import sys
import os

# Add the parent directory to the path to import proactive_messaging
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from proactive_messaging import (
    ProactiveMessagingService,
    CADENCE_LEVELS,
    INTERVALS,
    JITTERS
)

class TestProactiveMessagingService(unittest.TestCase):
    """Test cases for the ProactiveMessagingService class."""
    
    def setUp(self):
        """Set up test fixtures before each test method."""
        self.service = ProactiveMessagingService()
        
        # Mock the logger to prevent actual logging during tests
        self.service.logger = MagicMock()
    
    def test_parse_time_valid(self):
        """Test parsing valid time strings."""
        hours, minutes = self.service.parse_time("14:30")
        self.assertEqual(hours, 14)
        self.assertEqual(minutes, 30)
        
        hours, minutes = self.service.parse_time("02:05")
        self.assertEqual(hours, 2)
        self.assertEqual(minutes, 5)
    
    def test_parse_time_invalid(self):
        """Test parsing invalid time strings."""
        hours, minutes = self.service.parse_time("invalid")
        self.assertEqual(hours, 0)
        self.assertEqual(minutes, 0)
        
        hours, minutes = self.service.parse_time("25:70")
        self.assertEqual(hours, 25)
        self.assertEqual(minutes, 70)
    
    def test_is_within_quiet_hours(self):
        """Test checking if time is within quiet hours."""
        # Set quiet hours for testing
        self.service.quiet_hours_start = "02:30"
        self.service.quiet_hours_end = "08:00"
        
        # Test time within quiet hours
        test_time = datetime(2023, 1, 1, 5, 0)  # 5:00 AM
        self.assertTrue(self.service.is_within_quiet_hours(test_time))
        
        # Test time outside quiet hours
        test_time = datetime(2023, 1, 1, 10, 0)  # 10:00 AM
        self.assertFalse(self.service.is_within_quiet_hours(test_time))
        
        # Test boundary times
        test_time = datetime(2023, 1, 1, 2, 30)  # Start of quiet hours
        self.assertTrue(self.service.is_within_quiet_hours(test_time))
        
        test_time = datetime(2023, 1, 1, 8, 0)  # End of quiet hours
        self.assertFalse(self.service.is_within_quiet_hours(test_time))
    
    def test_adjust_for_quiet_hours(self):
        """Test adjusting scheduled time for quiet hours."""
        # Set quiet hours for testing
        self.service.quiet_hours_start = "02:30"
        self.service.quiet_hours_end = "08:00"
        
        # Test time within quiet hours
        scheduled_time = datetime(2023, 1, 1, 5, 0)  # 5:00 AM
        adjusted_time = self.service.adjust_for_quiet_hours(scheduled_time)
        
        # Should be adjusted to end of quiet hours plus buffer
        expected_time = datetime(2023, 1, 1, 8, 5)  # 8:05 AM
        self.assertEqual(adjusted_time, expected_time)
        
        # Test time outside quiet hours (should remain unchanged)
        scheduled_time = datetime(2023, 1, 1, 10, 0)  # 10:00 AM
        adjusted_time = self.service.adjust_for_quiet_hours(scheduled_time)
        self.assertEqual(adjusted_time, scheduled_time)
    
    def test_get_next_interval(self):
        """Test getting the next interval in cadence escalation."""
        # Test normal progression
        self.assertEqual(self.service.get_next_interval('1h'), '9h')
        self.assertEqual(self.service.get_next_interval('9h'), '1d')
        self.assertEqual(self.service.get_next_interval('1d'), '1w')
        self.assertEqual(self.service.get_next_interval('1w'), '1mo')
        
        # Test last level (should stay at last level)
        self.assertEqual(self.service.get_next_interval('1mo'), '1mo')
        
        # Test invalid current cadence (should start from beginning)
        self.assertEqual(self.service.get_next_interval('invalid'), '1h')
    
    def test_get_interval_with_jitter(self):
        """Test getting interval with jitter applied."""
        # Test with 1h cadence
        interval = self.service.get_interval_with_jitter('1h')
        
        # Should be base interval (3600) plus or minus jitter (900)
        # So between 2700 and 4500 seconds
        self.assertGreaterEqual(interval, 2700)
        self.assertLessEqual(interval, 4500)
        
        # Test minimum interval (should be at least 60 seconds)
        with patch.dict(JITTERS, {'1h': 3600}):  # Large jitter
            interval = self.service.get_interval_with_jitter('1h')
            self.assertGreaterEqual(interval, 60)
    
    def test_should_switch_to_long_term_mode(self):
        """Test checking if user should switch to long-term mode."""
        user_id = 12345
        
        # Test with fewer than max consecutive outreaches
        self.service.user_states[user_id] = {'consecutive_outreaches': 3}
        self.assertFalse(self.service.should_switch_to_long_term_mode(user_id))
        
        # Test with exactly max consecutive outreaches
        self.service.user_states[user_id] = {'consecutive_outreaches': 5}
        self.assertTrue(self.service.should_switch_to_long_term_mode(user_id))
        
        # Test with more than max consecutive outreaches
        self.service.user_states[user_id] = {'consecutive_outreaches': 10}
        self.assertTrue(self.service.should_switch_to_long_term_mode(user_id))
        
        # Test with user not in states
        self.assertFalse(self.service.should_switch_to_long_term_mode(99999))
    
    def test_reset_cadence(self):
        """Test resetting cadence to shortest interval."""
        user_id = 12345
        
        # Set initial state
        self.service.user_states[user_id] = {
            'cadence': '1w',
            'consecutive_outreaches': 3,
            'last_proactive_message': datetime.now(),
            'user_replied': False
        }
        
        # Reset cadence
        self.service.reset_cadence(user_id)
        
        # Check that cadence was reset
        self.assertEqual(self.service.user_states[user_id]['cadence'], '1h')
        self.assertEqual(self.service.user_states[user_id]['consecutive_outreaches'], 0)
        self.assertIsNone(self.service.user_states[user_id]['last_proactive_message'])
        self.assertFalse(self.service.user_states[user_id]['user_replied'])
    
    def test_update_user_reply_status_replied(self):
        """Test updating user reply status when user replied."""
        user_id = 12345
        
        # Set initial state
        self.service.user_states[user_id] = {
            'cadence': '1w',
            'consecutive_outreaches': 3,
            'user_replied': False
        }
        
        # Update user reply status
        self.service.update_user_reply_status(user_id, replied=True)
        
        # Check that user replied status was updated and cadence was reset
        self.assertTrue(self.service.user_states[user_id]['user_replied'])
        self.assertEqual(self.service.user_states[user_id]['cadence'], '1h')
        self.assertEqual(self.service.user_states[user_id]['consecutive_outreaches'], 0)
    
    def test_update_user_reply_status_not_replied(self):
        """Test updating user reply status when user did not reply."""
        user_id = 12345
        
        # Set initial state
        self.service.user_states[user_id] = {
            'cadence': '1w',
            'consecutive_outreaches': 3,
            'user_replied': True
        }
        
        # Update user reply status
        self.service.update_user_reply_status(user_id, replied=False)
        
        # Check that user replied status was updated but cadence was not reset
        self.assertFalse(self.service.user_states[user_id]['user_replied'])
        self.assertEqual(self.service.user_states[user_id]['cadence'], '1w')
    
    @patch('proactive_messaging.send_proactive_message')
    def test_schedule_proactive_message(self, mock_send_task):
        """Test scheduling a proactive message."""
        user_id = 12345
        
        # Enable proactive messaging
        self.service.enabled = True
        
        # Schedule proactive message
        self.service.schedule_proactive_message(user_id)
        
        # Check that user state was initialized
        self.assertIn(user_id, self.service.user_states)
        self.assertEqual(self.service.user_states[user_id]['cadence'], '1h')
        
        # Check that Celery task was scheduled
        mock_send_task.apply_async.assert_called_once()
    
    @patch('proactive_messaging.send_proactive_message')
    def test_schedule_proactive_message_disabled(self, mock_send_task):
        """Test scheduling a proactive message when disabled."""
        user_id = 12345
        
        # Disable proactive messaging
        self.service.enabled = False
        
        # Schedule proactive message
        self.service.schedule_proactive_message(user_id)
        
        # Check that Celery task was not scheduled
        mock_send_task.apply_async.assert_not_called()
    
    def test_handle_user_message(self):
        """Test handling incoming user message."""
        user_id = 12345
        
        # Set initial state with scheduled message
        self.service.user_states[user_id] = {
            'scheduled_time': datetime.now() + timedelta(hours=1),
            'cadence': '1w',
            'user_replied': False
        }
        
        # Handle user message
        with patch('proactive_messaging.send_proactive_message') as mock_send_task:
            self.service.handle_user_message(user_id)
        
        # Check that scheduled time was cleared and user replied status was updated
        self.assertIsNone(self.service.user_states[user_id]['scheduled_time'])
        self.assertTrue(self.service.user_states[user_id]['user_replied'])
        
        # Check that cadence was reset
        self.assertEqual(self.service.user_states[user_id]['cadence'], '1h')

if __name__ == '__main__':
    unittest.main()