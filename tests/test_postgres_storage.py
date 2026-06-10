#!/usr/bin/env python3
"""
Test script for PostgreSQL storage functionality.
This script verifies that the database connection and storage operations work correctly.
"""

import asyncio
import logging
import os
import sys
from typing import Optional
# Add the project root to Python path
sys.path.insert(0, '.')

from storage import create_storage, Storage
from storage.interfaces import Message, Conversation, User, Persona
from storage_conversation_manager import PostgresConversationManager

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def _test_storage_connection(db_url: str) -> bool:
    """Test basic storage connection and operations."""
    try:
        logger.info("Testing storage connection...")
        storage = await create_storage(db_url, use_pgvector=True)
        
        # Test health check
        health = await storage.health_check()
        if not health:
            logger.error("Storage health check failed")
            return False
        logger.info("✓ Storage health check passed")
        
        # Test user creation
        logger.info("Testing user operations...")
        user = await storage.users.create_user(
            username="test_user_123",
            extra_data={"test": True, "telegram_id": 123456}
        )
        logger.info("✓ User created: %s", user.id)
        
        # Test persona creation
        logger.info("Testing persona operations...")
        persona = await storage.personas.create_persona(
            user_id=str(user.id),
            name="Test Assistant",
            config={"personality": "friendly test assistant"}
        )
        logger.info("✓ Persona created: %s", persona.id)
        
        # Test conversation creation
        logger.info("Testing conversation operations...")
        conversation = await storage.conversations.create_conversation(
            user_id=str(user.id),
            persona_id=str(persona.id),
            title="Test Chat",
            extra_data={"test_session": True}
        )
        logger.info("✓ Conversation created: %s", conversation.id)
        
        # Test message operations
        logger.info("Testing message operations...")
        message1 = await storage.messages.append_message(
            conversation_id=str(conversation.id),
            role="user",
            content="Hello, this is a test message!",
            extra_data={"test": True}
        )
        logger.info("✓ User message created: %s", message1.id)
        
        message2 = await storage.messages.append_message(
            conversation_id=str(conversation.id),
            role="assistant",
            content="Hello! I'm responding to your test message.",
            extra_data={"test": True}
        )
        logger.info("✓ Assistant message created: %s", message2.id)
        
        # Test message retrieval
        logger.info("Testing message retrieval...")
        messages = await storage.messages.list_messages(str(conversation.id))
        logger.info("✓ Retrieved %d messages", len(messages))
        
        # Test recent messages with token budget
        recent_messages = await storage.messages.fetch_recent_messages(
            str(conversation.id), token_budget=1000
        )
        logger.info("✓ Retrieved %d recent messages within token budget", len(recent_messages))
        
        # Clean up
        await storage.close()
        logger.info("✓ Storage connection closed successfully")
        
        return True
        
    except Exception as e:
        logger.error("Storage test failed: %s", e)
        import traceback
        traceback.print_exc()
        return False


async def _test_conversation_manager(db_url: str) -> bool:
    """Test the PostgresConversationManager."""
    try:
        logger.info("Testing PostgresConversationManager...")
        
        manager = PostgresConversationManager(db_url, use_pgvector=True)
        await manager.initialize()
        logger.info("✓ Conversation manager initialized")
        
        # Test user operations
        test_user_id = 789012
        
        # Add messages
        await manager.add_message_async(test_user_id, "user", "Hello from conversation manager!")
        
        await manager.add_message_async(test_user_id, "assistant", "Hello! Nice to meet you through the conversation manager.")
        
        # Get conversation
        conversation = await manager.get_conversation_async(test_user_id)
        logger.info("✓ Retrieved conversation with %d messages", len(conversation))
        
        # Get formatted conversation
        formatted = await manager.get_formatted_conversation_async(test_user_id)
        logger.info("✓ Retrieved formatted conversation with %d messages", len(formatted))
        
        # Get user stats
        stats = await manager.get_user_stats_async(test_user_id)
        logger.info("✓ Retrieved user stats: %d total messages", stats['total_messages'])
        
        # Clean up
        await manager.close()
        logger.info("✓ Conversation manager closed successfully")
        
        return True
        
    except Exception as e:
        logger.error("Conversation manager test failed: %s", e)
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Main test function."""
    # Get database URL from environment or use default
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        db_url = "postgresql+asyncpg://ai_bot:ai_bot_pass@localhost:5432/ai_bot"
        logger.info("Using default database URL (set DATABASE_URL environment variable to override)")
    
    logger.info("Starting PostgreSQL storage tests...")
    logger.info("Database URL: %s", db_url.replace(db_url.split('@')[0].split(':')[-1], '***'))
    
    success = True
    
    # Test basic storage operations
    logger.info("\n" + "="*50)
    logger.info("TEST 1: Basic Storage Operations")
    logger.info("="*50)
    if not await _test_storage_connection(db_url):
        success = False
    
    # Test conversation manager
    logger.info("\n" + "="*50)
    logger.info("TEST 2: Conversation Manager")
    logger.info("="*50)
    if not await _test_conversation_manager(db_url):
        success = False
    
    # Final result
    logger.info("\n" + "="*50)
    logger.info("TEST RESULTS")
    logger.info("="*50)
    if success:
        logger.info("✅ ALL TESTS PASSED! PostgreSQL storage is working correctly.")
    else:
        logger.error("❌ SOME TESTS FAILED! Please check the error messages above.")
    
    return success


if __name__ == "__main__":
    result = asyncio.run(main())
    sys.exit(0 if result else 1)
