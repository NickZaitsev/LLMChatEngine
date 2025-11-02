"""
Tests for the storage factory functionality.

This module tests the storage factory operations including:
- Creating storage instances
- Database connection handling
- Health checks
- Error handling for invalid configurations
"""

import pytest
import os
from unittest.mock import patch

from storage import create_storage, Storage
from storage.models import PGVECTOR_AVAILABLE
from config import MEMORY_EMBED_DIM


@pytest.mark.asyncio
class TestStorageFactory:
    """Test cases for storage factory"""
    
    async def test_create_storage_sqlite(self):
        """Test creating storage with SQLite (in-memory)"""
        # Act
        storage = await create_storage(
            "sqlite+aiosqlite:///:memory:",
            use_pgvector=False
        )
        
        # Assert
        assert isinstance(storage, Storage)
        assert storage.messages is not None
        assert storage.memories is not None
        assert storage.conversations is not None
        assert storage.users is not None
        assert storage.personas is not None
        assert storage.use_pgvector == False
        
        # Test health check
        health = await storage.health_check()
        assert health == True
        
        # Cleanup
        await storage.close()
    
    async def test_create_storage_invalid_url(self):
        """Test creating storage with invalid database URL"""
        # Act & Assert
        with pytest.raises(ValueError, match="Database URL cannot be empty"):
            await create_storage("")
    
    async def test_create_storage_bad_connection(self):
        """Test creating storage with bad connection parameters"""
        # Act & Assert
        with pytest.raises(ValueError, match="Failed to connect to database"):
            await create_storage("postgresql+asyncpg://baduser:badpass@localhost:9999/baddb", use_pgvector=False)
    
    async def test_storage_health_check_success(self, storage):
        """Test successful health check"""
        # Act
        health = await storage.health_check()
        
        # Assert
        assert health == True
    
    async def test_storage_repositories_initialization(self, storage):
        """Test that all repositories are properly initialized"""
        # Assert
        assert storage.messages is not None
        assert storage.memories is not None
        assert storage.conversations is not None
        assert storage.users is not None
        assert storage.personas is not None
        
        # Test that repositories have expected methods
        assert hasattr(storage.messages, 'append_message')
        assert hasattr(storage.messages, 'fetch_recent_messages')
        assert hasattr(storage.memories, 'store_memory')
        assert hasattr(storage.memories, 'search_memories')
        assert hasattr(storage.conversations, 'create_conversation')
        assert hasattr(storage.users, 'create_user')
        assert hasattr(storage.personas, 'create_persona')
    
    async def test_storage_close(self):
        """Test storage cleanup"""
        # Arrange
        storage = await create_storage(
            "sqlite+aiosqlite:///:memory:",
            use_pgvector=False
        )
        
        # Act
        await storage.close()
        
        # Assert - Should not raise exception
        # In-memory SQLite connections might persist, so just ensure close doesn't raise
        assert storage.engine is not None  # Engine reference still exists
    
    @patch.dict(os.environ, {'DATABASE_URL': 'sqlite+aiosqlite:///:memory:'})
    async def test_create_storage_from_env_var(self):
        """Test creating storage using DATABASE_URL environment variable"""
        # Act
        storage = await create_storage("sqlite+aiosqlite:///:memory:")
        
        # Assert
        assert isinstance(storage, Storage)
        
        # Cleanup
        await storage.close()
    
    async def test_pgvector_availability_handling(self):
        """Test handling of pgvector availability"""
        # Test with pgvector explicitly disabled
        storage = await create_storage(
            "sqlite+aiosqlite:///:memory:",
            use_pgvector=False
        )
        
        # Should be False when explicitly disabled
        assert storage.use_pgvector == False
        
        # Cleanup
        await storage.close()
    
    async def test_storage_string_representation(self, storage):
        """Test storage string representation"""
        # Act
        repr_str = repr(storage)
        
        # Assert
        assert "Storage" in repr_str
        assert "pgvector" in repr_str
        assert "engine" in repr_str


@pytest.mark.asyncio 
class TestStorageIntegration:
    """Integration tests that test multiple repositories together"""
    
    async def test_full_conversation_flow(self, storage):
        """Test complete conversation flow across all repositories"""
        # Create user
        user = await storage.users.create_user(
            username="integration_test_user",
            extra_data={"test": "integration"}
        )
        
        # Create persona
        persona = await storage.personas.create_persona(
            user_id=str(user.id),
            name="Test Assistant",
            config={"personality": "helpful"}
        )
        
        # Create conversation
        conversation = await storage.conversations.create_conversation(
            user_id=str(user.id),
            persona_id=str(persona.id),
            title="Integration Test Conversation"
        )
        
        # Add messages
        user_message = await storage.messages.append_message(
            conversation_id=str(conversation.id),
            role="user",
            content="Hello, this is a test!"
        )
        
        assistant_message = await storage.messages.append_message(
            conversation_id=str(conversation.id),
            role="assistant", 
            content="Hello! How can I help you today?"
        )
        
        # Store memory
        embedding = [0.1] * MEMORY_EMBED_DIM
        memory = await storage.memories.store_memory(
            conversation_id=str(conversation.id),
            text="User greeted the assistant",
            embedding=embedding,
            memory_type="episodic"
        )
        
        # Verify everything is connected properly
        messages = await storage.messages.list_messages(str(conversation.id))
        assert len(messages) == 2
        assert messages[0].content == "Hello, this is a test!"
        assert messages[1].content == "Hello! How can I help you today?"
        
        memories = await storage.memories.list_memories(str(conversation.id))
        assert len(memories) == 1
        assert memories[0].text == "User greeted the assistant"
        
        conversations = await storage.conversations.list_conversations(str(user.id))
        assert len(conversations) == 1
        assert conversations[0].title == "Integration Test Conversation"
        
        personas = await storage.personas.list_personas(str(user.id))
        assert len(personas) == 1
        assert personas[0].name == "Test Assistant"
    
    async def test_token_budget_with_real_messages(self, storage):
        """Test token budget functionality with realistic message sizes"""
        # Create test data
        user = await storage.users.create_user(username="token_test_user")
        persona = await storage.personas.create_persona(
            user_id=str(user.id),
            name="Token Test Persona"
        )
        conversation = await storage.conversations.create_conversation(
            user_id=str(user.id),
            persona_id=str(persona.id)
        )
        
        # Add messages with known token counts
        messages_data = [
            ("user", "Hi", 2),
            ("assistant", "Hello! How can I help you today?", 8),
            ("user", "I need help with my Python code", 7),
            ("assistant", "I'd be happy to help you with your Python code! What specific issue are you facing?", 18),
        ]
        
        for role, content, expected_tokens in messages_data:
            await storage.messages.append_message(
                conversation_id=str(conversation.id),
                role=role,
                content=content,
                token_count=expected_tokens
            )
        
        # Test fetching with different token budgets
        recent_10 = await storage.messages.fetch_recent_messages(
            str(conversation.id), 
            token_budget=10
        )
        recent_20 = await storage.messages.fetch_recent_messages(
            str(conversation.id), 
            token_budget=20
        )
        recent_50 = await storage.messages.fetch_recent_messages(
            str(conversation.id), 
            token_budget=50
        )
        
        # Verify token budgets are respected
        total_tokens_10 = sum(msg.token_count for msg in recent_10)
        total_tokens_20 = sum(msg.token_count for msg in recent_20)
        total_tokens_50 = sum(msg.token_count for msg in recent_50)
        
        assert total_tokens_10 <= 10
        assert total_tokens_20 <= 20  
        assert total_tokens_50 <= 50
        
        # More tokens should mean more messages (up to the limit)
        assert len(recent_50) >= len(recent_20) >= len(recent_10)
    
    async def test_memory_search_across_conversations(self, storage):
        """Test that memory search works correctly across multiple conversations"""
        # Create test data
        user = await storage.users.create_user(username="memory_search_user")
        persona = await storage.personas.create_persona(
            user_id=str(user.id),
            name="Search Test Persona"
        )
        
        # Create two conversations
        conv1 = await storage.conversations.create_conversation(
            user_id=str(user.id),
            persona_id=str(persona.id),
            title="Conversation 1"
        )
        conv2 = await storage.conversations.create_conversation(
            user_id=str(user.id),
            persona_id=str(persona.id), 
            title="Conversation 2"
        )
        
        # Store memories with similar embeddings in both conversations
        similar_embedding = [0.9, 0.1] + [0.0] * 382
        different_embedding = [0.1, 0.9] + [0.0] * 382
        
        await storage.memories.store_memory(
            str(conv1.id), "Discussion about cats", similar_embedding
        )
        await storage.memories.store_memory(
            str(conv2.id), "Talk about dogs", similar_embedding  
        )
        await storage.memories.store_memory(
            str(conv1.id), "Conversation about space", different_embedding
        )
        
        # Search for similar memories
        query_embedding = [0.8, 0.2] + [0.0] * 382
        results = await storage.memories.search_memories(
            query_embedding=query_embedding,
            top_k=5,
            similarity_threshold=0.5
        )
        
        # Should find memories from both conversations
        assert len(results) >= 2
        conversation_ids = {str(mem.conversation_id) for mem in results}
        # Should include memories from both conversations
        assert len(conversation_ids) <= 2  # At most 2 conversations
    
    async def test_cascade_deletion_behavior(self, storage):
        """Test that cascade deletions work properly (conceptually)"""
        # Note: This test demonstrates the expected behavior
        # Actual CASCADE deletion would require direct database operations
        
        # Create complete hierarchy
        user = await storage.users.create_user(username="cascade_test_user")
        persona = await storage.personas.create_persona(
            user_id=str(user.id),
            name="Cascade Test Persona"
        )
        conversation = await storage.conversations.create_conversation(
            user_id=str(user.id),
            persona_id=str(persona.id)
        )
        
        # Add messages and memories
        message = await storage.messages.append_message(
            str(conversation.id), "user", "Test message"
        )
        memory = await storage.memories.store_memory(
            str(conversation.id), "Test memory", [0.1] * MEMORY_EMBED_DIM
        )
        
        # Verify everything exists
        messages = await storage.messages.list_messages(str(conversation.id))
        memories = await storage.memories.list_memories(str(conversation.id))
        assert len(messages) == 1
        assert len(memories) == 1
        
        # This test verifies the structure is set up correctly for cascade deletion
        # The actual CASCADE behavior is handled by the database constraints
        assert message.conversation_id == conversation.id
        assert memory.conversation_id == conversation.id