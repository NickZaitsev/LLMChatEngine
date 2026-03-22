"""
PromptAssembler for building LLM chat prompts with memory integration.

This module provides the PromptAssembler class that orchestrates building
chat prompts with memory context, conversation history, persona configuration,
and proper token budgeting.
"""

import logging
import math
from typing import Dict, List, Any, Optional, Mapping, Tuple, Protocol

from storage.interfaces import MessageRepo, PersonaRepo, ConversationRepo, UserRepo
from memory.manager import LlamaIndexMemoryManager
import config

logger = logging.getLogger(__name__)


class Tokenizer(Protocol):
    """Protocol for tokenizer implementations"""
    
    def encode(self, text: str) -> List[int]:
        """Encode text to tokens"""
        ...
    
    def count_tokens(self, text: str) -> int:
        """Count tokens in text"""
        ...


class TokenCounter:
    """Helper class for counting tokens with fallback heuristic"""
    
    def __init__(self, tokenizer: Optional[Tokenizer] = None, auto_tiktoken: bool = True):
        """
        Initialize token counter.
        
        Args:
            tokenizer: Optional tokenizer implementation (tiktoken preferred)
            auto_tiktoken: Whether to automatically try tiktoken if no tokenizer provided
        """
        self.tokenizer = tokenizer
        
        # Try to import tiktoken if no tokenizer provided and auto_tiktoken is enabled
        if not tokenizer and auto_tiktoken:
            try:
                import tiktoken
                encoding = tiktoken.get_encoding("cl100k_base")
                
                class TiktokenWrapper:
                    def __init__(self, encoding):
                        self._encoding = encoding
                    
                    def encode(self, text: str) -> List[int]:
                        return self._encoding.encode(text)
                    
                    def count_tokens(self, text: str) -> int:
                        return len(self._encoding.encode(text))
                
                self.tokenizer = TiktokenWrapper(encoding)
                logger.debug("Using tiktoken for token counting")
            except ImportError:
                logger.debug("tiktoken not available, using heuristic fallback")
    
    def count_tokens(self, text: str) -> int:
        """
        Count tokens in text using tokenizer or heuristic fallback.
        
        Args:
            text: Text to count tokens for
            
        Returns:
            Token count
        """
        if not text:
            return 0
        
        if self.tokenizer:
            try:
                return self.tokenizer.count_tokens(text)
            except Exception as e:
                logger.warning(f"Tokenizer failed: {e}, using fallback")
        
        # Fallback heuristic: ~4 characters per token
        return max(1, math.ceil(len(text) / 4))


class PromptAssembler:
    """
    Main class for assembling LLM chat prompts with memory integration.
    
    This class orchestrates the process of:
    - Building system prompts with persona configuration
    - Including relevant memories within token budget
    - Adding conversation history within token constraints
    - Proper token accounting and metadata tracking
    """
    
    def __init__(
        self,
        message_repo: MessageRepo,
        memory_manager: LlamaIndexMemoryManager,
        conversation_repo: ConversationRepo,
        user_repo: UserRepo,
        persona_repo: Optional[PersonaRepo] = None,
        tokenizer: Optional[Tokenizer] = None,
        config: Mapping[str, Any] = None
    ):
        """
        Initialize PromptAssembler.
        
        Args:
            message_repo: Repository for message storage/retrieval
            memory_manager: Manager for memory operations
            conversation_repo: Repository for conversation operations
            user_repo: Repository for user operations
            persona_repo: Optional repository for persona configurations
            tokenizer: Optional tokenizer for accurate token counting
            config: Configuration dictionary with:
                - max_memory_items: Maximum memory items to include (default: 3)
                - memory_token_budget_ratio: Ratio of history budget for memories (default: 0.4)
                - truncation_length: Length for message truncation (default: 200)
                - include_system_template: Whether to include base system template (default: True)
        """
        self.message_repo = message_repo
        self.memory_manager = memory_manager
        self.conversation_repo = conversation_repo
        self.user_repo = user_repo
        self.persona_repo = persona_repo
        self.token_counter = TokenCounter(tokenizer)
        
        # Set default config values
        self.config = dict(config or {})
        self.max_memory_items = self.config.get("max_memory_items", 3)
        self.memory_token_budget_ratio = self.config.get("memory_token_budget_ratio", 0.4)
        self.truncation_length = self.config.get("truncation_length", 200)
        self.include_system_template = self.config.get("include_system_template", True)
        self.personality = None  # Dynamic personality for multi-bot support
        
        logger.info(f"PromptAssembler initialized with max_memory_items={self.max_memory_items}")
    
    async def build_prompt(
        self,
        conversation_id: str,
        reply_token_budget: int = None,
        history_budget: int = None,
        user_query: Optional[str] = None
    ) -> List[Dict[str, str]]:
        """
        Build a chat prompt for LLM request.
        
        Args:
            conversation_id: UUID string of the conversation
            reply_token_budget: Tokens reserved for LLM reply (default from config)
            history_budget: Tokens available for history and memories (default from config)
            user_query: Optional current user message for memory retrieval
            
        Returns:
            List of message dicts with 'role' and 'content' keys, ordered for LLM
            
        Raises:
            ValueError: If conversation_id is invalid
        """
        # Use config defaults if not provided
        if reply_token_budget is None:
            reply_token_budget = config.PROMPT_REPLY_TOKEN_BUDGET
        if history_budget is None:
            history_budget = config.PROMPT_HISTORY_BUDGET
            
        messages, _ = await self.build_prompt_and_metadata(
            conversation_id, reply_token_budget, history_budget, user_query
        )
        return messages
    
    async def build_prompt_and_metadata(
        self,
        conversation_id: str,
        reply_token_budget: int = None,
        history_budget: int = None,
        user_query: Optional[str] = None
    ) -> Tuple[List[Dict[str, str]], Dict[str, Any]]:
        """
        Build a chat prompt with detailed metadata.
        
        Args:
            conversation_id: UUID string of the conversation
            reply_token_budget: Tokens reserved for LLM reply (default from config)
            history_budget: Tokens available for history and memories (default from config)
            user_query: Optional current user message for memory retrieval
            
        Returns:
            Tuple of (messages, metadata) where:
            - messages: List of message dicts ordered for LLM
            - metadata: Dict containing included_memory_ids, token_counts, truncated_message_ids
            
        Raises:
            ValueError: If inputs are invalid
        """
        # Use config defaults if not provided
        if reply_token_budget is None:
            reply_token_budget = config.PROMPT_REPLY_TOKEN_BUDGET
        if history_budget is None:
            history_budget = config.PROMPT_HISTORY_BUDGET
            
        if not conversation_id:
            raise ValueError("conversation_id cannot be empty")
        
        logger.info(f"Building prompt for conversation {conversation_id[:8]}...")
        
        # Validate conversation_id format
        # The conversation_id is now a string from the database, not a UUID.
        # try:
        #     UUID(conversation_id)
        # except ValueError as e:
        #     raise ValueError(f"Invalid conversation_id format: {conversation_id}") from e
        
        # Initialize tracking variables
        messages = []
        token_counts = {
            "system_tokens": 0,
            "memory_tokens": 0, 
            "history_tokens": 0,
            "reply_reserved": reply_token_budget
        }
        included_memory_ids = []
        truncated_message_ids = []

        # 1. Get conversation first (needed for bot personality lookup)
        conversation = await self.conversation_repo.get_conversation(conversation_id)

        # 2. Resolve the correct personality to use
        # Priority: self.personality (set by multibot_adapter in bot process)
        #   -> bot personality from DB (critical for Celery worker context)
        #   -> config.BOT_PERSONALITY (env var fallback)
        personality_to_use = self.personality or config.BOT_PERSONALITY
        
        if not self.personality and conversation and conversation.bot_id:
            try:
                from storage.models import Bot as BotModel
                from sqlalchemy import select
                
                async with self.conversation_repo.session_maker() as session:
                    result = await session.execute(
                        select(BotModel.personality).where(BotModel.id == conversation.bot_id)
                    )
                    bot_personality = result.scalar_one_or_none()
                    if bot_personality:
                        personality_to_use = bot_personality
                        logger.info(f"Loaded bot personality from DB for bot_id={conversation.bot_id}")
            except Exception as e:
                logger.warning(f"Failed to load bot personality from DB: {e}")

        # 3. Add system template if enabled
        if self.include_system_template:
            system_message = {"role": "system", "content": personality_to_use}
            system_tokens = self.token_counter.count_tokens(personality_to_use)
            messages.append(system_message)
            token_counts["system_tokens"] += system_tokens
            logger.debug(f"Added system template: {system_tokens} tokens")

        # 4. Add conversation summary if it exists
        if conversation and conversation.summary:
            summary_message = {"role": "system", "content": f"This is a summary of the conversation so far:\n{conversation.summary}"}
            summary_tokens = self.token_counter.count_tokens(summary_message["content"])
            messages.append(summary_message)
            token_counts["system_tokens"] += summary_tokens
            logger.debug(f"Added conversation summary: {summary_tokens} tokens")

        # 5. Calculate memory token budget
        memory_budget = int(history_budget * self.memory_token_budget_ratio)
        remaining_history_budget = history_budget - memory_budget

        # 6. Retrieve and add relevant memories
        try:
            if not self.memory_manager:
                logger.info("Memory manager not available, skipping semantic search")
            elif not conversation:
                logger.info("No conversation found, skipping memory retrieval")
            else:
                # Determine the best query for memory retrieval
                # Priority: user_query -> last user message -> conversation summary (for proactive messages)
                memory_query = user_query
                
                if memory_query:
                    logger.debug("Using provided user_query for memory query")
                else:
                    last_user_message = await self.message_repo.get_last_user_message(conversation_id)
                    if last_user_message:
                        memory_query = last_user_message.content
                        logger.debug("Using last user message from repo for memory query")
                    elif conversation.summary:
                        # Proactive messages often have no user message yet;
                        # use the conversation summary to retrieve relevant memories
                        memory_query = conversation.summary
                        logger.info("No user query or last user message; using conversation summary for memory query")
                
                if memory_query:
                    user = await self.user_repo.get_user(str(conversation.user_id))
                    if user:
                        logger.info(
                            "Querying memory for user=%s, query='%s', bot_id=%s",
                            user.username,
                            memory_query[:80],
                            conversation.bot_id,
                        )
                        context = await self.memory_manager.get_context(
                            user_id=user.username,
                            query=memory_query,
                            top_k=self.max_memory_items,
                            bot_id=str(conversation.bot_id) if conversation.bot_id else None
                        )
                        if context:
                            memory_content = f"### Memory Context\n{context}"
                            memory_message_tokens = self.token_counter.count_tokens(memory_content)
                            
                            if memory_message_tokens > memory_budget:
                                logger.warning(
                                    "Memory context (%d tokens) exceeds budget (%d tokens), truncating",
                                    memory_message_tokens, memory_budget,
                                )
                                # Simple truncation of characters as a fallback for budget management
                                # Calculating chars to keep: budget * 4 chars/token is heuristic-ish
                                # but let's be more precise by iteratively stripping lines if possible
                                lines = context.split("\n")
                                truncated_context = ""
                                current_tokens = self.token_counter.count_tokens("### Memory Context\n")
                                for line in lines:
                                    line_tokens = self.token_counter.count_tokens(line + "\n")
                                    if current_tokens + line_tokens <= memory_budget:
                                        truncated_context += line + "\n"
                                        current_tokens += line_tokens
                                    else:
                                        break
                                context = truncated_context.strip()
                                memory_content = f"### Memory Context\n{context}"
                                memory_message_tokens = current_tokens

                            if context:
                                memory_message = {"role": "system", "content": memory_content}
                                messages.append(memory_message)
                                token_counts["memory_tokens"] = memory_message_tokens
                                remaining_history_budget -= memory_message_tokens
                                # Track which memory items were included
                                for line in context.split("\n"):
                                    if line.strip():
                                        included_memory_ids.append(line.strip()[:64])
                                logger.info(f"Added memories to prompt: {memory_message_tokens} tokens")
                            else:
                                logger.warning("Memory context too large even after truncation, skipping")
                        else:
                            logger.info("Semantic search returned no results (empty vector store?)")
                    else:
                        logger.warning("User not found for conversation %s, skipping memory", conversation_id[:8])
                else:
                    logger.info("No user message or summary available, skipping memory retrieval")
        except ValueError as e:
            logger.warning(f"Failed to retrieve memories due to a value error: {e}")
        except Exception as e:
            logger.warning(f"An unexpected error occurred while retrieving memories: {e}", exc_info=True)

        # 7. Fetch active conversation history
        try:
            last_summarized_id = conversation.last_summarized_message_id if conversation else None
            recent_messages = await self.message_repo.fetch_active_messages(
                conversation_id, remaining_history_budget, last_summarized_id
            )
            logger.info(f"Retrieved {len(recent_messages)} active messages for conversation {conversation_id}")
            # for i, msg in enumerate(recent_messages):
            #     logger.info(f"  Active Message {i+1} [{msg.role}]: {msg.content[:100]}...")
            
            # Use all recent messages as-is
            # The current user message should be included as the last message in the prompt
            filtered_messages = recent_messages
            
            for msg in filtered_messages:
                # Check if message needs truncation
                content = msg.content
                message_tokens = self.token_counter.count_tokens(content)
                
                if len(content) > self.truncation_length * 2:  # Only truncate very long messages
                    content = content[:self.truncation_length] + "... (truncated)"
                    truncated_message_ids.append(str(msg.id))
                    message_tokens = self.token_counter.count_tokens(content)
                
                history_message = {
                    "role": msg.role,
                    "content": content
                }
                messages.append(history_message)
                token_counts["history_tokens"] += message_tokens
            
            logger.debug(f"Added {len(filtered_messages)} history messages: {token_counts['history_tokens']} tokens")
            
        except Exception as e:
            logger.warning(f"Failed to load conversation history: {e}")
        
        # 7. Build metadata
        metadata = {
            "included_memory_ids": included_memory_ids,
            "token_counts": token_counts,
            "truncated_message_ids": truncated_message_ids,
            "total_tokens": sum(token_counts.values()),
            "conversation_id": conversation_id
        }
        
        # Log audit information
        logger.info(f"Built prompt with {len(messages)} messages, "
                   f"{len(included_memory_ids)} memories, "
                   f"total tokens: {metadata['total_tokens']}")
        
        if included_memory_ids:
            logger.debug(f"Included memory IDs: {included_memory_ids}")
        
        return messages, metadata

    async def get_active_message_count(self, conversation_id: str) -> int:
        """
        Get the number of active (unsummarized) messages in a conversation.
        """
        conversation = await self.conversation_repo.get_conversation(conversation_id)
        if not conversation:
            return 0
        return await self.message_repo.count_active_messages(
            conversation_id, conversation.last_summarized_message_id
        )
    
    def _extract_summary_text(self, memory_text: str) -> str:
        """
        Extract summary text from structured memory data.
        
        Args:
            memory_text: Raw memory text (potentially JSON)
            
        Returns:
            Extracted summary text
        """
        if not memory_text:
            return ""
        
        try:
            if memory_text.startswith('{'):
                import json
                memory_data = json.loads(memory_text)
                return memory_data.get("profile", memory_data.get("summary", memory_text))
            else:
                return memory_text
        except (json.JSONDecodeError, KeyError):
            return memory_text


# Export public API
__all__ = [
    'PromptAssembler',
    'Tokenizer',
    'TokenCounter'
]
