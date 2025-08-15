import time
import logging
from typing import List, Dict

from config import MAX_CONVERSATION_HISTORY, MAX_TOKENS, MAX_CONTEXT_TOKENS, RESERVED_TOKENS, AVAILABLE_HISTORY_TOKENS

# Constants
TOKEN_ESTIMATION_RATIO = 3.0  # More accurate: ~3 characters per token
TOKEN_BUFFER_MULTIPLIER = 1.1  # Add 10% buffer for punctuation and special tokens

logger = logging.getLogger(__name__)


class ConversationManager:
    def __init__(self):
        self.conversations: Dict[int, List[Dict]] = {}
        logger.info("Conversation Manager initialized. Context: %d, Available: %d, History: %d",
                   MAX_CONTEXT_TOKENS, AVAILABLE_HISTORY_TOKENS, MAX_CONVERSATION_HISTORY)
    
    def _get_user_key(self, user_id: int) -> str:
        return f"conversation:{user_id}"
    
    def _estimate_tokens(self, text: str) -> int:
        """Estimate tokens using more accurate approximation (3 chars ≈ 1 token for mixed content)"""
        if not text:
            return 0
        # More accurate: ~3 characters per token for mixed content (English + emojis)
        # Add small buffer for punctuation and special tokens
        return max(1, int(len(text) / 3.0 * 1.1))
    
    def _get_conversation_tokens(self, conversation: List[Dict]) -> int:
        """Calculate total tokens in conversation"""
        total_tokens = 0
        for msg in conversation:
            total_tokens += self._estimate_tokens(msg.get("content", ""))
        return total_tokens
    
    def _trim_conversation_to_tokens(self, conversation: List[Dict], max_tokens: int) -> List[Dict]:
        """Trim conversation to fit within token limit while preserving chronological order"""
        if not conversation:
            return conversation
        
        available_tokens = AVAILABLE_HISTORY_TOKENS
        trimmed_conversation: List[Dict] = []
        current_tokens = 0
        
        for msg in conversation:
            content = msg.get("content", "")
            msg_tokens = self._estimate_tokens(content)
            
            if current_tokens + msg_tokens <= available_tokens:
                trimmed_conversation.append(msg)
                current_tokens += msg_tokens
            else:
                if msg_tokens > 100:
                    shortened_content = content[:400] + "..." if len(content) > 400 else content
                    shortened_tokens = self._estimate_tokens(shortened_content)
                    if current_tokens + shortened_tokens <= available_tokens:
                        shortened_msg = msg.copy()
                        shortened_msg["content"] = shortened_content
                        trimmed_conversation.append(shortened_msg)
                        current_tokens += shortened_tokens
        
        return trimmed_conversation
    
    def add_message(self, user_id: int, role: str, content: str) -> None:
        """Add a message to the user's conversation history"""
        message = {
            "role": role,
            "content": content,
            "timestamp": time.time()
        }
        
        logger.info("Adding message: user=%s, role=%s, length=%d chars", user_id, role, len(content))
        self._add_to_memory(user_id, message)
    
    def _add_to_memory(self, user_id: int, message: Dict) -> None:
        """Add message to in-memory storage"""
        if user_id not in self.conversations:
            self.conversations[user_id] = []
            logger.info("Created new conversation for user %s", user_id)
        
        self.conversations[user_id].append(message)
        current_length = len(self.conversations[user_id])
        
        logger.info("User %s now has %d messages", user_id, current_length)
        
        # Only trim if conversation is significantly over the limit
        if current_length > MAX_CONVERSATION_HISTORY * 2:
            logger.info("Trimming conversation for user %s (%d messages)", user_id, current_length)
            self.conversations[user_id] = self._trim_conversation_to_tokens(
                self.conversations[user_id], MAX_CONTEXT_TOKENS
            )
            logger.info("After trimming: user %s has %d messages", user_id, len(self.conversations[user_id]))
    
    def get_conversation(self, user_id: int) -> List[Dict]:
        """Get the conversation history for a user"""
        return list(self.conversations.get(user_id, []))
    
    def clear_conversation(self, user_id: int) -> None:
        """Clear conversation history for a user"""
        if user_id in self.conversations:
            messages_count = len(self.conversations[user_id])
            del self.conversations[user_id]
            logger.info("Cleared conversation for user %s (%d messages)", user_id, messages_count)
        else:
            logger.info("No conversation to clear for user %s", user_id)
    
    def get_formatted_conversation(self, user_id: int) -> List[Dict]:
        """Get conversation formatted for AI API with token management"""
        conversation = self.get_conversation(user_id)
        logger.info("Formatting conversation for user %s (%d messages)", user_id, len(conversation))
        
        max_context_tokens = AVAILABLE_HISTORY_TOKENS
        formatted_conversation: List[Dict] = []
        current_tokens = 0
        
        for msg in conversation:
            content = msg.get("content", "")
            msg_tokens = self._estimate_tokens(content)
            
            if current_tokens + msg_tokens <= max_context_tokens:
                formatted_conversation.append({
                    "role": msg.get("role", "user"),
                    "content": content
                })
                current_tokens += msg_tokens
            else:
                # Try to shorten long messages to fit
                if msg_tokens > 200:
                    shortened_content = content[:600] + "..." if len(content) > 600 else content
                    shortened_tokens = self._estimate_tokens(shortened_content)
                    if current_tokens + shortened_tokens <= max_context_tokens:
                        formatted_conversation.append({
                            "role": msg.get("role", "user"),
                            "content": shortened_content
                        })
                        current_tokens += shortened_tokens
        
        logger.info("Formatted %d messages using %d tokens (max: %d)",
                   len(formatted_conversation), current_tokens, max_context_tokens)
        return formatted_conversation
    
    def get_user_stats(self, user_id: int) -> Dict:
        """Get statistics about user's conversation"""
        conversation = self.get_conversation(user_id)
        total_tokens = self._get_conversation_tokens(conversation)
        
        return {
            "total_messages": len(conversation),
            "user_messages": len([msg for msg in conversation if msg.get("role") == "user"]),
            "bot_messages": len([msg for msg in conversation if msg.get("role") == "assistant"]),
            "estimated_tokens": total_tokens,
            "max_context_tokens": MAX_CONTEXT_TOKENS,
            "reserved_tokens": RESERVED_TOKENS,
            "available_history_tokens": AVAILABLE_HISTORY_TOKENS,
            "available_tokens": max(0, AVAILABLE_HISTORY_TOKENS - total_tokens),
            "token_usage_percent": (total_tokens / AVAILABLE_HISTORY_TOKENS) * 100 if AVAILABLE_HISTORY_TOKENS else 0,
            "last_message": conversation[-1].get("timestamp") if conversation else None
        }
    
    def get_conversation_summary(self, user_id: int) -> str:
        """Get a summary of the conversation for context preservation"""
        conversation = self.get_conversation(user_id)
        if not conversation:
            return "No conversation history."
        
        user_messages = [msg.get("content", "") for msg in conversation if msg.get("role") == "user"]
        if len(user_messages) <= 3:
            return "Conversation just started."
        
        summary_parts = []
        for i, msg in enumerate(user_messages[-5:], 1):
            summary_parts.append(f"{i}. {msg[:80]}...")
        
        return "Recent topics: " + " | ".join(summary_parts)
    
    def debug_conversation_state(self, user_id: int) -> Dict:
        """Debug method to show current conversation state"""
        conversation = self.get_conversation(user_id)
        formatted_conversation = self.get_formatted_conversation(user_id)
        
        return {
            "raw_conversation_length": len(conversation),
            "formatted_conversation_length": len(formatted_conversation),
            "raw_tokens": self._get_conversation_tokens(conversation),
            "formatted_tokens": self._get_conversation_tokens(formatted_conversation),
            "max_context_tokens": MAX_CONTEXT_TOKENS,
            "available_history_tokens": AVAILABLE_HISTORY_TOKENS,
            "last_messages": [
                {
                    "role": msg.get("role", "user"),
                    "content": (msg.get("content", "")[:100] + "...") if len(msg.get("content", "")) > 100 else msg.get("content", ""),
                    "timestamp": msg.get("timestamp", "N/A")
                }
                for msg in conversation[-5:]
            ] if conversation else [],
            "formatted_messages": [
                {
                    "role": msg.get("role", "user"),
                    "content": (msg.get("content", "")[:100] + "...") if len(msg.get("content", "")) > 100 else msg.get("content", "")
                }
                for msg in formatted_conversation[-5:]
            ] if formatted_conversation else []
        }
    
    # Async versions for compatibility with PostgresConversationManager
    async def get_conversation_async(self, user_id: int) -> List[Dict]:
        """Async version of get_conversation for compatibility."""
        return self.get_conversation(user_id)
    
    async def get_formatted_conversation_async(self, user_id: int) -> List[Dict]:
        """Async version of get_formatted_conversation for compatibility."""
        return self.get_formatted_conversation(user_id)
    
    async def get_user_stats_async(self, user_id: int) -> Dict:
        """Async version of get_user_stats for compatibility."""
        return self.get_user_stats(user_id)
    
    async def debug_conversation_state_async(self, user_id: int) -> Dict:
        """Async version of debug_conversation_state for compatibility."""
        return self.debug_conversation_state(user_id)
    
    async def clear_conversation_async(self, user_id: int) -> None:
        """Async version of clear_conversation for compatibility."""
        self.clear_conversation(user_id)