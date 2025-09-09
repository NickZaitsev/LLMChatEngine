"""
Memory management for AI girlfriend bot.

This module provides the main MemoryManager class that orchestrates episodic memory
creation, summarization, embedding, and retrieval.
"""

import asyncio
import hashlib
import json
import logging
from typing import List, Dict, Any, Optional, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from storage.interfaces import MessageRepo, MemoryRepo, ConversationRepo, Message, Memory
from .embedding import embed_texts, embed_single_text
from .summarizer import Summarizer, SummarizerOutput

logger = logging.getLogger(__name__)


@dataclass
class MemoryRecord:
    """
    Memory record with additional metadata for retrieval results.
    
    This extends the basic Memory interface with additional fields needed
    for the memory management API.
    """
    id: UUID
    conversation_id: UUID
    memory_type: str
    text: str
    created_at: datetime
    embedding: Optional[List[float]] = None
    importance: Optional[float] = None
    lang: Optional[str] = None
    source_message_ids: Optional[List[str]] = None
    
    @classmethod
    def from_memory(cls, memory: Memory, **kwargs) -> 'MemoryRecord':
        """Create MemoryRecord from storage Memory object."""
        return cls(
            id=memory.id,
            conversation_id=memory.conversation_id,
            memory_type=memory.memory_type,
            text=memory.text,
            created_at=memory.created_at,
            embedding=memory.embedding,
            **kwargs
        )


class MemoryManager:
    """
    Main memory management class for episodic memory creation and retrieval.
    
    This class orchestrates the process of:
    - Creating episodic memories from message chunks
    - Rolling up summaries into conversation profiles
    - Retrieving relevant memories through semantic search
    - Managing embeddings for efficient search
    """
    
    def __init__(
        self, 
        message_repo: MessageRepo, 
        memory_repo: MemoryRepo, 
        conversation_repo: ConversationRepo, 
        config: Mapping[str, Any]
    ):
        """
        Initialize MemoryManager with repository dependencies and configuration.
        
        Args:
            message_repo: Repository for message storage/retrieval
            memory_repo: Repository for memory storage/retrieval  
            conversation_repo: Repository for conversation metadata
            config: Configuration dictionary containing:
                - embed_model: Embedding model name (default: sentence-transformers/all-MiniLM-L6-v2)
                - summarizer_mode: "llm" or "local"
                - llm_summarize: Async function for LLM summarization (if mode="llm")
                - local_model: HuggingFace model name (if mode="local")
                - chunk_overlap: Number of overlapping messages between chunks (default: 2)
        """
        self.message_repo = message_repo
        self.memory_repo = memory_repo
        self.conversation_repo = conversation_repo
        self.config = dict(config)  # Make mutable copy
        
        # Set defaults
        self.embed_model = self.config.get("embed_model", "sentence-transformers/all-MiniLM-L6-v2")
        self.chunk_overlap = self.config.get("chunk_overlap", 2)
        
        # Initialize summarizer
        summarizer_config = {
            "mode": self.config.get("summarizer_mode", "llm"),
            "llm_summarize": self.config.get("llm_summarize"),
            "local_model": self.config.get("local_model", "facebook/bart-large-cnn")
        }
        
        try:
            self.summarizer = Summarizer(summarizer_config)
        except Exception as e:
            logger.warning(f"Failed to initialize summarizer: {e}, using fallback")
            # Fallback to local mode
            fallback_config = {"mode": "local", "local_model": "facebook/bart-large-cnn"}
            self.summarizer = Summarizer(fallback_config)
        
        logger.info(f"MemoryManager initialized with embed_model={self.embed_model}")
    
    async def create_episodic_memories(
        self, 
        conversation_id: str, 
        chunk_size_messages: int = 15
    ) -> List[MemoryRecord]:
        """
        Create episodic memories from conversation messages.
        
        Fetches raw messages, chunks them by message count, generates summaries,
        computes embeddings, and stores them as episodic memories.
        
        Args:
            conversation_id: UUID of the conversation to process
            chunk_size_messages: Number of messages per chunk
            
        Returns:
            List of created MemoryRecord objects
            
        Raises:
            ValueError: If conversation_id is invalid
            RuntimeError: If memory creation fails
        """
        if not conversation_id:
            raise ValueError("conversation_id cannot be empty")
        
        logger.info(f"Creating episodic memories for conversation {conversation_id}")
        
        try:
            # Fetch all messages for the conversation (do not delete them)
            messages = await self.message_repo.list_messages(conversation_id, limit=1000)
            
            if not messages:
                logger.info(f"No messages found for conversation {conversation_id}")
                return []
            
            logger.info(f"Processing {len(messages)} messages in chunks of {chunk_size_messages}")
            
            # Check what memories already exist to avoid duplicates
            existing_memories = await self.memory_repo.list_memories(
                conversation_id, memory_type="episodic"
            )
            existing_hashes = set()
            for memory in existing_memories:
                # Extract hash from memory text if it contains our metadata
                try:
                    if memory.text.startswith('{') and memory.text.endswith('}'):
                        memory_data = json.loads(memory.text)
                        if 'content_hash' in memory_data:
                            existing_hashes.add(memory_data['content_hash'])
                except (json.JSONDecodeError, KeyError):
                    pass
            
            # Create chunks with overlap
            chunks = self._chunk_messages(messages, chunk_size_messages, self.chunk_overlap)
            created_memories = []
            
            for i, chunk in enumerate(chunks):
                try:
                    # Create content text from chunk
                    chunk_text = self._messages_to_text(chunk)
                    
                    # Create content hash for deduplication
                    content_hash = hashlib.sha256(chunk_text.encode()).hexdigest()[:16]
                    
                    # Skip if we already have this content
                    if content_hash in existing_hashes:
                        logger.debug(f"Skipping duplicate chunk {i+1}/{len(chunks)}")
                        continue
                    
                    # Get message IDs from chunk
                    source_message_ids = [str(msg.id) for msg in chunk]
                    
                    # Summarize the chunk
                    summary_output = await self.summarizer.summarize_chunk(
                        chunk_text, source_message_ids
                    )
                    
                    # Create structured memory data
                    memory_data = {
                        "summary": summary_output.summary_text,
                        "key_facts": summary_output.key_facts,
                        "importance": summary_output.importance,
                        "source_message_ids": summary_output.source_message_ids,
                        "lang": summary_output.lang,
                        "content_hash": content_hash,
                        "chunk_index": i,
                        "created_at": datetime.now(timezone.utc).isoformat()
                    }
                    
                    memory_text = json.dumps(memory_data, ensure_ascii=False, separators=(',', ':'))
                    
                    # Generate embedding for the summary text
                    embedding = await embed_single_text(
                        summary_output.summary_text, 
                        model_name=self.embed_model
                    )
                    
                    # Store episodic memory
                    memory = await self.memory_repo.store_memory(
                        conversation_id=conversation_id,
                        text=memory_text,
                        embedding=embedding,
                        memory_type="episodic"
                    )
                    
                    # Create MemoryRecord for return
                    memory_record = MemoryRecord.from_memory(
                        memory,
                        importance=summary_output.importance,
                        lang=summary_output.lang,
                        source_message_ids=summary_output.source_message_ids
                    )
                    
                    created_memories.append(memory_record)
                    existing_hashes.add(content_hash)  # Avoid duplicates within this run
                    
                    logger.debug(f"Created episodic memory {i+1}/{len(chunks)} "
                               f"with importance {summary_output.importance:.2f}")
                
                except Exception as e:
                    logger.error(f"Failed to create memory for chunk {i+1}: {e}")
                    continue
            
            logger.info(f"Created {len(created_memories)} new episodic memories")
            return created_memories
        
        except Exception as e:
            logger.error(f"Failed to create episodic memories: {e}")
            raise RuntimeError(f"Memory creation failed: {e}") from e
    
    async def rollup_summary(self, conversation_id: str) -> str:
        """
        Create or update a rolling summary for the conversation.
        
        Fetches latest episodic memories, merges them with existing summary,
        and stores the result as a single "summary" type memory.
        
        Args:
            conversation_id: UUID of the conversation to summarize
            
        Returns:
            The updated summary text
            
        Raises:
            ValueError: If conversation_id is invalid
        """
        if not conversation_id:
            raise ValueError("conversation_id cannot be empty")
        
        logger.info(f"Rolling up summary for conversation {conversation_id}")
        
        try:
            # Get existing summary
            summary_memories = await self.memory_repo.list_memories(
                conversation_id, memory_type="summary"
            )
            
            existing_profile = ""
            if summary_memories:
                # Use the most recent summary
                latest_summary = max(summary_memories, key=lambda m: m.created_at)
                try:
                    if latest_summary.text.startswith('{'):
                        summary_data = json.loads(latest_summary.text)
                        existing_profile = summary_data.get("profile", latest_summary.text)
                    else:
                        existing_profile = latest_summary.text
                except json.JSONDecodeError:
                    existing_profile = latest_summary.text
            
            # Get recent episodic memories to merge
            episodic_memories = await self.memory_repo.list_memories(
                conversation_id, memory_type="episodic"
            )
            
            if not episodic_memories:
                logger.info(f"No episodic memories to merge for conversation {conversation_id}")
                return existing_profile
            
            # Parse episodic memories into SummarizerOutput objects
            new_summaries = []
            for memory in episodic_memories:
                try:
                    if memory.text.startswith('{'):
                        memory_data = json.loads(memory.text)
                        summary_output = SummarizerOutput(
                            summary_text=memory_data.get("summary", ""),
                            key_facts=memory_data.get("key_facts", []),
                            importance=memory_data.get("importance", 0.5),
                            source_message_ids=memory_data.get("source_message_ids", []),
                            lang=memory_data.get("lang", "en")
                        )
                        new_summaries.append(summary_output)
                except (json.JSONDecodeError, KeyError) as e:
                    logger.warning(f"Failed to parse episodic memory {memory.id}: {e}")
                    continue
            
            if not new_summaries:
                logger.info(f"No valid episodic memories to merge")
                return existing_profile
            
            # Merge summaries
            merge_result = await self.summarizer.merge_summaries(existing_profile, new_summaries)
            
            # Create hash for deduplication
            profile_hash = hashlib.sha256(merge_result.updated_profile.encode()).hexdigest()[:16]
            
            # Check if this profile already exists (idempotency)
            for existing in summary_memories:
                try:
                    if existing.text.startswith('{'):
                        existing_data = json.loads(existing.text)
                        if existing_data.get("profile_hash") == profile_hash:
                            logger.info("Summary unchanged, skipping duplicate storage")
                            return merge_result.updated_profile
                except (json.JSONDecodeError, KeyError):
                    pass
            
            # Create structured summary data
            summary_data = {
                "profile": merge_result.updated_profile,
                "change_log": merge_result.change_log,
                "lang": merge_result.lang,
                "profile_hash": profile_hash,
                "episodic_count": len(new_summaries),
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            
            summary_text = json.dumps(summary_data, ensure_ascii=False, separators=(',', ':'))
            
            # Generate embedding for the profile
            embedding = await embed_single_text(
                merge_result.updated_profile,
                model_name=self.embed_model
            )
            
            # Store the updated summary
            await self.memory_repo.store_memory(
                conversation_id=conversation_id,
                text=summary_text,
                embedding=embedding,
                memory_type="summary"
            )
            
            logger.info(f"Updated summary for conversation {conversation_id}")
            return merge_result.updated_profile
        
        except Exception as e:
            logger.error(f"Failed to rollup summary: {e}")
            raise RuntimeError(f"Summary rollup failed: {e}") from e
    
    async def retrieve_relevant_memories(
        self, 
        query_text: str, 
        top_k: int = 6
    ) -> List[MemoryRecord]:
        """
        Retrieve memories relevant to a query using semantic search.
        
        Embeds the query text and searches for similar memories using vector similarity.
        
        Args:
            query_text: Text to search for
            top_k: Number of top results to return
            
        Returns:
            List of relevant MemoryRecord objects ordered by similarity
            
        Raises:
            ValueError: If query_text is empty
        """
        if not query_text or not query_text.strip():
            raise ValueError("query_text cannot be empty")
        
        logger.debug(f"Retrieving memories for query: {query_text[:100]}...")
        
        try:
            # Embed the query
            query_embedding = await embed_single_text(
                query_text.strip(),
                model_name=self.embed_model
            )
            
            # Search for similar memories
            similar_memories = await self.memory_repo.search_memories(
                query_embedding=query_embedding,
                top_k=top_k,
                similarity_threshold=0.5  # Reasonable threshold
            )
            
            # Convert to MemoryRecord objects with additional metadata
            memory_records = []
            
            for memory in similar_memories:
                # Extract additional metadata from structured memory text
                importance = None
                lang = None
                source_message_ids = None
                
                try:
                    if memory.text.startswith('{'):
                        memory_data = json.loads(memory.text)
                        importance = memory_data.get("importance")
                        lang = memory_data.get("lang")
                        source_message_ids = memory_data.get("source_message_ids", [])
                except (json.JSONDecodeError, KeyError):
                    pass
                
                memory_record = MemoryRecord.from_memory(
                    memory,
                    importance=importance,
                    lang=lang,
                    source_message_ids=source_message_ids
                )
                
                memory_records.append(memory_record)
            
            logger.debug(f"Retrieved {len(memory_records)} relevant memories")
            return memory_records
        
        except Exception as e:
            logger.error(f"Failed to retrieve memories: {e}")
            raise RuntimeError(f"Memory retrieval failed: {e}") from e
    
    async def ensure_embeddings_for_messages(self, message_ids: List[str]) -> None:
        """
        Ensure embeddings exist for specified messages by batch processing.
        
        This method checks which messages are missing embeddings and generates
        them in batches for efficiency.
        
        Args:
            message_ids: List of message IDs to ensure embeddings for
            
        Raises:
            ValueError: If message_ids is empty or invalid
        """
        if not message_ids:
            logger.debug("No message IDs provided for embedding")
            return
        
        logger.info(f"Ensuring embeddings for {len(message_ids)} messages")
        
        try:
            # For now, this is a placeholder implementation since the storage interfaces
            # don't include message embeddings. In a full implementation, you might:
            # 1. Check which messages are missing embeddings
            # 2. Batch fetch the message content
            # 3. Generate embeddings for missing ones
            # 4. Store embeddings back to messages
            
            # This could be implemented as a separate message embedding table
            # or by extending the Message model to include embeddings
            
            logger.warning("Message embedding functionality not yet implemented in storage layer")
            logger.info("Consider extending Message model to include embedding field")
            
            # Placeholder: just log that we would process these messages
            logger.debug(f"Would process embeddings for messages: {message_ids[:5]}...")
            
        except Exception as e:
            logger.error(f"Failed to ensure message embeddings: {e}")
            raise RuntimeError(f"Message embedding failed: {e}") from e
    
    def _chunk_messages(
        self, 
        messages: List[Message], 
        chunk_size: int, 
        overlap: int = 2
    ) -> List[List[Message]]:
        """
        Chunk messages into overlapping groups.
        
        Args:
            messages: List of messages to chunk
            chunk_size: Number of messages per chunk
            overlap: Number of overlapping messages between chunks
            
        Returns:
            List of message chunks
        """
        if not messages:
            return []
        
        chunks = []
        start = 0
        
        while start < len(messages):
            end = min(start + chunk_size, len(messages))
            chunk = messages[start:end]
            chunks.append(chunk)
            
            # Move start position with overlap
            start = max(start + chunk_size - overlap, start + 1)
            
            # Avoid infinite loop if overlap >= chunk_size
            if start >= len(messages):
                break
        
        return chunks
    
    def _messages_to_text(self, messages: List[Message]) -> str:
        """
        Convert a list of messages to a text representation.
        
        Args:
            messages: List of messages to convert
            
        Returns:
            Formatted text representation
        """
        if not messages:
            return ""
        
        text_parts = []
        for message in messages:
            # Format: "Role: Content"
            text_parts.append(f"{message.role}: {message.content}")
        
        return " \n ".join(text_parts)


# Export public API
__all__ = [
    'MemoryManager',
    'MemoryRecord'
]