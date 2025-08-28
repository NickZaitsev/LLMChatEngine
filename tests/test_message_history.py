"""
Test file for message history functionality.
"""

import asyncio
import logging
import os
import sys
from datetime import datetime

# Add the project root to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from storage import create_storage
from config import DATABASE_URL

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_message_history():
    """Test the message history functionality."""
    logger.info("Starting message history test")
    
    # Create storage instance with file-based SQLite for testing
    storage = await create_storage("sqlite+aiosqlite:///test_message_history.db", use_pgvector=False)
    logger.info("Storage created successfully")
    
    # Test user ID - convert integer to UUID for database
    import uuid
    telegram_user_id = 123456789
    user_id = uuid.uuid5(uuid.NAMESPACE_OID, f"telegram_user_{telegram_user_id}")
    role = "user"
    content = "Hello, this is a test message!"
    
    try:
        # Test save_message function
        logger.info("Testing save_message function")
        message_log, message_user = await storage.message_history.save_message(user_id, role, content)
        logger.info("Message saved successfully")
        logger.info(f"MessageLog ID: {message_log.id}")
        logger.info(f"MessageUser ID: {message_user.id}")
        
        # Test get_user_history function
        logger.info("Testing get_user_history function")
        history = await storage.message_history.get_user_history(user_id, limit=10)
        logger.info(f"Retrieved {len(history)} messages from history")
        
        if history:
            logger.info(f"First message: {history[0].content}")
        
        # Test clear_user_history function
        logger.info("Testing clear_user_history function")
        deleted_count = await storage.message_history.clear_user_history(user_id)
        logger.info(f"Cleared {deleted_count} messages from user history")
        
        # Verify messages are cleared
        logger.info("Verifying messages are cleared")
        history_after_clear = await storage.message_history.get_user_history(user_id, limit=10)
        logger.info(f"Messages after clear: {len(history_after_clear)}")
        
        # Test that messages_log still has the message
        # This would require a direct query to the messages_log table
        logger.info("Test completed successfully")
        
    except Exception as e:
        logger.error(f"Test failed with error: {e}")
        raise
    finally:
        # Clean up
        await storage.close()
        logger.info("Storage closed")


if __name__ == "__main__":
    asyncio.run(test_message_history())