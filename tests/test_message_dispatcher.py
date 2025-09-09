import pytest
import asyncio
import json
from unittest.mock import Mock, patch, AsyncMock
import redis

from message_manager import MessageDispatcher

class TestMessageDispatcher:
    """Test cases for MessageDispatcher class."""
    
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
            redis_client.delete(f"queue:{self.user_id}")
            redis_client.delete(f"dispatcher:processing:{self.user_id}")
            redis_client.srem("dispatcher:active_users", self.user_id)
        except Exception:
            pass  # Ignore cleanup errors
    
    def test_init_success(self):
        """Test successful initialization of MessageDispatcher."""
        with patch('redis.Redis.ping') as mock_ping, \
             patch('telegram.Bot') as mock_bot, \
             patch('message_manager.TypingIndicatorManager') as mock_typing_manager:
            
            mock_ping.return_value = True
            mock_bot.return_value = Mock()
            mock_typing_manager.return_value = Mock()
            
            dispatcher = MessageDispatcher(self.redis_url)
            assert dispatcher.redis_client is not None
            assert dispatcher.max_retries == 3
            assert dispatcher.lock_timeout == 30
            assert dispatcher.running is False
    
    def test_init_failure(self):
        """Test failed initialization of MessageDispatcher."""
        with patch('redis.from_url') as mock_from_url:
            mock_from_url.side_effect = Exception("Connection failed")
            with pytest.raises(Exception):
                MessageDispatcher(self.redis_url)
    
    @pytest.mark.asyncio
    async def test_process_message_success(self):
        """Test successful message processing."""
        # Mock send_ai_response as an async function that returns None
        mock_send_ai_response = AsyncMock()
        
        # Mock Bot and TypingIndicatorManager classes in the message_dispatcher module
        mock_bot_class = Mock()
        mock_bot_instance = Mock()
        # Mock the async methods of the bot
        mock_bot_instance.send_chat_action = AsyncMock()
        mock_bot_instance.send_message = AsyncMock()
        mock_bot_class.return_value = mock_bot_instance
        
        mock_typing_manager_class = Mock()
        mock_typing_manager_instance = Mock()
        # Mock the async methods of the TypingIndicatorManager
        mock_typing_manager_instance.start_typing = AsyncMock()
        mock_typing_manager_instance.stop_typing = AsyncMock()
        mock_typing_manager_class.return_value = mock_typing_manager_instance
        
        with patch('redis.Redis.ping') as mock_ping, \
             patch('message_manager.Bot', new=mock_bot_class), \
             patch('message_manager.TypingIndicatorManager', new=mock_typing_manager_class), \
             patch('message_manager.send_ai_response', new=mock_send_ai_response):
            
            mock_ping.return_value = True
            
            dispatcher = MessageDispatcher(self.redis_url)
            
            message_data = {
                "user_id": self.user_id,
                "chat_id": self.chat_id,
                "text": self.test_message,
                "message_type": "regular",
                "retry_count": 0
            }
            
            success = await dispatcher.process_message(message_data)
            
            assert success is True
            mock_send_ai_response.assert_called_once_with(
                chat_id=self.chat_id,
                text=self.test_message,
                bot=mock_bot_instance,
                typing_manager=mock_typing_manager_instance
            )
    
    @pytest.mark.asyncio
    async def test_process_message_failure(self):
        """Test failed message processing."""
        # Mock send_ai_response as an async function that raises an exception
        mock_send_ai_response = AsyncMock()
        mock_send_ai_response.side_effect = Exception("Failed to send message")
        
        # Mock Bot and TypingIndicatorManager classes in the message_dispatcher module
        mock_bot_class = Mock()
        mock_bot_instance = Mock()
        # Mock the async methods of the bot
        mock_bot_instance.send_chat_action = AsyncMock()
        mock_bot_instance.send_message = AsyncMock()
        mock_bot_class.return_value = mock_bot_instance
        
        mock_typing_manager_class = Mock()
        mock_typing_manager_instance = Mock()
        mock_typing_manager_class.return_value = mock_typing_manager_instance
        
        with patch('redis.Redis.ping') as mock_ping, \
             patch('message_manager.Bot', new=mock_bot_class), \
             patch('message_manager.TypingIndicatorManager', new=mock_typing_manager_class), \
             patch('message_manager.send_ai_response', new=mock_send_ai_response):
            
            mock_ping.return_value = True
            
            dispatcher = MessageDispatcher(self.redis_url)
            
            message_data = {
                "user_id": self.user_id,
                "chat_id": self.chat_id,
                "text": self.test_message,
                "message_type": "regular",
                "retry_count": 0
            }
            
            success = await dispatcher.process_message(message_data)
            
            assert success is False
    
    @pytest.mark.asyncio
    async def test_handle_failed_message_retry(self):
        """Test handling of failed message with retry."""
        # Mock Bot and TypingIndicatorManager classes in the message_dispatcher module
        mock_bot_class = Mock()
        mock_bot_instance = Mock()
        # Mock the async methods of the bot
        mock_bot_instance.send_chat_action = AsyncMock()
        mock_bot_instance.send_message = AsyncMock()
        mock_bot_class.return_value = mock_bot_instance
        
        mock_typing_manager_class = Mock()
        mock_typing_manager_instance = Mock()
        mock_typing_manager_class.return_value = mock_typing_manager_instance
        
        with patch('redis.Redis.ping') as mock_ping, \
             patch('message_manager.Bot', new=mock_bot_class), \
             patch('message_manager.TypingIndicatorManager', new=mock_typing_manager_class):
            
            mock_ping.return_value = True
            
            dispatcher = MessageDispatcher(self.redis_url, max_retries=3)
            
            # Mock Redis methods
            with patch.object(dispatcher.redis_client, 'rpush') as mock_rpush:
                mock_rpush.return_value = 1
                
                message_data = {
                    "user_id": self.user_id,
                    "chat_id": self.chat_id,
                    "text": self.test_message,
                    "message_type": "regular",
                    "retry_count": 1  # Less than max_retries
                }
                
                await dispatcher.handle_failed_message(message_data)
                
                # Verify the message was requeued
                mock_rpush.assert_called_once()
                args = mock_rpush.call_args[0]
                assert args[0] == f"queue:{self.user_id}"
                
                # Verify the retry count was incremented
                message_json = args[1]
                updated_message_data = json.loads(message_json)
                assert updated_message_data["retry_count"] == 2
    
    @pytest.mark.asyncio
    async def test_handle_failed_message_dead_letter_queue(self):
        """Test handling of failed message moved to dead letter queue."""
        # Mock Bot and TypingIndicatorManager classes in the message_dispatcher module
        mock_bot_class = Mock()
        mock_bot_instance = Mock()
        # Mock the async methods of the bot
        mock_bot_instance.send_chat_action = AsyncMock()
        mock_bot_instance.send_message = AsyncMock()
        mock_bot_class.return_value = mock_bot_instance
        
        mock_typing_manager_class = Mock()
        mock_typing_manager_instance = Mock()
        mock_typing_manager_class.return_value = mock_typing_manager_instance
        
        with patch('redis.Redis.ping') as mock_ping, \
             patch('message_manager.Bot', new=mock_bot_class), \
             patch('message_manager.TypingIndicatorManager', new=mock_typing_manager_class):
            
            mock_ping.return_value = True
            
            dispatcher = MessageDispatcher(self.redis_url, max_retries=3)
            
            # Mock Redis methods
            with patch.object(dispatcher.redis_client, 'rpush') as mock_rpush:
                mock_rpush.return_value = 1
                
                message_data = {
                    "user_id": self.user_id,
                    "chat_id": self.chat_id,
                    "text": self.test_message,
                    "message_type": "regular",
                    "retry_count": 3  # Equal to max_retries
                }
                
                await dispatcher.handle_failed_message(message_data)
                
                # Verify the message was moved to dead letter queue
                mock_rpush.assert_called_once()
                args = mock_rpush.call_args[0]
                assert args[0] == f"dlq:{self.user_id}"

    @pytest.mark.asyncio
    async def test_scan_existing_queues(self):
        """Test scanning for existing queues at startup."""
        # Mock Bot and TypingIndicatorManager classes in the message_dispatcher module
        mock_bot_class = Mock()
        mock_bot_instance = Mock()
        mock_bot_class.return_value = mock_bot_instance
        
        mock_typing_manager_class = Mock()
        mock_typing_manager_instance = Mock()
        mock_typing_manager_class.return_value = mock_typing_manager_instance
        
        with patch('redis.Redis.ping') as mock_ping, \
             patch('message_manager.Bot', new=mock_bot_class), \
             patch('message_manager.TypingIndicatorManager', new=mock_typing_manager_class):
            
            mock_ping.return_value = True
            dispatcher = MessageDispatcher(self.redis_url)
            
            # Mock Redis scan method to return some test keys
            test_keys = [b'queue:12345', b'queue:67890', b'queue:1111']
            with patch.object(dispatcher.redis_client, 'scan') as mock_scan, \
                 patch.object(dispatcher.redis_client, 'llen') as mock_llen, \
                 patch.object(dispatcher.redis_client, 'sadd') as mock_sadd:
                
                # Mock scan to return test keys and then exit
                mock_scan.side_effect = [(1, []), (0, test_keys)]
                
                # Mock llen to return non-zero values (non-empty queues)
                mock_llen.return_value = 5
                
                await dispatcher._scan_existing_queues()
                
                # Verify scan was called
                assert mock_scan.call_count == 2
                
                # Verify llen was called for each key
                assert mock_llen.call_count == 3
                
                # Verify sadd was called to add users to active set
                assert mock_sadd.call_count == 3

if __name__ == "__main__":
    pytest.main([__file__])