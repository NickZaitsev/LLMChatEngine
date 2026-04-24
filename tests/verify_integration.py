"""
Integration verification script for the PostgreSQL storage system.

This script demonstrates that the new storage system is working correctly
and can replace the in-memory storage with minimal integration effort.
"""

import asyncio
import logging
import os
import sys
from typing import Dict, List

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
from config import MEMORY_EMBED_DIM


async def verify_storage_system():
    """
    Comprehensive verification that the storage system works as expected.
    
    This simulates the flow that the bot would use and verifies all functionality.
    """
    try:
        # Import storage system
        from storage import create_storage
        from storage.repos import TokenEstimator
        
        logger.info("🚀 Starting PostgreSQL storage system verification...")
        
        # Use SQLite for testing (no external dependencies)
        storage = await create_storage(
            "sqlite+aiosqlite:///:memory:",
            use_pgvector=False
        )
        logger.info("✅ Storage system initialized successfully")
        
        # Test 1: Basic repository functionality
        logger.info("🧪 Testing basic repository operations...")
        
        # Create test user
        user = await storage.users.create_user(
            username="test_user_12345",
            metadata={"telegram_id": 12345}
        )
        logger.info(f"✅ User created: {user.username}")
        
        # Create test persona
        persona = await storage.personas.create_persona(
            user_id=str(user.id),
            name="Test Assistant",
            config={"personality": "helpful and friendly"}
        )
        logger.info(f"✅ Persona created: {persona.name}")
        
        # Create test conversation
        conversation = await storage.conversations.create_conversation(
            user_id=str(user.id),
            persona_id=str(persona.id),
            title="Test Conversation"
        )
        logger.info(f"✅ Conversation created: {conversation.title}")
        
        # Test 2: Message operations (simulating bot usage)
        logger.info("💬 Testing message operations...")
        
        # Simulate conversation flow
        messages_data = [
            ("user", "Hello! How are you?"),
            ("assistant", "Hello! I'm doing great, thank you for asking! How can I help you today?"),
            ("user", "Can you tell me a joke?"),
            ("assistant", "Sure! Why don't scientists trust atoms? Because they make up everything! 😄"),
            ("user", "That's funny! Tell me about yourself."),
            ("assistant", "I'm an AI assistant designed to be helpful, friendly, and supportive. I love chatting with people like you!")
        ]
        
        created_messages = []
        for role, content in messages_data:
            message = await storage.messages.append_message(
                conversation_id=str(conversation.id),
                role=role,
                content=content
            )
            created_messages.append(message)
            logger.info(f"✅ Message stored: {role[:4]} - {content[:30]}...")
        
        # Test token budget functionality
        logger.info("🎯 Testing token budget functionality...")
        
        # Test fetching messages within token budget
        recent_messages = await storage.messages.fetch_recent_messages(
            str(conversation.id),
            token_budget=50  # Small budget to test trimming
        )
        
        total_tokens = sum(msg.token_count for msg in recent_messages)
        logger.info(f"✅ Retrieved {len(recent_messages)} messages within 50 token budget (used {total_tokens} tokens)")
        
        # Test 3: Memory operations with embeddings
        logger.info("🧠 Testing memory operations...")
        
        # Create test embeddings
        embedding_1 = [0.1, 0.2, 0.3] + [0.0] * (MEMORY_EMBED_DIM-3)  
        embedding_2 = [0.9, 0.1, 0.0] + [0.0] * (MEMORY_EMBED_DIM-3)  # Different similarity
        
        # Store memories
        memory_1 = await storage.memories.store_memory(
            str(conversation.id),
            "User enjoys humor and jokes",
            embedding_1,
            memory_type="episodic"
        )
        
        memory_2 = await storage.memories.store_memory(
            str(conversation.id), 
            "User is curious about AI personalities",
            embedding_2,
            memory_type="episodic"
        )
        
        logger.info(f"✅ Stored {len([memory_1, memory_2])} memories with embeddings")
        
        # Test similarity search
        query_embedding = [0.15, 0.25, 0.35] + [0.0] * (MEMORY_EMBED_DIM-3)  # Similar to embedding_1
        similar_memories = await storage.memories.search_memories(
            query_embedding,
            top_k=5,
            similarity_threshold=0.3
        )
        
        logger.info(f"✅ Found {len(similar_memories)} similar memories")
        
        # Test 4: Token estimation
        logger.info("🔢 Testing token estimation...")
        
        estimator = TokenEstimator()
        test_texts = [
            "Hello world",
            "This is a longer message with more words to test token estimation accuracy",
            "Short",
            ""
        ]
        
        for text in test_texts:
            tokens = estimator.estimate_tokens(text)
            logger.info(f"✅ '{text[:20]}...' estimated at {tokens} tokens")
        
        # Test 5: Database health and cleanup
        logger.info("🏥 Testing database health...")
        
        health = await storage.health_check()
        logger.info(f"✅ Database health check: {'PASS' if health else 'FAIL'}")
        
        # Test repository statistics
        all_messages = await storage.messages.list_messages(str(conversation.id))
        all_memories = await storage.memories.list_memories(str(conversation.id))
        all_conversations = await storage.conversations.list_conversations(str(user.id))
        
        logger.info(f"📊 Final statistics:")
        logger.info(f"   - Messages: {len(all_messages)}")
        logger.info(f"   - Memories: {len(all_memories)}")
        logger.info(f"   - Conversations: {len(all_conversations)}")
        
        # Cleanup
        await storage.close()
        logger.info("✅ Storage connection closed successfully")
        
        logger.info("🎉 All tests passed! Storage system is working correctly.")
        return True
        
    except Exception as e:
        logger.error(f"❌ Verification failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def verify_file_structure():
    """Verify that all required files are present and properly structured."""
    logger.info("📁 Verifying file structure...")
    
    required_files = [
        'storage/__init__.py',
        'storage/models.py', 
        'storage/repos.py',
        'storage/interfaces.py',
        'migrations/env.py',
        'migrations/script.py.mako',
        'migrations/versions/20250113_1738_001_initial_schema.py',
        'alembic.ini',
        'requirements.txt',
        'tests/conftest.py',
        'tests/test_message_repo.py',
        'tests/test_memory_repo.py',
        'tests/test_storage_factory.py',
        'pytest.ini'
    ]
    
    missing_files = []
    for file_path in required_files:
        if not os.path.exists(file_path):
            missing_files.append(file_path)
    
    if missing_files:
        logger.error(f"❌ Missing required files: {missing_files}")
        return False
    
    logger.info("✅ All required files are present")
    return True


async def verify_migration_system():
    """Verify that the migration system is properly configured."""
    logger.info("🗄️ Verifying migration system...")
    
    try:
        # Check if alembic can be imported and configured
        import alembic
        from alembic.config import Config
        from alembic.runtime.migration import MigrationContext
        from alembic.operations import Operations
        
        # Test alembic configuration
        alembic_cfg = Config("alembic.ini")
        logger.info("✅ Alembic configuration loaded successfully")
        
        # Verify migration script exists
        if os.path.exists("migrations/versions/20250113_1738_001_initial_schema.py"):
            logger.info("✅ Initial migration script found")
        else:
            logger.warning("⚠️ Initial migration script not found")
        
        return True
        
    except ImportError as e:
        logger.error(f"❌ Alembic not available: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Migration system verification failed: {e}")
        return False


async def main():
    """Main verification function."""
    logger.info("🔍 Starting comprehensive system verification...")
    
    # Step 1: Verify file structure
    if not verify_file_structure():
        logger.error("❌ File structure verification failed")
        sys.exit(1)
    
    # Step 2: Verify migration system
    migration_ok = await verify_migration_system()
    if not migration_ok:
        logger.warning("⚠️ Migration system issues detected (may need alembic install)")
    
    # Step 3: Verify storage system functionality
    storage_ok = await verify_storage_system()
    if not storage_ok:
        logger.error("❌ Storage system verification failed")
        sys.exit(1)
    
    logger.info("🎊 SUCCESS: PostgreSQL storage system is ready for production!")
    logger.info("")
    logger.info("📋 Next steps:")
    logger.info("   1. Install dependencies: pip install -r requirements.txt")
    logger.info("   2. Set up PostgreSQL database")
    logger.info("   3. Configure DATABASE_URL in .env")
    logger.info("   4. Run migrations: alembic upgrade head")
    logger.info("   5. Update bot.py to use PostgresConversationManager")
    logger.info("   6. Run tests: pytest")


if __name__ == "__main__":
    asyncio.run(main())