"""
Memory management package for AI girlfriend bot.

This package provides episodic memory creation, summarization, embedding, 
and semantic retrieval capabilities.
"""

from .manager import LlamaIndexMemoryManager
from .llamaindex.summarizer import LlamaIndexSummarizer

__all__ = [
    'LlamaIndexMemoryManager',
    'LlamaIndexSummarizer'
]

__version__ = '1.0.0'