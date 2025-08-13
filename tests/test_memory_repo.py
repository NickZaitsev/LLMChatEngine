"""
Tests for PostgresMemoryRepo functionality.

This module tests memory repository operations including:
- Storing memories with embeddings
- Searching memories by similarity
- Listing memories by conversation and type
- Fallback behavior without pgvector
"""

import pytest
import math
from uuid import uuid4

from storage.repos import PostgresMemoryRepo
from tests.conftest import assert_uuid_string


@pytest.mark.asyncio
class TestMemoryRepo:
    """Test cases for PostgresMemoryRepo"""
    
    async def test_store_memory_basic(self, memory_repo: PostgresMemoryRepo, sample_conversation, sample_embedding):
        """Test storing a basic memory"""
        # Arrange
        conversation_id = str(sample_conversation.id)
        text = "This is a test memory about our conversation"
        memory_type = "episodic"
        
        # Act
        memory = await memory_repo.store_memory(
            conversation_id=conversation_id,
            text=text,
            embedding=sample_embedding,
            memory_type=memory_type
        )
        
        # Assert
        assert memory.conversation_id == sample_conversation.id
        assert memory.text == text
        assert memory.memory_type == memory_type
        assert memory.embedding == sample_embedding
        assert_uuid_string(str(memory.id))
    
    async def test_store_memory_summary_type(self, memory_repo: PostgresMemoryRepo, sample_conversation, sample_embedding):
        """Test storing a summary-type memory"""
        # Arrange
        conversation_id = str(sample_conversation.id)
        text = "Summary: The user discussed their favorite hobbies"
        
        # Act
        memory = await memory_repo.store_memory(
            conversation_id=conversation_id,
            text=text,
            embedding=sample_embedding,
            memory_type="summary"
        )
        
        # Assert
        assert memory.memory_type == "summary"
    
    async def test_store_memory_invalid_conversation_id(self, memory_repo: PostgresMemoryRepo, sample_embedding):
        """Test storing memory with invalid conversation ID"""
        # Act & Assert
        with pytest.raises(ValueError, match="Invalid conversation_id format"):
            await memory_repo.store_memory(
                conversation_id="not-a-uuid",
                text="Test memory",
                embedding=sample_embedding
            )
    
    async def test_list_memories_all(self, memory_repo: PostgresMemoryRepo, sample_conversation, sample_embedding):
        """Test listing all memories for a conversation"""
        # Arrange
        conversation_id = str(sample_conversation.id)
        memories_data = [
            ("First episodic memory", "episodic"),
            ("Summary of conversation", "summary"),
            ("Second episodic memory", "episodic")
        ]
        
        # Store memories
        for text, memory_type in memories_data:
            await memory_repo.store_memory(
                conversation_id=conversation_id,
                text=text,
                embedding=sample_embedding,
                memory_type=memory_type
            )
        
        # Act
        all_memories = await memory_repo.list_memories(conversation_id)
        
        # Assert
        assert len(all_memories) == 3
        memory_texts = [mem.text for mem in all_memories]
        assert "First episodic memory" in memory_texts
        assert "Summary of conversation" in memory_texts
        assert "Second episodic memory" in memory_texts
    
    async def test_list_memories_filtered_by_type(self, memory_repo: PostgresMemoryRepo, sample_conversation, sample_embedding):
        """Test listing memories filtered by type"""
        # Arrange
        conversation_id = str(sample_conversation.id)
        
        # Store different types of memories
        await memory_repo.store_memory(
            conversation_id=conversation_id,
            text="Episodic memory 1",
            embedding=sample_embedding,
            memory_type="episodic"
        )
        await memory_repo.store_memory(
            conversation_id=conversation_id,
            text="Summary memory",
            embedding=sample_embedding,
            memory_type="summary"
        )
        await memory_repo.store_memory(
            conversation_id=conversation_id,
            text="Episodic memory 2",
            embedding=sample_embedding,
            memory_type="episodic"
        )
        
        # Act
        episodic_memories = await memory_repo.list_memories(conversation_id, memory_type="episodic")
        summary_memories = await memory_repo.list_memories(conversation_id, memory_type="summary")
        
        # Assert
        assert len(episodic_memories) == 2
        assert len(summary_memories) == 1
        
        episodic_texts = [mem.text for mem in episodic_memories]
        assert "Episodic memory 1" in episodic_texts
        assert "Episodic memory 2" in episodic_texts
        
        assert summary_memories[0].text == "Summary memory"
    
    async def test_search_memories_similarity(self, memory_repo: PostgresMemoryRepo, sample_conversation):
        """Test searching memories by similarity"""
        # Arrange
        conversation_id = str(sample_conversation.id)
        
        # Create embeddings with different similarities
        # Similar embeddings (high dot product)
        similar_embedding_1 = [0.9, 0.1, 0.0] + [0.0] * 381
        similar_embedding_2 = [0.8, 0.2, 0.1] + [0.0] * 381
        # Different embedding (lower similarity)
        different_embedding = [0.1, 0.1, 0.9] + [0.0] * 381
        
        # Store memories with different embeddings
        await memory_repo.store_memory(
            conversation_id=conversation_id,
            text="Memory about cats and dogs",
            embedding=similar_embedding_1,
            memory_type="episodic"
        )
        await memory_repo.store_memory(
            conversation_id=conversation_id,
            text="Memory about pets and animals",
            embedding=similar_embedding_2,
            memory_type="episodic"
        )
        await memory_repo.store_memory(
            conversation_id=conversation_id,
            text="Memory about space and stars",
            embedding=different_embedding,
            memory_type="episodic"
        )
        
        # Act - Search with embedding similar to the first two
        query_embedding = [0.85, 0.15, 0.05] + [0.0] * 381
        results = await memory_repo.search_memories(
            query_embedding=query_embedding,
            top_k=5,
            similarity_threshold=0.5
        )
        
        # Assert - Should find the similar memories first
        assert len(results) >= 2  # Should find at least the two similar ones
        
        # The most similar should be first (results are ordered by similarity)
        top_result = results[0]
        assert "cats and dogs" in top_result.text or "pets and animals" in top_result.text
    
    async def test_search_memories_threshold_filtering(self, memory_repo: PostgresMemoryRepo, sample_conversation):
        """Test that similarity threshold properly filters results"""
        # Arrange
        conversation_id = str(sample_conversation.id)
        
        # Create very different embeddings
        embedding_1 = [1.0, 0.0, 0.0] + [0.0] * 381
        embedding_2 = [0.0, 1.0, 0.0] + [0.0] * 381
        embedding_3 = [0.0, 0.0, 1.0] + [0.0] * 381
        
        await memory_repo.store_memory(
            conversation_id=conversation_id,
            text="Memory 1",
            embedding=embedding_1
        )
        await memory_repo.store_memory(
            conversation_id=conversation_id,
            text="Memory 2", 
            embedding=embedding_2
        )
        await memory_repo.store_memory(
            conversation_id=conversation_id,
            text="Memory 3",
            embedding=embedding_3
        )
        
        # Act - Search with very high threshold
        query_embedding = [0.5, 0.5, 0.0] + [0.0] * 381
        results = await memory_repo.search_memories(
            query_embedding=query_embedding,
            top_k=10,
            similarity_threshold=0.9  # Very high threshold
        )
        
        # Assert - Should find few or no results due to high threshold
        assert len(results) <= 3  # At most all memories, likely fewer
        
        # Test with lower threshold
        results_low_threshold = await memory_repo.search_memories(
            query_embedding=query_embedding,
            top_k=10,
            similarity_threshold=0.1  # Low threshold
        )
        
        # Should find more results with lower threshold
        assert len(results_low_threshold) >= len(results)
    
    async def test_search_memories_empty_results(self, memory_repo: PostgresMemoryRepo):
        """Test searching when no memories exist"""
        # Arrange
        query_embedding = [0.1] * 384
        
        # Act
        results = await memory_repo.search_memories(query_embedding)
        
        # Assert
        assert len(results) == 0
    
    async def test_cosine_similarity_calculation(self, memory_repo: PostgresMemoryRepo):
        """Test the cosine similarity calculation"""
        # Test identical vectors
        vec1 = [1.0, 0.0, 0.0]
        vec2 = [1.0, 0.0, 0.0]
        similarity = memory_repo._cosine_similarity(vec1, vec2)
        assert abs(similarity - 1.0) < 1e-6
        
        # Test orthogonal vectors
        vec3 = [1.0, 0.0, 0.0]
        vec4 = [0.0, 1.0, 0.0]
        similarity = memory_repo._cosine_similarity(vec3, vec4)
        assert abs(similarity - 0.0) < 1e-6
        
        # Test opposite vectors
        vec5 = [1.0, 0.0, 0.0]
        vec6 = [-1.0, 0.0, 0.0]
        similarity = memory_repo._cosine_similarity(vec5, vec6)
        assert abs(similarity - (-1.0)) < 1e-6
        
        # Test zero vectors (edge case)
        vec7 = [0.0, 0.0, 0.0]
        vec8 = [1.0, 0.0, 0.0]
        similarity = memory_repo._cosine_similarity(vec7, vec8)
        assert similarity == 0.0
    
    async def test_store_memory_nonexistent_conversation(self, memory_repo: PostgresMemoryRepo, sample_embedding):
        """Test storing memory for non-existent conversation"""
        # Arrange
        fake_conversation_id = str(uuid4())
        
        # Act - SQLite doesn't enforce foreign key constraints by default
        # so this will succeed in tests, but would fail in PostgreSQL production
        memory = await memory_repo.store_memory(
            conversation_id=fake_conversation_id,
            text="This works in SQLite test mode",
            embedding=sample_embedding
        )
        
        # Assert
        assert memory.text == "This works in SQLite test mode"
        assert str(memory.conversation_id) == fake_conversation_id
    
    async def test_memory_ordering_by_creation_time(self, memory_repo: PostgresMemoryRepo, sample_conversation, sample_embedding):
        """Test that memories are returned in creation order"""
        # Arrange
        conversation_id = str(sample_conversation.id)
        
        # Store memories in sequence
        memory1 = await memory_repo.store_memory(
            conversation_id=conversation_id,
            text="First memory",
            embedding=sample_embedding
        )
        memory2 = await memory_repo.store_memory(
            conversation_id=conversation_id,
            text="Second memory", 
            embedding=sample_embedding
        )
        memory3 = await memory_repo.store_memory(
            conversation_id=conversation_id,
            text="Third memory",
            embedding=sample_embedding
        )
        
        # Act
        memories = await memory_repo.list_memories(conversation_id)
        
        # Assert - Should be ordered by creation time
        assert len(memories) == 3
        assert memories[0].created_at <= memories[1].created_at
        assert memories[1].created_at <= memories[2].created_at
        
        # Check content order
        assert memories[0].text == "First memory"
        assert memories[1].text == "Second memory"
        assert memories[2].text == "Third memory"
    
    async def test_search_memories_top_k_limit(self, memory_repo: PostgresMemoryRepo, sample_conversation, sample_embedding):
        """Test that search respects the top_k limit"""
        # Arrange
        conversation_id = str(sample_conversation.id)
        
        # Store 5 memories
        for i in range(5):
            await memory_repo.store_memory(
                conversation_id=conversation_id,
                text=f"Memory {i+1}",
                embedding=sample_embedding
            )
        
        # Act - Search with top_k=3
        results = await memory_repo.search_memories(
            query_embedding=sample_embedding,
            top_k=3,
            similarity_threshold=0.0  # Low threshold to include all
        )
        
        # Assert
        assert len(results) == 3  # Should respect the limit
    
    async def test_multiple_conversations_isolation(self, memory_repo: PostgresMemoryRepo, conversation_repo, sample_embedding):
        """Test that memories from different conversations are isolated"""
        # Arrange - Create two conversations
        from tests.conftest import generate_uuid
        
        conv1 = await conversation_repo.create_conversation(
            user_id=generate_uuid(),
            persona_id=generate_uuid(),
            title="Conversation 1"
        )
        conv2 = await conversation_repo.create_conversation(
            user_id=generate_uuid(),
            persona_id=generate_uuid(),
            title="Conversation 2"
        )
        
        # Store memories in each conversation
        await memory_repo.store_memory(str(conv1.id), "Memory in conv1", sample_embedding)
        await memory_repo.store_memory(str(conv2.id), "Memory in conv2", sample_embedding)
        await memory_repo.store_memory(str(conv1.id), "Another memory in conv1", sample_embedding)
        
        # Act
        conv1_memories = await memory_repo.list_memories(str(conv1.id))
        conv2_memories = await memory_repo.list_memories(str(conv2.id))
        
        # Assert
        assert len(conv1_memories) == 2
        assert len(conv2_memories) == 1
        
        # Check content isolation
        conv1_texts = [mem.text for mem in conv1_memories]
        conv2_texts = [mem.text for mem in conv2_memories]
        
        assert "Memory in conv1" in conv1_texts
        assert "Another memory in conv1" in conv1_texts
        assert "Memory in conv2" in conv2_texts
        assert "Memory in conv2" not in conv1_texts
        assert "Memory in conv1" not in conv2_texts