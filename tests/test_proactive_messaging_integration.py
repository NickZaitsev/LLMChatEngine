"""
Integration tests for the proactive messaging system with the main bot.
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import sys
import os

# Add the parent directory to the path to import bot and proactive_messaging
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from bot import AIGirlfriendBot
from proactive_messaging import ProactiveMessagingService


@pytest.fixture
def bot_instance():
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
            # Mock the async method properly
            mock_cm_instance._ensure_user_and_conversation = AsyncMock()
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
                    bot = AIGirlfriendBot()
                    
                    # Set up mock objects
                    bot.conversation_manager = mock_cm_instance
                    bot.ai_handler = mock_ai_instance
                    bot.typing_manager = mock_tm_instance
                    
                    yield bot


def test_proactive_messaging_service_initialization(bot_instance):
    """Test that proactive messaging service is initialized in the bot."""
    # Check that proactive messaging service is available
    assert bot_instance.proactive_messaging_service is not None
    assert isinstance(bot_instance.proactive_messaging_service, ProactiveMessagingService)


@pytest.mark.asyncio
async def test_handle_message_triggers_proactive_messaging(bot_instance):
    """Test that handling a message triggers proactive messaging service."""
    # Set up mocks
    with patch('bot.send_ai_response') as mock_send, \
         patch('bot.clean_ai_response') as mock_clean:
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
        bot_instance.conversation_manager.add_message_async = AsyncMock()
        bot_instance.conversation_manager.get_formatted_conversation_async = AsyncMock(return_value=[])
        
        # Mock AI handler method
        bot_instance.ai_handler.generate_response = AsyncMock(return_value="Test response")
        
        # Mock proactive messaging service
        if bot_instance.proactive_messaging_service:
            bot_instance.proactive_messaging_service.handle_user_message = MagicMock()
        
        # Mock buffer manager dispatch method to simulate immediate dispatch
        original_dispatch = bot_instance.buffer_manager.dispatch_buffer
        bot_instance.buffer_manager.dispatch_buffer = AsyncMock(return_value="Hello bot!")
        
        # Call handle_message
        await bot_instance.handle_message(mock_update, mock_context)
        
        # Check that proactive messaging service was called
        if bot_instance.proactive_messaging_service:
            bot_instance.proactive_messaging_service.handle_user_message.assert_called_once_with(
                12345
            )
        
        # Restore original dispatch method
        bot_instance.buffer_manager.dispatch_buffer = original_dispatch


@pytest.mark.asyncio
async def test_handle_message_proactive_messaging_failure(bot_instance):
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
    bot_instance.conversation_manager.add_message_async = AsyncMock()
    bot_instance.conversation_manager.get_formatted_conversation_async = AsyncMock(return_value=[])
    
    # Mock AI handler method
    bot_instance.ai_handler.generate_response = AsyncMock(return_value="Test response")
    
    # Mock send_ai_response and clean_ai_response
    with patch('bot.send_ai_response') as mock_send, \
         patch('bot.clean_ai_response') as mock_clean:
        mock_clean.return_value = "Test response"
        mock_send.return_value = None
        
        # Make proactive messaging service raise an exception
        if bot_instance.proactive_messaging_service:
            bot_instance.proactive_messaging_service.handle_user_message = MagicMock(
                side_effect=Exception("Proactive messaging error")
            )
        
        # Mock buffer manager dispatch method to simulate immediate dispatch
        original_dispatch = bot_instance.buffer_manager.dispatch_buffer
        bot_instance.buffer_manager.dispatch_buffer = AsyncMock(return_value="Hello bot!")
        
        # Call handle_message - should not raise an exception
        try:
            await bot_instance.handle_message(mock_update, mock_context)
            success = True
        except Exception:
            success = False
        finally:
            # Restore original dispatch method
            bot_instance.buffer_manager.dispatch_buffer = original_dispatch
        
        assert success  # Should not raise an exception


def test_bot_initialization_with_proactive_messaging(bot_instance):
    """Test that bot initializes correctly with proactive messaging."""
    # Check that the bot has the proactive messaging service
    assert hasattr(bot_instance, 'proactive_messaging_service')
    
    # Check that it's the correct type
    if bot_instance.proactive_messaging_service is not None:
        assert isinstance(bot_instance.proactive_messaging_service, ProactiveMessagingService)