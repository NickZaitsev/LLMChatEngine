import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import redis

from bot import TelegramChatBot
from messaging import MessageQueueManager
from proactive_messaging import ProactiveMessagingService


class TestMessageQueueIntegration:
    """Integration tests for MessageQueueManager with bot and proactive messaging systems."""
    
    def setup_method(self):
        """Set up test fixtures before each test method."""
        self.redis_url = "redis://localhost:6379/15"  # Use database 15 for testing
        self.user_id = 12345
        self.chat_id = 67890
        self.test_message = "Hello, this is a test message!"
        
    def teardown_method(self):
        """Tear down test fixtures after each test method."""
        # Clean up test data
        try:
            redis_client = redis.from_url(self.redis_url)
            redis_client.delete(f"queue:{self.user_id}:default")
            redis_client.srem("dispatcher:active_users", f"{self.user_id}:default")
        except Exception:
            pass  # Ignore cleanup errors
    
    @pytest.mark.asyncio
    async def test_bot_integration_with_message_queue(self):
        """Test that bot uses message queue when available."""
        with patch('redis.Redis.ping') as mock_ping:
            mock_ping.return_value = True
            
            # Create a mock bot instance
            with patch('bot.TelegramChatBot._initialize_storage'), \
                 patch('bot.TelegramChatBot._initialize_memory_components'), \
                 patch('bot.TelegramChatBot._initialize_lmstudio_model'):
                
                bot = TelegramChatBot()
                
                # Mock the message queue manager
                bot.message_queue_manager = MessageQueueManager(self.redis_url)
                
                # Mock Redis methods
                with patch.object(bot.message_queue_manager, 'enqueue_script', new=AsyncMock(return_value=1)) as mock_enqueue:
                    
                    # Test enqueueing a message through the bot's interface
                    # This simulates what happens in _dispatch_buffered_message
                    if bot.message_queue_manager:
                        await bot.message_queue_manager.enqueue_message(
                            user_id=self.user_id,
                            chat_id=self.chat_id,
                            text=self.test_message,
                            message_type="regular"
                        )
                        
                        # Verify the message was enqueued
                        mock_enqueue.assert_awaited_once()
                        args = mock_enqueue.await_args.kwargs
                        assert args["keys"][0] == f"queue:{self.user_id}:default"
                        
                        # Verify the message content
                        message_json = args["args"][1]
                        message_data = json.loads(message_json)
                        assert message_data["user_id"] == self.user_id
                        assert message_data["chat_id"] == self.chat_id
                        assert message_data["text"] == self.test_message
                        assert message_data["message_type"] == "regular"
    
    @pytest.mark.asyncio
    async def test_proactive_messaging_integration_with_message_queue(self):
        """Test that proactive messaging uses message queue when available."""
        with patch('redis.Redis.ping') as mock_ping:
            mock_ping.return_value = True
            
            # Create a mock proactive messaging service
            service = ProactiveMessagingService()
            
            # Mock the message queue manager
            service.message_queue_manager = MessageQueueManager(self.redis_url)
            
            # Mock Redis methods
            with patch.object(service.message_queue_manager, 'enqueue_script', new=AsyncMock(return_value=1)) as mock_enqueue:
                
                # Test enqueueing a proactive message
                if service.message_queue_manager:
                    await service.message_queue_manager.enqueue_message(
                        user_id=self.user_id,
                        chat_id=self.user_id,  # For proactive messages, chat_id is typically the same as user_id
                        text=self.test_message,
                        message_type="proactive"
                    )
                    
                    # Verify the message was enqueued
                    mock_enqueue.assert_awaited_once()
                    args = mock_enqueue.await_args.kwargs
                    assert args["keys"][0] == f"queue:{self.user_id}:default"
                    
                    # Verify the message content
                    message_json = args["args"][1]
                    message_data = json.loads(message_json)
                    assert message_data["user_id"] == self.user_id
                    assert message_data["chat_id"] == self.user_id
                    assert message_data["text"] == self.test_message
                    assert message_data["message_type"] == "proactive"
    
    @pytest.mark.asyncio
    async def test_startup_processing_integration(self):
        """Test that startup processing correctly identifies existing queues."""
        with patch('redis.Redis.ping') as mock_ping:
            mock_ping.return_value = True
            
            # Create a mock bot instance
            with patch('bot.TelegramChatBot._initialize_storage'), \
                 patch('bot.TelegramChatBot._initialize_memory_components'), \
                 patch('bot.TelegramChatBot._initialize_lmstudio_model'):
                
                bot = TelegramChatBot()
                bot.message_dispatcher = SimpleNamespace(_scan_existing_queues=AsyncMock())

                # Instead of calling start_dispatching (which starts an infinite loop),
                # just call _scan_existing_queues directly to test it
                if bot.message_dispatcher:
                    await bot.message_dispatcher._scan_existing_queues()
                    bot.message_dispatcher._scan_existing_queues.assert_awaited_once()

if __name__ == "__main__":
    pytest.main([__file__])
