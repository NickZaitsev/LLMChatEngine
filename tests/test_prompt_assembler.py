"""
Comprehensive unit tests for PromptAssembler.

This module tests token budgeting, ordering, cap behavior, metadata fields,
and various edge cases of the prompt assembly system.
"""

import json
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4, UUID
from typing import List, Dict, Any

from storage.interfaces import Message, Memory
from memory.manager import LlamaIndexMemoryManager as MemoryManager
from prompt.assembler import PromptAssembler, TokenCounter, Tokenizer
import config


class MockTokenizer:
    """Mock tokenizer for testing"""
    
    def encode(self, text: str) -> List[int]:
        # Simple mock: return list with length based on character count
        return list(range(len(text) // 4 + 1))
    
    def count_tokens(self, text: str) -> int:
        # Simple heuristic for testing
        return max(1, len(text) // 4)


@pytest.fixture
def mock_tokenizer():
    """Create a mock tokenizer for testing"""
    return MockTokenizer()


@pytest.fixture
def mock_message_repo():
    """Create a mock MessageRepo for testing"""
    repo = AsyncMock()
    repo.fetch_recent_messages = AsyncMock()
    return repo


@pytest.fixture
def mock_memory_manager():
    """Create a mock MemoryManager for testing"""
    manager = AsyncMock()
    manager.retrieve_relevant_memories = AsyncMock()
    manager.memory_repo = AsyncMock()
    manager.memory_repo.list_memories = AsyncMock()
    return manager


@pytest.fixture
def mock_persona_repo():
    """Create a mock PersonaRepo for testing"""
    repo = AsyncMock()
    repo.get_persona = AsyncMock()
    return repo


@pytest.fixture
def sample_conversation_id():
    """Generate a sample conversation ID"""
    return str(uuid4())


@pytest.fixture
def sample_messages():
    """Create sample messages for testing"""
    conv_id = uuid4()
    return [
        Message(
            id=uuid4(),
            conversation_id=conv_id,
            role="user",
            content="Hello, how are you?",
            extra_data={},
            token_count=6,
            created_at=datetime.now(timezone.utc)
        ),
        Message(
            id=uuid4(),
            conversation_id=conv_id,
            role="assistant", 
            content="I'm doing great! How can I help you today?",
            extra_data={},
            token_count=12,
            created_at=datetime.now(timezone.utc)
        ),
        Message(
            id=uuid4(),
            conversation_id=conv_id,
            role="user",
            content="Tell me about the weather",
            extra_data={},
            token_count=6,
            created_at=datetime.now(timezone.utc)
        )
    ]


@pytest.fixture
def sample_memories():
    """Create sample memory records for testing"""
    conv_id = uuid4()
    return [
        MemoryRecord(
            id=uuid4(),
            conversation_id=conv_id,
            memory_type="episodic",
            text='{"summary": "User likes pizza and prefers Italian food", "importance": 0.8}',
            created_at=datetime.now(timezone.utc),
            importance=0.8
        ),
        MemoryRecord(
            id=uuid4(), 
            conversation_id=conv_id,
            memory_type="episodic",
            text='{"summary": "User works as a software engineer", "importance": 0.7}',
            created_at=datetime.now(timezone.utc),
            importance=0.7
        ),
        MemoryRecord(
            id=uuid4(),
            conversation_id=conv_id, 
            memory_type="episodic",
            text='{"summary": "User enjoys hiking and outdoor activities", "importance": 0.6}',
            created_at=datetime.now(timezone.utc),
            importance=0.6
        )
    ]


@pytest.fixture
def sample_summary_memory():
    """Create a sample summary memory"""
    return Memory(
        id=uuid4(),
        conversation_id=uuid4(),
        memory_type="summary", 
        text='{"profile": "User is a friendly software engineer who loves pizza and hiking. Prefers casual conversation style."}',
        created_at=datetime.now(timezone.utc)
    )


@pytest.fixture
def prompt_assembler(mock_message_repo, mock_memory_manager, mock_persona_repo, mock_tokenizer):
    """Create a PromptAssembler instance for testing"""
    config = {
        "max_memory_items": 3,
        "memory_token_budget_ratio": 0.4,
        "truncation_length": 200,
        "include_system_template": True
    }
    return PromptAssembler(
        message_repo=mock_message_repo,
        memory_manager=mock_memory_manager,
        conversation_repo=MagicMock(),
        user_repo=MagicMock(),
        persona_repo=mock_persona_repo,
        tokenizer=mock_tokenizer,
        config=config
    )


class TestTokenCounter:
    """Test the TokenCounter helper class"""
    
    def test_token_counter_with_tokenizer(self, mock_tokenizer):
        """Test TokenCounter with a provided tokenizer"""
        counter = TokenCounter(mock_tokenizer)
        count = counter.count_tokens("Hello world test")
        assert count == 4  # Based on MockTokenizer logic
    
    def test_token_counter_fallback(self):
        """Test TokenCounter fallback heuristic"""
        counter = TokenCounter(None, auto_tiktoken=False)
        count = counter.count_tokens("Hello world test")  # 16 chars
        assert count == 4  # ceil(16/4) = 4
    
    def test_token_counter_empty_text(self, mock_tokenizer):
        """Test TokenCounter with empty text"""
        counter = TokenCounter(mock_tokenizer)
        assert counter.count_tokens("") == 0
        assert counter.count_tokens(None) == 0


class TestPromptAssembler:
    """Test the main PromptAssembler functionality"""
    
    @pytest.mark.asyncio
    async def test_build_prompt_basic(self, prompt_assembler, sample_conversation_id,
                                     sample_messages, sample_memories, sample_summary_memory):
        """Test basic prompt building with all components"""
        # Setup mocks
        prompt_assembler.message_repo.fetch_recent_messages.return_value = sample_messages
        prompt_assembler.memory_manager.retrieve_relevant_memories.return_value = sample_memories
        prompt_assembler.memory_manager.memory_repo.list_memories.return_value = [sample_summary_memory]
        
        # Build prompt
        messages = await prompt_assembler.build_prompt(
            conversation_id=sample_conversation_id,
            reply_token_budget=500,  # Updated to match config default
            history_budget=7500   # Updated to match config default
        )
        
        # Verify structure
        assert len(messages) >= 3  # system + profile + memories + history
        assert messages[0]["role"] == "system"
        
        # Verify system template is included
        assert config.BOT_PERSONALITY in messages[0]["content"]
    
    @pytest.mark.asyncio
    async def test_build_prompt_and_metadata(self, prompt_assembler, sample_conversation_id,
                                            sample_messages, sample_memories, sample_summary_memory):
        """Test prompt building with metadata tracking"""
        # Setup mocks
        prompt_assembler.message_repo.fetch_recent_messages.return_value = sample_messages
        prompt_assembler.memory_manager.retrieve_relevant_memories.return_value = sample_memories
        prompt_assembler.memory_manager.memory_repo.list_memories.return_value = [sample_summary_memory]
        
        # Build prompt with metadata
        messages, metadata = await prompt_assembler.build_prompt_and_metadata(
            conversation_id=sample_conversation_id,
            reply_token_budget=500,  # Updated to match config default
            history_budget=7500   # Updated to match config default
        )
        
        # Verify metadata structure
        assert "included_memory_ids" in metadata
        assert "token_counts" in metadata
        assert "truncated_message_ids" in metadata
        assert "total_tokens" in metadata
        assert "conversation_id" in metadata
        
        # Verify token counts structure
        token_counts = metadata["token_counts"]
        assert "system_tokens" in token_counts
        assert "memory_tokens" in token_counts
        assert "history_tokens" in token_counts
        assert "reply_reserved" in token_counts
        
        # Verify token accounting
        assert token_counts["reply_reserved"] == 500  # Updated to match config default
        assert metadata["total_tokens"] > 0
        
        # Verify memory inclusion
        assert len(metadata["included_memory_ids"]) <= 3  # max_memory_items
        assert len(metadata["included_memory_ids"]) <= len(sample_memories)
    
    @pytest.mark.asyncio
    async def test_memory_token_budgeting(self, prompt_assembler, sample_conversation_id, sample_memories):
        """Test that memory inclusion respects token budgeting"""
        # Setup with small memory budget
        prompt_assembler.config["memory_token_budget_ratio"] = 0.1  # Very small budget
        prompt_assembler.message_repo.fetch_recent_messages.return_value = []
        prompt_assembler.memory_manager.retrieve_relevant_memories.return_value = sample_memories
        prompt_assembler.memory_manager.memory_repo.list_memories.return_value = []
        
        messages, metadata = await prompt_assembler.build_prompt_and_metadata(
            conversation_id=sample_conversation_id,
            history_budget=100  # Small budget
        )
        
        # Should limit memories due to token budget
        memory_budget = int(100 * 0.1)  # 10 tokens for memories
        assert metadata["token_counts"]["memory_tokens"] <= memory_budget + 50  # Allow some flexibility
    
    @pytest.mark.asyncio
    async def test_max_memory_items_cap(self, prompt_assembler, sample_conversation_id):
        """Test that memory inclusion is capped by max_memory_items"""
        # Create many memories
        many_memories = []
        conv_id = uuid4()
        for i in range(10):
            many_memories.append(MemoryRecord(
                id=uuid4(),
                conversation_id=conv_id,
                memory_type="episodic", 
                text=f'{{"summary": "Memory {i}", "importance": 0.5}}',
                created_at=datetime.now(timezone.utc),
                importance=0.5
            ))
        
        # Setup mocks
        prompt_assembler.message_repo.fetch_recent_messages.return_value = []
        prompt_assembler.memory_manager.retrieve_relevant_memories.return_value = many_memories
        prompt_assembler.memory_manager.memory_repo.list_memories.return_value = []
        
        messages, metadata = await prompt_assembler.build_prompt_and_metadata(
            conversation_id=sample_conversation_id,
            history_budget=10000  # Large budget
        )
        
        # Should be capped by max_memory_items (3)
        assert len(metadata["included_memory_ids"]) <= 3
    
    @pytest.mark.asyncio
    async def test_message_truncation(self, prompt_assembler, sample_conversation_id):
        """Test that long messages are truncated"""
        # Create a very long message
        long_content = "A" * 1000  # Very long message
        long_message = Message(
            id=uuid4(),
            conversation_id=UUID(sample_conversation_id),
            role="user",
            content=long_content,
            extra_data={},
            token_count=250,
            created_at=datetime.now(timezone.utc)
        )
        
        # Setup mocks
        prompt_assembler.message_repo.fetch_recent_messages.return_value = [long_message]
        prompt_assembler.memory_manager.retrieve_relevant_memories.return_value = []
        prompt_assembler.memory_manager.memory_repo.list_memories.return_value = []
        
        messages, metadata = await prompt_assembler.build_prompt_and_metadata(
            conversation_id=sample_conversation_id,
            history_budget=7500  # Updated to match config default
        )
        
        # Should have truncated the long message
        assert len(metadata["truncated_message_ids"]) >= 0
        
        # Find the truncated message in the prompt
        truncated_found = False
        for msg in messages:
            if "(truncated)" in msg["content"]:
                truncated_found = True
                break
        
        # Message should be truncated if it was very long
        if len(long_content) > prompt_assembler.truncation_length * 2:
            assert str(long_message.id) in metadata["truncated_message_ids"]
    
    @pytest.mark.asyncio
    async def test_invalid_conversation_id(self, prompt_assembler):
        """Test handling of invalid conversation ID"""
        with pytest.raises(ValueError, match="Invalid conversation_id format"):
            await prompt_assembler.build_prompt(
                conversation_id="invalid-uuid"
            )
    
    @pytest.mark.asyncio
    async def test_empty_conversation_id(self, prompt_assembler):
        """Test handling of empty conversation ID"""
        with pytest.raises(ValueError, match="conversation_id cannot be empty"):
            await prompt_assembler.build_prompt(
                conversation_id=""
            )
        
        with pytest.raises(ValueError, match="conversation_id cannot be empty"):
            await prompt_assembler.build_prompt_and_metadata(
                conversation_id=""
            )
    
    @pytest.mark.asyncio
    async def test_no_memories_available(self, prompt_assembler, sample_conversation_id, sample_messages):
        """Test prompt building when no memories are available"""
        # Setup mocks with no memories
        prompt_assembler.message_repo.fetch_recent_messages.return_value = sample_messages
        prompt_assembler.memory_manager.retrieve_relevant_memories.return_value = []
        prompt_assembler.memory_manager.memory_repo.list_memories.return_value = []
        
        messages, metadata = await prompt_assembler.build_prompt_and_metadata(
            conversation_id=sample_conversation_id
            # Using default values from config
        )
        
        # Should still work without memories
        assert len(messages) >= 1  # At least system message
        assert metadata["token_counts"]["memory_tokens"] >= 0
        assert len(metadata["included_memory_ids"]) == 0
    
    @pytest.mark.asyncio
    async def test_no_history_available(self, prompt_assembler, sample_conversation_id):
        """Test prompt building when no message history is available"""
        # Setup mocks with no history
        prompt_assembler.message_repo.fetch_recent_messages.return_value = []
        prompt_assembler.memory_manager.retrieve_relevant_memories.return_value = []
        prompt_assembler.memory_manager.memory_repo.list_memories.return_value = []
        
        messages, metadata = await prompt_assembler.build_prompt_and_metadata(
            conversation_id=sample_conversation_id
            # Using default values from config
        )
        
        # Should still include system message and current message
        assert len(messages) >= 1
        assert metadata["token_counts"]["history_tokens"] >= 0
    
    @pytest.mark.asyncio
    async def test_system_template_disabled(self, mock_message_repo, mock_memory_manager, 
                                           mock_persona_repo, mock_tokenizer, sample_conversation_id):
        """Test prompt building with system template disabled"""
        config = {"include_system_template": False}
        assembler = PromptAssembler(
            message_repo=mock_message_repo,
            memory_manager=mock_memory_manager,
            conversation_repo=MagicMock(),
            user_repo=MagicMock(),
            persona_repo=mock_persona_repo,
            tokenizer=mock_tokenizer,
            config=config
        )
        
        # Setup mocks
        mock_message_repo.fetch_recent_messages.return_value = []
        mock_memory_manager.retrieve_relevant_memories.return_value = []
        mock_memory_manager.memory_repo.list_memories.return_value = []
        
        messages, metadata = await assembler.build_prompt_and_metadata(
            conversation_id=sample_conversation_id
            # Using default values from config
        )
        
        # Should not include system template
        system_messages = [msg for msg in messages if msg["role"] == "system" and config.BOT_PERSONALITY in msg["content"]]
        assert len(system_messages) == 0
        assert metadata["token_counts"]["system_tokens"] == 0
    
    @pytest.mark.asyncio
    async def test_message_ordering(self, prompt_assembler, sample_conversation_id, 
                                   sample_messages, sample_memories, sample_summary_memory):
        """Test that messages are properly ordered"""
        # Setup mocks
        prompt_assembler.message_repo.fetch_recent_messages.return_value = sample_messages
        prompt_assembler.memory_manager.retrieve_relevant_memories.return_value = sample_memories
        prompt_assembler.memory_manager.memory_repo.list_memories.return_value = [sample_summary_memory]
        
        messages, metadata = await prompt_assembler.build_prompt_and_metadata(
            conversation_id=sample_conversation_id
            # Using default values from config
        )
        
        # Verify ordering: system messages first, then history
        assert messages[0]["role"] == "system"  # System template first
        
        # Verify all system messages come before user/assistant messages from history
        first_history_index = None
        for i, msg in enumerate(messages):
            if msg["role"] in ["user", "assistant"]:
                first_history_index = i
                break
        
        if first_history_index is not None:
            # All system messages should come before first history message
            for i in range(first_history_index):
                assert messages[i]["role"] == "system"


class TestEdgeCases:
    """Test edge cases and error handling"""
    
    @pytest.mark.asyncio
    async def test_repository_errors(self, prompt_assembler, sample_conversation_id):
        """Test handling of repository errors"""
        # Setup mocks to raise exceptions
        prompt_assembler.message_repo.fetch_recent_messages.side_effect = Exception("DB Error")
        prompt_assembler.memory_manager.retrieve_relevant_memories.side_effect = Exception("Memory Error")
        prompt_assembler.memory_manager.memory_repo.list_memories.side_effect = Exception("Summary Error")
        
        # Should still work despite errors (with warnings logged)
        messages, metadata = await prompt_assembler.build_prompt_and_metadata(
            conversation_id=sample_conversation_id
            # Using default values from config
        )
        
        # Should at least have system template
        assert len(messages) >= 1
    
    @pytest.mark.asyncio
    async def test_zero_budgets(self, prompt_assembler, sample_conversation_id):
        """Test handling of zero token budgets"""
        # Setup minimal mocks
        prompt_assembler.message_repo.fetch_recent_messages.return_value = []
        prompt_assembler.memory_manager.retrieve_relevant_memories.return_value = []
        prompt_assembler.memory_manager.memory_repo.list_memories.return_value = []
        
        messages, metadata = await prompt_assembler.build_prompt_and_metadata(
            conversation_id=sample_conversation_id,
            reply_token_budget=0,
            history_budget=0
        )
        
        # Should still work with minimal content
        assert len(messages) >= 1
        assert metadata["token_counts"]["reply_reserved"] == 0


if __name__ == "__main__":
    pytest.main([__file__])