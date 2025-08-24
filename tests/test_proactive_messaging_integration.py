"""
Integration tests for the proactive messaging system with the main bot.
"""

import unittest
from unittest.mock import patch, MagicMock, AsyncMock
import sys
import os

# Add the parent directory to the path to import bot and proactive_messaging
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from bot import AIGirlfriendBot
from proactive_messaging import ProactiveMessagingService

class TestProactiveMessagingIntegration(unittest.TestCase):
    """Test cases for proactive messaging integration with the main bot."""
    
    def setUp(self):
        """Set up test fixtures before each test method."""
        # Mock environment variables to prevent actual initialization
        with patch.dict(os.environ, {
            'TELEGRAM_TOKEN': 'test_token',
            'DATABASE_URL': 'postgresql://test:test@test:5432/test',
            'PROACTIVE_MESSAGING_ENABLED': 'true'
        }):
            # Mock the conversation manager to prevent database connections
            with patch('bot.PostgresConversationManager') as mock_cm:
                mock_cm_instance = MagicMock()
                mock_cm_instance.initialize = AsyncMock()
                mock_cm.return_value = mock_cm_instance
                
                # Mock the AI handler
                with patch('bot.AIHandler') as mock_ai:
                    mock_ai_instance = MagicMock()
                    mock_ai.return_value = mock_ai_instance
                    
                    # Mock the typing manager
                    with patch('bot.TypingIndicatorManager') as mock_tm:
                        mock_tm_instance = MagicMock()
                        mock_tm_instance.start_typing = AsyncMock()
                        mock_tm_instance.stop_typing = AsyncMock()
                        mock_tm.return_value = mock_tm_instance
                        
                        # Create the bot instance
                        self.bot = AIGirlfriendBot()
                        
                        # Set up mock objects
                        self.bot.conversation_manager = mock_cm_instance
                        self.bot.ai_handler = mock_ai_instance
                        self.bot.typing_manager = mock_tm_instance
    
    def test_proactive_messaging_service_initialization(self):
        """Test that proactive messaging service is initialized in the bot."""
        # Check that proactive messaging service is available
        self.assertIsNotNone(self.bot.proactive_messaging_service)
        self.assertIsInstance(self.bot.proactive_messaging_service, ProactiveMessagingService)
    
    @patch('bot.send_ai_response')
    @patch('bot.clean_ai_response')
    async def test_handle_message_triggers_proactive_messaging(self, mock_clean, mock_send):
        """Test that handling a message triggers proactive messaging service."""
        # Set up mocks
        mock_clean.return_value = "Test response"
        mock_send.return_value = None
        
        # Create mock update and context
        mock_update = MagicMock()
        mock_update.effective_user.id = 12345
        mock_update.effective_user.first_name = "Test"
        mock_update.effective_chat.id = 67890
        mock_update.message.text = "Hello bot!"
        
        mock_context = MagicMock()
        mock_context.bot = MagicMock()
        
        # Mock conversation manager methods
        self.bot.conversation_manager.add_message_async = AsyncMock()
        self.bot.conversation_manager.get_formatted_conversation_async = AsyncMock(return_value=[])
        
        # Mock AI handler method
        self.bot.ai_handler.generate_response = AsyncMock(return_value="Test response")
        
        # Mock proactive messaging service
        if self.bot.proactive_messaging_service:
            self.bot.proactive_messaging_service.handle_user_message = MagicMock()
        
        # Call handle_message
        await self.bot.handle_message(mock_update, mock_context)
        
        # Check that proactive messaging service was called
        if self.bot.proactive_messaging_service:
            self.bot.proactive_messaging_service.handle_user_message.assert_called_once_with(
                12345, self.bot
            )
    
    async def test_handle_message_proactive_messaging_failure(self):
        """Test that handle_message continues even if proactive messaging fails."""
        # Create mock update and context
        mock_update = MagicMock()
        mock_update.effective_user.id = 12345
        mock_update.effective_user.first_name = "Test"
        mock_update.effective_chat.id = 67890
        mock_update.message.text = "Hello bot!"
        
        mock_context = MagicMock()
        mock_context.bot = MagicMock()
        
        # Mock conversation manager methods
        self.bot.conversation_manager.add_message_async = AsyncMock()
        self.bot.conversation_manager.get_formatted_conversation_async = AsyncMock(return_value=[])
        
        # Mock AI handler method
        self.bot.ai_handler.generate_response = AsyncMock(return_value="Test response")
        
        # Mock send_ai_response and clean_ai_response
        with patch('bot.send_ai_response') as mock_send, \
             patch('bot.clean_ai_response') as mock_clean:
            mock_clean.return_value = "Test response"
            mock_send.return_value = None
            
            # Make proactive messaging service raise an exception
            if self.bot.proactive_messaging_service:
                self.bot.proactive_messaging_service.handle_user_message = MagicMock(
                    side_effect=Exception("Proactive messaging error")
                )
            
            # Call handle_message - should not raise an exception
            try:
                await self.bot.handle_message(mock_update, mock_context)
                success = True
            except Exception:
                success = False
            
            self.assertTrue(success)  # Should not raise an exception
    
    def test_bot_initialization_with_proactive_messaging(self):
        """Test that bot initializes correctly with proactive messaging."""
        # Check that the bot has the proactive messaging service
        self.assertTrue(hasattr(self.bot, 'proactive_messaging_service'))
        
        # Check that it's the correct type
        if self.bot.proactive_messaging_service is not None:
            self.assertIsInstance(self.bot.proactive_messaging_service, ProactiveMessagingService)

if __name__ == '__main__':
    unittest.main()