import asyncio
import logging
import sys
import os

# Add the parent directory to the path so we can import our modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from storage_conversation_manager import PostgresConversationManager
from config import DATABASE_URL, USE_PGVECTOR

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def test_message_timing():
    """Test that messages are immediately available in conversation history after being added"""
    # Initialize the conversation manager with file-based SQLite for testing
    conversation_manager = PostgresConversationManager("sqlite+aiosqlite:///tests/test_message_timing.db", False)
    await conversation_manager.initialize()
    
    # Test user ID - use the same Telegram user ID as other tests
    telegram_user_id = 123456789
    user_id = telegram_user_id
    
    # Clear any existing conversation for this test user
    await conversation_manager.clear_conversation_async(user_id)
    
    # Add a test message
    test_message = "Hello, this is a test message!"
    logger.info("Adding test message: %s", test_message)
    
    # Use the new async method to add the message
    await conversation_manager.add_message_async(user_id, "user", test_message)
    
    # Immediately retrieve the formatted conversation
    conversation_history = await conversation_manager.get_formatted_conversation_async(user_id)
    
    # Check if our message is in the conversation history
    message_found = False
    for msg in conversation_history:
        if msg["role"] == "user" and msg["content"] == test_message:
            message_found = True
            break
    
    if message_found:
        logger.info("✅ SUCCESS: Message is immediately available in conversation history")
        print("✅ Test PASSED: Message is immediately available in conversation history")
    else:
        logger.error("❌ FAILURE: Message is NOT available in conversation history")
        print("❌ Test FAILED: Message is NOT available in conversation history")
    
    # Clean up - clear the test conversation
    await conversation_manager.clear_conversation_async(user_id)
    logger.info("Cleaned up test conversation")
    
    # Close the storage connection
    await conversation_manager.close()
    
    # Remove the test database file
    try:
        if os.path.exists("tests/test_message_timing.db"):
            os.remove("tests/test_message_timing.db")
            logger.info("Test database file removed")
    except Exception as e:
        logger.warning(f"Failed to remove test database file: {e}")

if __name__ == "__main__":
    asyncio.run(test_message_timing())