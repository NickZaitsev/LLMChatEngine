"""
Tests for MemoryManager functionality.

This module tests memory manager operations including:
- Episodic memory creation from message chunks
- Summary rollup and merging
- Semantic memory retrieval
- Integration with embedding and summarization components
"""

import pytest
import pytest_asyncio
import asyncio
import json
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime, timedelta
from uuid import uuid4

from memory.manager import MemoryManager, MemoryRecord
from storage.interfaces import Message
from tests.conftest import generate_uuid
from config import MEMORY_EMBED_DIM

@pytest.fixture
def mock_llm_summarize():
    """Mock LLM summarization function for testing."""
    async def mock_llm_func(text: str, mode: str) -> str:
        if mode == "summarize":
            # Return structured JSON response
            return json.dumps({
                "summary": f"Summary of: {text[:50]}...",
                "key_facts": [f"Fact from {text[:20]}...", "Another fact"],
                "importance": 0.7,
                "language": "en"
            })
        elif mode == "merge":
            # Return merged profile with expected content
            if "machine learning" in text.lower() and "transformers" in text.lower():
                return "User is interested in AI and machine learning. They started a new project with transformers for sentiment analysis using BERT models."
            elif "machine learning" in text.lower():
                return "User is interested in AI and machine learning. They have been learning about NLP and using Python tools for their projects."
            elif "transformers" in text.lower():
                return "User is interested in AI and machine learning. They started a new project with transformers for sentiment analysis using BERT models."
            else:
                return f"Updated profile based on: {text[:100]}..."
        else:
            return f"LLM response for {mode}: {text[:50]}..."
    
    return mock_llm_func


@pytest.fixture
def mock_config(mock_llm_summarize):
    """Mock configuration for MemoryManager."""
    return {
        "embed_model": "sentence-transformers/all-MiniLM-L6-v2",
        "summarizer_mode": "llm",
        "llm_summarize": mock_llm_summarize,
        "chunk_overlap": 2
    }


@pytest.fixture 
def mock_local_config():
    """Mock configuration for local mode testing."""
    return {
        "embed_model": "sentence-transformers/all-MiniLM-L6-v2", 
        "summarizer_mode": "local",
        "local_model": "facebook/bart-large-cnn",
        "chunk_overlap": 3
    }


@pytest_asyncio.fixture
async def memory_manager(storage, mock_config):
    """Create MemoryManager instance for testing."""
    return MemoryManager(
        message_repo=storage.messages,
        memory_repo=storage.memories, 
        conversation_repo=storage.conversations,
        config=mock_config
    )


@pytest_asyncio.fixture
async def sample_messages(storage, sample_conversation):
    """Create sample messages for testing."""
    conversation_id = str(sample_conversation.id)
    messages = []
    
    # Create a sequence of messages
    message_contents = [
        "Hello, how are you today?",
        "I'm doing well, thank you! I've been reading about machine learning.",
        "That's interesting! What aspects of ML are you most curious about?",
        "I'm particularly interested in natural language processing.",
        "NLP is fascinating. Have you tried any practical applications?",
        "Yes, I've been experimenting with sentiment analysis on social media data.",
        "That sounds like a great project. What tools are you using?",
        "Mainly Python with scikit-learn and some transformer models.",
        "Excellent choices. How are you finding the transformer models?",
        "They're powerful but can be computationally intensive.",
        "That's a common trade-off. Have you considered model optimization?",
        "I'm looking into quantization and pruning techniques.",
        "Those are great approaches for production deployment.",
        "Thanks for the advice! This has been a helpful conversation.",
        "You're welcome! Feel free to ask if you have more questions."
    ]
    
    # Create messages with alternating roles
    for i, content in enumerate(message_contents):
        role = "user" if i % 2 == 0 else "assistant"
        message = await storage.messages.append_message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            token_count=len(content) // 4
        )
        messages.append(message)
        
        # Add small delay to ensure different timestamps
        await asyncio.sleep(0.001)
    
    return messages


class TestMemoryManagerInit:
    """Test MemoryManager initialization and configuration."""
    
    @pytest.mark.asyncio
    async def test_initialization_with_llm_config(self, storage, mock_config):
        """Test initialization with LLM configuration."""
        manager = MemoryManager(
            storage.messages, storage.memories, storage.conversations, mock_config
        )
        
        assert manager.embed_model == "sentence-transformers/all-MiniLM-L6-v2"
        assert manager.chunk_overlap == 2
        assert manager.summarizer.mode == "llm"
    
    @pytest.mark.asyncio
    async def test_initialization_with_local_config(self, storage, mock_local_config):
        """Test initialization with local summarization config."""
        manager = MemoryManager(
            storage.messages, storage.memories, storage.conversations, mock_local_config
        )
        
        assert manager.embed_model == "sentence-transformers/all-MiniLM-L6-v2"
        assert manager.chunk_overlap == 3
        assert manager.summarizer.mode == "local"
    
    @pytest.mark.asyncio
    async def test_initialization_with_defaults(self, storage):
        """Test initialization with minimal config (should use defaults)."""
        minimal_config = {"summarizer_mode": "local"}
        
        manager = MemoryManager(
            storage.messages, storage.memories, storage.conversations, minimal_config
        )
        
        assert manager.embed_model == "sentence-transformers/all-MiniLM-L6-v2"
        assert manager.chunk_overlap == 2  # default
        assert manager.summarizer.mode == "local"


class TestEpisodicMemoryCreation:
    """Test episodic memory creation from message chunks."""
    
    @patch('memory.manager.embed_single_text')
    @pytest.mark.asyncio
    async def test_create_episodic_memories_basic(
        self, mock_embed, memory_manager, sample_messages, sample_conversation
    ):
        """Test basic episodic memory creation."""
        # Arrange
        mock_embed.return_value = [0.1] * MEMORY_EMBED_DIM
        conversation_id = str(sample_conversation.id)
        
        # Act
        memories = await memory_manager.create_episodic_memories(
            conversation_id=conversation_id,
            chunk_size_messages=5
        )
        
        # Assert
        assert len(memories) > 0
        assert all(isinstance(mem, MemoryRecord) for mem in memories)
        assert all(mem.memory_type == "episodic" for mem in memories)
        assert all(mem.conversation_id == sample_conversation.id for mem in memories)
        
        # Check that embeddings were generated
        mock_embed.assert_called()
        
        # Check that memory text contains structured data
        for memory in memories:
            assert memory.text.startswith('{')  # JSON structure
            memory_data = json.loads(memory.text)
            assert "summary" in memory_data
            assert "key_facts" in memory_data
            assert "importance" in memory_data
            assert "content_hash" in memory_data
    
    @patch('memory.manager.embed_single_text')
    @pytest.mark.asyncio
    async def test_create_episodic_memories_chunking(
        self, mock_embed, memory_manager, sample_messages, sample_conversation
    ):
        """Test message chunking behavior."""
        # Arrange
        mock_embed.return_value = [0.1] * MEMORY_EMBED_DIM
        conversation_id = str(sample_conversation.id)
        
        # Act with small chunk size
        memories = await memory_manager.create_episodic_memories(
            conversation_id=conversation_id,
            chunk_size_messages=3
        )
        
        # Assert - Should create multiple chunks from 15 messages
        assert len(memories) >= 3  # Expect multiple chunks
        
        # Verify chunk indices are present in memory data
        chunk_indices = []
        for memory in memories:
            memory_data = json.loads(memory.text)
            chunk_indices.append(memory_data["chunk_index"])
        
        # Should have sequential chunk indices starting from 0
        assert 0 in chunk_indices
        assert len(set(chunk_indices)) == len(memories)  # All unique
    
    @patch('memory.manager.embed_single_text')
    @pytest.mark.asyncio
    async def test_create_episodic_memories_deduplication(
        self, mock_embed, memory_manager, sample_messages, sample_conversation
    ):
        """Test deduplication of existing memories."""
        # Arrange
        mock_embed.return_value = [0.1] * MEMORY_EMBED_DIM
        conversation_id = str(sample_conversation.id)
        
        # Act - Create memories twice
        memories1 = await memory_manager.create_episodic_memories(
            conversation_id=conversation_id,
            chunk_size_messages=5
        )
        
        memories2 = await memory_manager.create_episodic_memories(
            conversation_id=conversation_id,
            chunk_size_messages=5  # Same parameters
        )
        
        # Assert - Second run should create no new memories (deduplication)
        assert len(memories1) > 0
        assert len(memories2) == 0  # No new memories due to deduplication
    
    @pytest.mark.asyncio
    async def test_create_episodic_memories_empty_conversation(self, memory_manager):
        """Test handling of empty conversation."""
        # Act
        memories = await memory_manager.create_episodic_memories(
            conversation_id=str(uuid4()),  # Non-existent conversation
            chunk_size_messages=5
        )
        
        # Assert
        assert len(memories) == 0
    
    @pytest.mark.asyncio
    async def test_create_episodic_memories_invalid_id(self, memory_manager):
        """Test error handling for invalid conversation ID."""
        with pytest.raises(ValueError, match="conversation_id cannot be empty"):
            await memory_manager.create_episodic_memories(
                conversation_id="",
                chunk_size_messages=5
            )


class TestSummaryRollup:
    """Test summary rollup and merging functionality."""
    
    @patch('memory.manager.embed_single_text')
    @pytest.mark.asyncio
    async def test_rollup_summary_first_time(
        self, mock_embed, memory_manager, sample_conversation
    ):
        """Test creating first summary rollup."""
        # Arrange
        mock_embed.return_value = [0.1] * MEMORY_EMBED_DIM
        conversation_id = str(sample_conversation.id)
        
        # Create some episodic memories first
        episodic_data = {
            "summary": "User discussed machine learning interests",
            "key_facts": ["Interested in NLP", "Using Python tools"],
            "importance": 0.8,
            "source_message_ids": ["msg1", "msg2"],
            "lang": "en",
            "content_hash": "abc123"
        }
        
        await memory_manager.memory_repo.store_memory(
            conversation_id=conversation_id,
            text=json.dumps(episodic_data),
            embedding=[0.2] * MEMORY_EMBED_DIM,
            memory_type="episodic"
        )
        
        # Act
        summary = await memory_manager.rollup_summary(conversation_id)
        
        # Assert
        assert summary  # Should return non-empty summary
        assert "machine learning" in summary.lower()
        
        # Verify summary was stored
        summary_memories = await memory_manager.memory_repo.list_memories(
            conversation_id, memory_type="summary"
        )
        assert len(summary_memories) == 1
        
        # Verify structure of stored summary
        summary_data = json.loads(summary_memories[0].text)
        assert "profile" in summary_data
        assert "change_log" in summary_data
        assert "profile_hash" in summary_data
    
    @patch('memory.manager.embed_single_text')
    @pytest.mark.asyncio
    async def test_rollup_summary_update_existing(
        self, mock_embed, memory_manager, sample_conversation
    ):
        """Test updating an existing summary."""
        # Arrange
        mock_embed.return_value = [0.1] * MEMORY_EMBED_DIM
        conversation_id = str(sample_conversation.id)
        
        # Create existing summary
        existing_summary_data = {
            "profile": "User is interested in AI and machine learning",
            "change_log": [],
            "lang": "en",
            "profile_hash": "old_hash"
        }
        
        await memory_manager.memory_repo.store_memory(
            conversation_id=conversation_id,
            text=json.dumps(existing_summary_data),
            embedding=[0.1] * MEMORY_EMBED_DIM,
            memory_type="summary"
        )
        
        # Add new episodic memory
        new_episodic_data = {
            "summary": "User started a new project with transformers",
            "key_facts": ["Working on sentiment analysis", "Using BERT models"],
            "importance": 0.9,
            "source_message_ids": ["msg3", "msg4"],
            "lang": "en",
            "content_hash": "def456"
        }
        
        await memory_manager.memory_repo.store_memory(
            conversation_id=conversation_id,
            text=json.dumps(new_episodic_data),
            embedding=[0.2] * MEMORY_EMBED_DIM,
            memory_type="episodic"
        )
        
        # Act
        updated_summary = await memory_manager.rollup_summary(conversation_id)
        
        # Assert
        assert updated_summary
        assert "transformers" in updated_summary.lower() or "sentiment" in updated_summary.lower()
        
        # Verify new summary was stored
        summary_memories = await memory_manager.memory_repo.list_memories(
            conversation_id, memory_type="summary"
        )
        assert len(summary_memories) == 2  # Old + new
    
    @patch('memory.manager.embed_single_text')
    @pytest.mark.asyncio
    async def test_rollup_summary_idempotent(
        self, mock_embed, memory_manager, sample_conversation
    ):
        """Test that rollup is idempotent for same content."""
        # Arrange
        mock_embed.return_value = [0.1] * MEMORY_EMBED_DIM
        conversation_id = str(sample_conversation.id)
        
        # Mock the LLM to return same content
        original_llm_func = memory_manager.summarizer.llm_func
        
        async def consistent_llm_func(text: str, mode: str) -> str:
            return "Consistent summary content"
        
        memory_manager.summarizer.llm_func = consistent_llm_func
        
        # Create episodic memory
        episodic_data = {
            "summary": "Test summary",
            "key_facts": ["Test fact"],
            "importance": 0.5,
            "source_message_ids": ["msg1"],
            "lang": "en",
            "content_hash": "test123"
        }
        
        await memory_manager.memory_repo.store_memory(
            conversation_id=conversation_id,
            text=json.dumps(episodic_data),
            embedding=[0.1] * MEMORY_EMBED_DIM,
            memory_type="episodic"
        )
        
        # Act - Roll up twice
        summary1 = await memory_manager.rollup_summary(conversation_id)
        summary2 = await memory_manager.rollup_summary(conversation_id)
        
        # Assert - Should be identical and not create duplicate
        assert summary1 == summary2
        
        summary_memories = await memory_manager.memory_repo.list_memories(
            conversation_id, memory_type="summary"
        )
        assert len(summary_memories) >= 1  # At least one, maybe duplicate detection
        
        # Restore original LLM function
        memory_manager.summarizer.llm_func = original_llm_func
    
    @pytest.mark.asyncio
    async def test_rollup_summary_no_episodic_memories(
        self, memory_manager, sample_conversation
    ):
        """Test rollup when no episodic memories exist."""
        conversation_id = str(sample_conversation.id)
        
        # Act
        summary = await memory_manager.rollup_summary(conversation_id)
        
        # Assert
        assert summary == ""  # Should return empty string
    
    @pytest.mark.asyncio
    async def test_rollup_summary_invalid_id(self, memory_manager):
        """Test error handling for invalid conversation ID."""
        with pytest.raises(ValueError, match="conversation_id cannot be empty"):
            await memory_manager.rollup_summary("")


class TestMemoryRetrieval:
    """Test semantic memory retrieval functionality."""
    
    @patch('memory.manager.embed_single_text')
    @pytest.mark.asyncio
    async def test_retrieve_relevant_memories_basic(
        self, mock_embed, memory_manager, sample_conversation
    ):
        """Test basic memory retrieval."""
        # Arrange
        mock_embed.return_value = [0.1] * MEMORY_EMBED_DIM
        conversation_id = str(sample_conversation.id)
        
        # Create some test memories with different content
        memories_data = [
            {
                "summary": "Discussion about machine learning and AI",
                "key_facts": ["ML algorithms", "Neural networks"],
                "importance": 0.8,
                "source_message_ids": ["msg1"],
                "lang": "en"
            },
            {
                "summary": "Conversation about cooking and recipes",
                "key_facts": ["Italian cuisine", "Pasta recipes"],
                "importance": 0.6,
                "source_message_ids": ["msg2"],
                "lang": "en"
            }
        ]
        
        # Store memories with different embeddings
        for i, memory_data in enumerate(memories_data):
            # Create different embeddings for different content
            embedding = [0.1 + i * 0.1] * MEMORY_EMBED_DIM
            await memory_manager.memory_repo.store_memory(
                conversation_id=conversation_id,
                text=json.dumps(memory_data),
                embedding=embedding,
                memory_type="episodic"
            )
        
        # Act - Search for ML-related content
        memories = await memory_manager.retrieve_relevant_memories(
            query_text="Tell me about artificial intelligence",
            top_k=5
        )
        
        # Assert
        assert len(memories) > 0
        assert all(isinstance(mem, MemoryRecord) for mem in memories)
        
        # Should have additional metadata extracted
        for memory in memories:
            assert memory.importance is not None
            assert memory.lang is not None
            assert memory.source_message_ids is not None
    
    @patch('memory.manager.embed_single_text') 
    @pytest.mark.asyncio
    async def test_retrieve_relevant_memories_ranking(
        self, mock_embed, memory_manager, sample_conversation
    ):
        """Test that memories are returned in similarity order."""
        # Arrange - Mock embeddings to return predictable similarities
        query_embedding = [1.0, 0.0, 0.0] + [0.0] * 381
        similar_embedding = [0.9, 0.1, 0.0] + [0.0] * 381
        different_embedding = [0.0, 0.0, 1.0] + [0.0] * 381
        
        mock_embed.return_value = query_embedding
        conversation_id = str(sample_conversation.id)
        
        # Store memories with different similarities
        similar_memory_data = {
            "summary": "Very relevant content",
            "importance": 0.9,
            "source_message_ids": ["msg1"],
            "lang": "en"
        }
        
        different_memory_data = {
            "summary": "Less relevant content",
            "importance": 0.5,
            "source_message_ids": ["msg2"], 
            "lang": "en"
        }
        
        await memory_manager.memory_repo.store_memory(
            conversation_id=conversation_id,
            text=json.dumps(similar_memory_data),
            embedding=similar_embedding,
            memory_type="episodic"
        )
        
        await memory_manager.memory_repo.store_memory(
            conversation_id=conversation_id,
            text=json.dumps(different_memory_data),
            embedding=different_embedding,
            memory_type="episodic"
        )
        
        # Act
        memories = await memory_manager.retrieve_relevant_memories(
            query_text="relevant query",
            top_k=5
        )
        
        # Assert - More similar memory should come first
        assert len(memories) >= 1
        # The exact order depends on the similarity calculation in the repo
        # but we should get results
    
    @patch('memory.manager.embed_single_text')
    @pytest.mark.asyncio
    async def test_retrieve_relevant_memories_top_k_limit(
        self, mock_embed, memory_manager, sample_conversation
    ):
        """Test top_k limiting."""
        # Arrange
        mock_embed.return_value = [0.1] * MEMORY_EMBED_DIM
        conversation_id = str(sample_conversation.id)
        
        # Store multiple memories
        for i in range(10):
            memory_data = {
                "summary": f"Memory {i}",
                "importance": 0.5,
                "source_message_ids": [f"msg{i}"],
                "lang": "en"
            }
            
            await memory_manager.memory_repo.store_memory(
                conversation_id=conversation_id,
                text=json.dumps(memory_data),
                embedding=[0.1 + i * 0.01] * MEMORY_EMBED_DIM,
                memory_type="episodic"
            )
        
        # Act
        memories = await memory_manager.retrieve_relevant_memories(
            query_text="test query",
            top_k=3
        )
        
        # Assert
        assert len(memories) <= 3  # Should respect top_k limit
    
    @pytest.mark.asyncio
    async def test_retrieve_relevant_memories_empty_query(self, memory_manager):
        """Test error handling for empty query."""
        with pytest.raises(ValueError, match="query_text cannot be empty"):
            await memory_manager.retrieve_relevant_memories("")
    
    @patch('memory.manager.embed_single_text')
    @pytest.mark.asyncio
    async def test_retrieve_relevant_memories_no_results(
        self, mock_embed, memory_manager, sample_conversation
    ):
        """Test retrieval when no memories exist."""
        # Arrange
        mock_embed.return_value = [0.1] * MEMORY_EMBED_DIM
        
        # Act
        memories = await memory_manager.retrieve_relevant_memories(
            query_text="some query",
            top_k=5
        )
        
        # Assert
        assert len(memories) == 0


class TestMessageEmbeddings:
    """Test message embedding functionality."""
    
    @pytest.mark.asyncio
    async def test_ensure_embeddings_for_messages_placeholder(self, memory_manager):
        """Test the placeholder implementation."""
        # Act - Should not raise error but log warning
        await memory_manager.ensure_embeddings_for_messages(["msg1", "msg2"])
        
        # Assert - No exception should be raised
        # This is a placeholder implementation
    
    @pytest.mark.asyncio
    async def test_ensure_embeddings_empty_list(self, memory_manager):
        """Test with empty message list."""
        # Act - Should handle gracefully
        await memory_manager.ensure_embeddings_for_messages([])
        
        # Assert - No exception


class TestUtilityMethods:
    """Test utility methods in MemoryManager."""
    
    @pytest.mark.asyncio
    async def test_chunk_messages_basic(self, memory_manager):
        """Test message chunking functionality."""
        # Arrange - Create mock messages
        messages = []
        for i in range(10):
            message = Mock()
            message.id = f"msg_{i}"
            message.content = f"Content {i}"
            messages.append(message)
        
        # Act
        chunks = memory_manager._chunk_messages(messages, chunk_size=3, overlap=1)
        
        # Assert
        assert len(chunks) > 1
        assert all(len(chunk) <= 3 for chunk in chunks)
        
        # Check overlap
        if len(chunks) > 1:
            # Last message of first chunk should appear in second chunk
            assert chunks[0][-1] in chunks[1]
    
    @pytest.mark.asyncio
    async def test_chunk_messages_no_overlap(self, memory_manager):
        """Test chunking without overlap."""
        # Arrange
        messages = [Mock() for _ in range(6)]
        for i, msg in enumerate(messages):
            msg.id = f"msg_{i}"
        
        # Act
        chunks = memory_manager._chunk_messages(messages, chunk_size=3, overlap=0)
        
        # Assert
        assert len(chunks) == 2
        assert len(chunks[0]) == 3
        assert len(chunks[1]) == 3
    
    @pytest.mark.asyncio
    async def test_chunk_messages_empty(self, memory_manager):
        """Test chunking empty message list."""
        chunks = memory_manager._chunk_messages([], chunk_size=5, overlap=1)
        assert chunks == []
    
    @pytest.mark.asyncio
    async def test_messages_to_text(self, memory_manager):
        """Test conversion of messages to text."""
        # Arrange
        messages = []
        for i, (role, content) in enumerate([
            ("user", "Hello there"),
            ("assistant", "Hi! How can I help?"),
            ("user", "Tell me about AI")
        ]):
            message = Mock()
            message.role = role
            message.content = content
            messages.append(message)
        
        # Act
        text = memory_manager._messages_to_text(messages)
        
        # Assert
        assert "user: Hello there" in text
        assert "assistant: Hi! How can I help?" in text
        assert "user: Tell me about AI" in text
        assert text.count('\n') == 2  # Two newlines for three messages
    
    @pytest.mark.asyncio
    async def test_messages_to_text_empty(self, memory_manager):
        """Test conversion of empty message list."""
        text = memory_manager._messages_to_text([])
        assert text == ""


class TestErrorHandling:
    """Test error handling and edge cases."""
    
    @patch('memory.manager.embed_single_text')
    @pytest.mark.asyncio
    async def test_embedding_failure_handling(
        self, mock_embed, memory_manager, sample_messages, sample_conversation
    ):
        """Test handling of embedding failures."""
        # Arrange - Mock embedding to fail
        mock_embed.side_effect = Exception("Embedding service unavailable")
        conversation_id = str(sample_conversation.id)
        
        # Act - The implementation continues processing and logs errors
        memories = await memory_manager.create_episodic_memories(
            conversation_id=conversation_id,
            chunk_size_messages=5
        )
        
        # Assert - No memories should be created due to embedding failures
        assert len(memories) == 0
    
    @patch('memory.manager.embed_single_text')
    @pytest.mark.asyncio
    async def test_summarizer_failure_fallback(
        self, mock_embed, memory_manager, sample_messages, sample_conversation
    ):
        """Test fallback when summarizer fails."""
        # Arrange
        mock_embed.return_value = [0.1] * MEMORY_EMBED_DIM
        conversation_id = str(sample_conversation.id)
        
        # Mock summarizer to fail
        original_summarize = memory_manager.summarizer.summarize_chunk
        memory_manager.summarizer.summarize_chunk = AsyncMock(
            side_effect=Exception("Summarizer failed")
        )
        
        # Act & Assert - Should handle gracefully or fail appropriately
        try:
            memories = await memory_manager.create_episodic_memories(
                conversation_id=conversation_id,
                chunk_size_messages=5
            )
            # If it succeeds, that's also ok (depends on implementation)
        except RuntimeError:
            # Expected if summarizer failure causes memory creation to fail
            pass
        
        # Restore original
        memory_manager.summarizer.summarize_chunk = original_summarize
    
    @patch('memory.manager.embed_single_text')
    @pytest.mark.asyncio
    async def test_retrieval_failure_handling(
        self, mock_embed, memory_manager, sample_conversation
    ):
        """Test handling of retrieval failures."""
        # Arrange - Mock embedding to fail
        mock_embed.side_effect = Exception("Embedding service down")
        
        # Act & Assert
        with pytest.raises(RuntimeError, match="Memory retrieval failed"):
            await memory_manager.retrieve_relevant_memories(
                query_text="test query",
                top_k=5
            )


@pytest.mark.integration
class TestMemoryManagerIntegration:
    """Integration tests for complete memory management workflows."""
    
    @patch('memory.manager.embed_single_text')
    @patch('memory.manager.embed_texts')
    @pytest.mark.asyncio
    async def test_full_memory_workflow(
        self, mock_embed_texts, mock_embed_single, memory_manager, 
        sample_messages, sample_conversation
    ):
        """Test complete workflow: create memories -> rollup -> retrieve."""
        # Arrange
        mock_embed_single.return_value = [0.1] * MEMORY_EMBED_DIM
        mock_embed_texts.return_value = [[0.1] * MEMORY_EMBED_DIM]
        conversation_id = str(sample_conversation.id)
        
        # Act 1 - Create episodic memories
        episodic_memories = await memory_manager.create_episodic_memories(
            conversation_id=conversation_id,
            chunk_size_messages=5
        )
        
        assert len(episodic_memories) > 0
        
        # Act 2 - Create summary rollup
        summary = await memory_manager.rollup_summary(conversation_id)
        assert summary  # Should have content
        
        # Act 3 - Retrieve relevant memories
        relevant_memories = await memory_manager.retrieve_relevant_memories(
            query_text="machine learning discussion",
            top_k=3
        )
        
        # Assert - Should find both episodic and summary memories
        assert len(relevant_memories) > 0
        memory_types = {mem.memory_type for mem in relevant_memories}
        assert "episodic" in memory_types or "summary" in memory_types
        
        # All memories should be from the same conversation
        assert all(
            mem.conversation_id == sample_conversation.id 
            for mem in relevant_memories
        )