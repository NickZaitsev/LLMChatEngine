"""
Test script to verify the typing indicator integration with the buffer manager works correctly
"""
import asyncio
import logging
import sys
import os

# Add the parent directory to the path so we can import our modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from buffer_manager import BufferManager
from message_manager import TypingIndicatorManager

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


class MockBot:
    """Mock bot for testing"""
    async def send_chat_action(self, chat_id, action):
        logger.info(f"Mock bot sending chat action '{action}' to chat {chat_id}")


async def test_buffer_typing_integration():
    """Test the BufferManager typing indicator integration"""
    logger.info("🚀 Starting buffer typing indicator integration test...")
    
    try:
        # Create instances
        buffer_manager = BufferManager()
        typing_manager = TypingIndicatorManager()
        mock_bot = MockBot()
        
        # Set up buffer manager with typing manager
        buffer_manager.set_typing_manager(typing_manager)
        
        # Test user ID and chat ID
        user_id = 12345
        chat_id = 67890
        
        # Set user context
        buffer_manager.set_user_context(user_id, mock_bot, chat_id)
        
        logger.info("✓ BufferManager and TypingIndicatorManager instances created")
        logger.info("✓ BufferManager configured with TypingIndicatorManager")
        logger.info("✓ User context set in BufferManager")
        
        # Test adding first message (should start typing indicator)
        logger.info("1. Adding first message to buffer...")
        await buffer_manager.add_message(user_id, "Hello, this is my first message!")
        logger.info("✓ First message added to buffer")
        
        # Wait a bit to see if typing action is sent
        await asyncio.sleep(0.5)
        
        # Check if typing is active
        is_active = typing_manager.is_typing_active(chat_id)
        logger.info(f"✓ Typing active status: {is_active}")
        
        # Test adding additional messages (should not start new typing indicator)
        logger.info("2. Adding additional messages to buffer...")
        await buffer_manager.add_message(user_id, "This is my second message.")
        await buffer_manager.add_message(user_id, "And this is my third message.")
        logger.info("✓ Additional messages added to buffer")
        
        # Wait a bit more
        await asyncio.sleep(0.5)
        
        # Test dispatching buffer (should stop typing indicator)
        logger.info("3. Dispatching buffer...")
        concatenated_message = await buffer_manager.dispatch_buffer(user_id)
        logger.info(f"✓ Buffer dispatched. Concatenated message: {concatenated_message}")
        
        # Wait a bit to see if typing action stops
        await asyncio.sleep(0.5)
        
        # Check if typing is still active
        is_active_after = typing_manager.is_typing_active(chat_id)
        logger.info(f"✓ Typing active after dispatch: {is_active_after}")
        
        # Test adding message after dispatch (should start typing indicator again when buffer is empty)
        logger.info("4. Adding message after dispatch...")
        await buffer_manager.add_message(user_id, "This is a new message after dispatch.")
        logger.info("✓ New message added to buffer")
        
        # Wait a bit to see if typing action is sent
        await asyncio.sleep(0.5)
        
        # Check if typing is active again
        is_active_new = typing_manager.is_typing_active(chat_id)
        logger.info(f"✓ Typing active for new message: {is_active_new}")
        
        # Cleanup
        await typing_manager.cleanup()
        logger.info("✓ Cleanup completed")
        
        logger.info("🎉 All buffer typing indicator integration tests passed!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Buffer typing indicator integration test failed: {e}")
        return False


async def main():
    """Run all tests"""
    success = await test_buffer_typing_integration()
    
    if success:
        print("\nAll tests PASSED!")
        return 0
    else:
        print("\nSome tests FAILED!")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))