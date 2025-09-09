import pytest
import asyncio
import json
from unittest.mock import Mock, patch
import redis

from message_manager import MessageQueueManager

class TestMessageQueueManager:
    """Test cases for MessageQueueManager class."""
    
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
            redis_client.srem("dispatcher:active_users", self.user_id)
        except Exception:
            pass  # Ignore cleanup errors
    
    def test_init_success(self):
        """Test successful initialization of MessageQueueManager."""
        with patch('redis.Redis.ping') as mock_ping:
            mock_ping.return_value = True
            manager = MessageQueueManager(self.redis_url)
            assert manager.redis_client is not None
    
    def test_init_failure(self):
        """Test failed initialization of MessageQueueManager."""
        with patch('redis.from_url') as mock_from_url:
            mock_from_url.side_effect = Exception("Connection failed")
            with pytest.raises(Exception):
                MessageQueueManager(self.redis_url)
    
    @pytest.mark.asyncio
    async def test_enqueue_message_success(self):
        """Test successful message enqueueing."""
        with patch('redis.Redis.ping') as mock_ping:
            mock_ping.return_value = True
            manager = MessageQueueManager(self.redis_url)
            
            # Mock Redis methods
            with patch.object(manager.redis_client, 'rpush') as mock_rpush, \
                 patch.object(manager.redis_client, 'sadd') as mock_sadd:
                
                mock_rpush.return_value = 1
                mock_sadd.return_value = 1
                
                await manager.enqueue_message(
                    user_id=self.user_id,
                    chat_id=self.chat_id,
                    text=self.test_message,
                    message_type="regular"
                )
                
                # Verify rpush was called with correct arguments
                mock_rpush.assert_called_once()
                args = mock_rpush.call_args[0]
                assert args[0] == f"queue:{self.user_id}"
                
                # Verify the message content
                message_json = args[1]
                message_data = json.loads(message_json)
                assert message_data["user_id"] == self.user_id
                assert message_data["chat_id"] == self.chat_id
                assert message_data["text"] == self.test_message
                assert message_data["message_type"] == "regular"
                assert "timestamp" in message_data
                assert message_data["retry_count"] == 0
                
                # Verify sadd was called to add user to active users set
                mock_sadd.assert_called_once_with("dispatcher:active_users", self.user_id)
    
    @pytest.mark.asyncio
    async def test_enqueue_message_validation_errors(self):
        """Test validation errors in message enqueueing."""
        with patch('redis.Redis.ping') as mock_ping:
            mock_ping.return_value = True
            manager = MessageQueueManager(self.redis_url)
            
            # Test invalid user_id
            with pytest.raises(ValueError):
                await manager.enqueue_message(
                    user_id=-1,  # Invalid user_id
                    chat_id=self.chat_id,
                    text=self.test_message
                )
            
            # Test invalid chat_id
            with pytest.raises(ValueError):
                await manager.enqueue_message(
                    user_id=self.user_id,
                    chat_id=-1,  # Invalid chat_id
                    text=self.test_message
                )
            
            # Test invalid text
            with pytest.raises(ValueError):
                await manager.enqueue_message(
                    user_id=self.user_id,
                    chat_id=self.chat_id,
                    text=""  # Empty text
                )
            
            # Test invalid message_type
            with pytest.raises(ValueError):
                await manager.enqueue_message(
                    user_id=self.user_id,
                    chat_id=self.chat_id,
                    text=self.test_message,
                    message_type="invalid_type"  # Invalid message_type
                )
    
    @pytest.mark.asyncio
    async def test_get_queue_size_success(self):
        """Test successful queue size retrieval."""
        with patch('redis.Redis.ping') as mock_ping:
            mock_ping.return_value = True
            manager = MessageQueueManager(self.redis_url)
            
            # Mock llen method
            with patch.object(manager.redis_client, 'llen') as mock_llen:
                mock_llen.return_value = 5
                
                size = await manager.get_queue_size(self.user_id)
                assert size == 5
                mock_llen.assert_called_once_with(f"queue:{self.user_id}")
    
    @pytest.mark.asyncio
    async def test_get_queue_size_validation_error(self):
        """Test validation error in queue size retrieval."""
        with patch('redis.Redis.ping') as mock_ping:
            mock_ping.return_value = True
            manager = MessageQueueManager(self.redis_url)
            
            # Test invalid user_id
            with pytest.raises(ValueError):
                await manager.get_queue_size(-1)  # Invalid user_id
    
    @pytest.mark.asyncio
    async def test_is_queue_empty_true(self):
        """Test checking if queue is empty when it is empty."""
        with patch('redis.Redis.ping') as mock_ping:
            mock_ping.return_value = True
            manager = MessageQueueManager(self.redis_url)
            
            # Mock get_queue_size to return 0
            with patch.object(manager, 'get_queue_size') as mock_get_queue_size:
                mock_get_queue_size.return_value = 0
                
                is_empty = await manager.is_queue_empty(self.user_id)
                assert is_empty is True
                mock_get_queue_size.assert_called_once_with(self.user_id)
    
    @pytest.mark.asyncio
    async def test_is_queue_empty_false(self):
        """Test checking if queue is empty when it is not empty."""
        with patch('redis.Redis.ping') as mock_ping:
            mock_ping.return_value = True
            manager = MessageQueueManager(self.redis_url)
            
            # Mock get_queue_size to return 3
            with patch.object(manager, 'get_queue_size') as mock_get_queue_size:
                mock_get_queue_size.return_value = 3
                
                is_empty = await manager.is_queue_empty(self.user_id)
                assert is_empty is False
                mock_get_queue_size.assert_called_once_with(self.user_id)

if __name__ == "__main__":
    pytest.main([__file__])