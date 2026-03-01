"""
Memory management package for AI chat bot.

This package provides:
- Adaptive conversation chunking (token-aware, turn-based)
- Direct embedding of conversation fragments (no LLM extraction)
- Semantic retrieval with neighbor expansion
"""

from .manager import LlamaIndexMemoryManager
from .adaptive_chunker import AdaptiveChunker, ConversationChunk

__all__ = [
    'LlamaIndexMemoryManager',
    'AdaptiveChunker',
    'ConversationChunk',
]

__version__ = '2.0.0'