"""
Memory management package for AI girlfriend bot.

This package provides episodic memory creation, summarization, embedding, 
and semantic retrieval capabilities.
"""

from .manager import MemoryManager
from .embedding import embed_texts
from .summarizer import summarize_chunk, merge_summaries, SummarizerOutput, MergeOutput

__all__ = [
    'MemoryManager',
    'embed_texts', 
    'summarize_chunk',
    'merge_summaries',
    'SummarizerOutput',
    'MergeOutput'
]

__version__ = '1.0.0'