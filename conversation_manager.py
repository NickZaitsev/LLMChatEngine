import json
import time
import logging
from typing import List, Dict, Optional, DefaultDict
from collections import defaultdict
from config import MAX_CONVERSATION_HISTORY, MAX_TOKENS, MAX_CONTEXT_TOKENS, RESERVED_TOKENS, AVAILABLE_HISTORY_TOKENS


logger = logging.getLogger(__name__)


class ConversationManager:
    def __init__(self):
        self.conversations: Dict[int, List[Dict]] = {}
        
        logger.info("Conversation Manager initialized. input=%s, output=%s, history=%s, exchanges=%s",
                    MAX_CONTEXT_TOKENS, MAX_TOKENS, AVAILABLE_HISTORY_TOKENS, MAX_CONVERSATION_HISTORY)
    
    def _get_user_key(self, user_id: int) -> str:
        return f"conversation:{user_id}"
    
    def _estimate_tokens(self, text: str) -> int:
        """Rough estimate of tokens (4 characters ≈ 1 token)"""
        return max(0, len(text) // 4)
    
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
        
        logger.debug("Add message: user_id=%s role=%s content_preview=%s", user_id, role, content[:80])
        self._add_to_memory(user_id, message)
    
    def _add_to_memory(self, user_id: int, message: Dict) -> None:
        """Add message to in-memory storage"""
        if user_id not in self.conversations:
            self.conversations[user_id] = []
            logger.debug("Created new in-memory conversation for user %s", user_id)
        
        self.conversations[user_id].append(message)
        
        # Only trim if conversation is significantly over the limit
        if len(self.conversations[user_id]) > MAX_CONVERSATION_HISTORY * 2:
            logger.debug("Trimming in-memory conversation for user %s (len=%s)", user_id, len(self.conversations[user_id]))
            self.conversations[user_id] = self._trim_conversation_to_tokens(
                self.conversations[user_id], MAX_CONTEXT_TOKENS
            )
    
    def get_conversation(self, user_id: int) -> List[Dict]:
        """Get the conversation history for a user"""
        return list(self.conversations.get(user_id, []))
    
    def clear_conversation(self, user_id: int) -> None:
        """Clear conversation history for a user"""
        if user_id in self.conversations:
            del self.conversations[user_id]
    
    def get_formatted_conversation(self, user_id: int) -> List[Dict]:
        """Get conversation formatted for AI API with token management"""
        conversation = self.get_conversation(user_id)
        logger.debug("Format conversation for user %s (raw_len=%s)", user_id, len(conversation))
        
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
                if msg_tokens > 200:
                    shortened_content = content[:600] + "..." if len(content) > 600 else content
                    shortened_tokens = self._estimate_tokens(shortened_content)
                    if current_tokens + shortened_tokens <= max_context_tokens:
                        formatted_conversation.append({
                            "role": msg.get("role", "user"),
                            "content": shortened_content
                        })
                        current_tokens += shortened_tokens
        
        logger.debug("Formatted conversation len=%s tokens_used=%s", len(formatted_conversation), current_tokens)
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