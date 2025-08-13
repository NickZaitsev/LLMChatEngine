"""
Summarization utilities for memory management.

This module provides abstraction for text summarization with support for both
LLM-based and local HuggingFace model-based summarization.
"""

import asyncio
import json
import logging
from typing import List, Dict, Any, Optional, Callable, Awaitable
from dataclasses import dataclass, asdict
from concurrent.futures import ThreadPoolExecutor
import threading
import re

logger = logging.getLogger(__name__)

# Global model cache and executor
_model_cache: Dict[str, Any] = {}
_model_lock = threading.Lock()
_executor: Optional[ThreadPoolExecutor] = None


@dataclass
class SummarizerOutput:
    """
    Output from chunk summarization.
    
    Attributes:
        summary_text: The generated summary text
        key_facts: List of key facts extracted from the chunk
        importance: Importance score from 0.0 to 1.0
        source_message_ids: List of source message IDs that contributed to this summary
        lang: Detected/specified language code
    """
    summary_text: str
    key_facts: List[str]
    importance: float
    source_message_ids: List[str]
    lang: str = "en"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SummarizerOutput':
        """Create from dictionary."""
        return cls(**data)


@dataclass  
class MergeOutput:
    """
    Output from merging summaries into an existing profile.
    
    Attributes:
        updated_profile: The updated/merged profile text
        change_log: List of changes made during merging
        lang: Language code of the merged content
    """
    updated_profile: str
    change_log: List[Dict[str, Any]]
    lang: str = "en"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MergeOutput':
        """Create from dictionary."""
        return cls(**data)


def _get_executor() -> ThreadPoolExecutor:
    """Get or create thread executor for CPU-bound summarization tasks."""
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="summarizer")
    return _executor


def _load_local_model(model_name: str) -> Any:
    """
    Load a HuggingFace model for local summarization.
    
    Args:
        model_name: Name/path of the HuggingFace model
        
    Returns:
        Loaded model and tokenizer tuple
    """
    with _model_lock:
        if model_name not in _model_cache:
            try:
                from transformers import pipeline
                logger.info(f"Loading local summarization model: {model_name}")
                
                # Use summarization pipeline for ease of use
                summarizer = pipeline(
                    "summarization",
                    model=model_name,
                    tokenizer=model_name,
                    device=-1,  # Use CPU
                    framework="pt"
                )
                
                _model_cache[model_name] = summarizer
                logger.info(f"Successfully loaded model: {model_name}")
                
            except ImportError:
                raise ImportError(
                    "transformers is required for local summarization. "
                    "Install it with: pip install transformers torch"
                )
            except Exception as e:
                logger.error(f"Failed to load local model {model_name}: {e}")
                raise
        
        return _model_cache[model_name]


def _extract_key_facts(text: str, max_facts: int = 5) -> List[str]:
    """
    Extract key facts from text using simple heuristics.
    
    Args:
        text: Input text to extract facts from
        max_facts: Maximum number of facts to extract
        
    Returns:
        List of key facts
    """
    if not text or not text.strip():
        return []
    
    # Split into sentences
    sentences = re.split(r'[.!?]+', text)
    sentences = [s.strip() for s in sentences if s.strip()]
    
    # Simple scoring: prioritize sentences with specific patterns
    scored_sentences = []
    
    for sentence in sentences:
        score = 0
        
        # Boost sentences with numbers, names, dates
        if re.search(r'\b\d+\b', sentence):
            score += 1
        if re.search(r'\b[A-Z][a-z]+\b', sentence):
            score += 1  
        if re.search(r'\b(said|told|mentioned|discussed|decided|agreed)\b', sentence, re.IGNORECASE):
            score += 2
        
        # Length scoring - prefer moderate length sentences
        if 20 <= len(sentence) <= 200:
            score += 1
        
        scored_sentences.append((score, sentence))
    
    # Sort by score and take top facts
    scored_sentences.sort(key=lambda x: x[0], reverse=True)
    
    return [sent for _, sent in scored_sentences[:max_facts]]


def _estimate_importance(text: str) -> float:
    """
    Estimate importance of a text chunk using simple heuristics.
    
    Args:
        text: Text to analyze
        
    Returns:
        Importance score from 0.0 to 1.0
    """
    if not text or not text.strip():
        return 0.0
    
    score = 0.5  # Base score
    
    # Content indicators
    if re.search(r'\b(important|critical|urgent|significant|decision|problem)\b', text, re.IGNORECASE):
        score += 0.2
    
    # Emotional indicators
    if re.search(r'\b(love|hate|angry|sad|happy|excited|worried|concerned)\b', text, re.IGNORECASE):
        score += 0.15
    
    # Question indicators
    if '?' in text:
        score += 0.1
    
    # Length bonus for substantive content
    if len(text) > 500:
        score += 0.1
    
    # Personal information indicators
    if re.search(r'\b(I am|my name|I work|I live|I like|I don\'t like)\b', text, re.IGNORECASE):
        score += 0.1
    
    return min(1.0, max(0.0, score))


def _detect_language(text: str) -> str:
    """
    Simple language detection using basic heuristics.
    
    Args:
        text: Text to analyze
        
    Returns:
        Detected language code (defaults to 'en')
    """
    # This is a very simple implementation
    # In production, you might want to use a proper language detection library
    
    if not text:
        return "en"
    
    # Count common words in different languages
    english_words = ['the', 'and', 'is', 'in', 'to', 'of', 'a', 'that', 'it', 'with']
    spanish_words = ['el', 'la', 'de', 'que', 'y', 'es', 'en', 'un', 'se', 'no']
    french_words = ['le', 'de', 'et', 'à', 'un', 'il', 'être', 'et', 'en', 'avoir']
    
    text_lower = text.lower()
    
    en_count = sum(1 for word in english_words if f' {word} ' in f' {text_lower} ')
    es_count = sum(1 for word in spanish_words if f' {word} ' in f' {text_lower} ')
    fr_count = sum(1 for word in french_words if f' {word} ' in f' {text_lower} ')
    
    if es_count > en_count and es_count > fr_count:
        return "es"
    elif fr_count > en_count and fr_count > es_count:
        return "fr"
    else:
        return "en"


async def _llm_summarize_chunk(
    text: str,
    llm_func: Callable[[str, str], Awaitable[str]],
    source_message_ids: List[str]
) -> SummarizerOutput:
    """
    Summarize text chunk using LLM function.
    
    Args:
        text: Text to summarize
        llm_func: Async function that takes (text, mode) and returns summary
        source_message_ids: List of source message IDs
        
    Returns:
        SummarizerOutput with structured summary data
    """
    if not text or not text.strip():
        return SummarizerOutput(
            summary_text="",
            key_facts=[],
            importance=0.0,
            source_message_ids=source_message_ids,
            lang="en"
        )
    
    # Create detailed prompt for structured output
    prompt = f"""
Please analyze the following conversation and provide a structured summary in JSON format:

Conversation:
{text}

Please respond with a JSON object containing:
{{
  "summary": "A concise summary of the key points discussed",
  "key_facts": ["fact1", "fact2", "fact3"],
  "importance": 0.8,
  "language": "en"
}}

The importance should be a number between 0.0 and 1.0 representing how significant this conversation segment is.
Key facts should be specific, actionable pieces of information.
"""
    
    try:
        # Call the LLM function
        llm_response = await llm_func(prompt, "summarize")
        
        # Try to parse JSON response
        try:
            # Extract JSON from response if it's wrapped in other text
            json_match = re.search(r'\{[^{}]*\}', llm_response, re.DOTALL)
            if json_match:
                response_data = json.loads(json_match.group())
            else:
                response_data = json.loads(llm_response)
            
            return SummarizerOutput(
                summary_text=response_data.get("summary", llm_response[:500]),
                key_facts=response_data.get("key_facts", []),
                importance=float(response_data.get("importance", 0.5)),
                source_message_ids=source_message_ids,
                lang=response_data.get("language", _detect_language(text))
            )
            
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning(f"Failed to parse LLM JSON response, using fallback: {e}")
            
            # Fallback to using the raw response as summary
            return SummarizerOutput(
                summary_text=llm_response[:500] if llm_response else text[:200],
                key_facts=_extract_key_facts(text),
                importance=_estimate_importance(text),
                source_message_ids=source_message_ids,
                lang=_detect_language(text)
            )
            
    except Exception as e:
        logger.error(f"LLM summarization failed: {e}")
        
        # Fallback to local processing
        return SummarizerOutput(
            summary_text=text[:200] + "..." if len(text) > 200 else text,
            key_facts=_extract_key_facts(text),
            importance=_estimate_importance(text),
            source_message_ids=source_message_ids,
            lang=_detect_language(text)
        )


def _local_summarize_chunk(
    text: str,
    model_name: str,
    source_message_ids: List[str]
) -> SummarizerOutput:
    """
    Summarize text chunk using local HuggingFace model.
    
    Args:
        text: Text to summarize
        model_name: Name of the HuggingFace model to use
        source_message_ids: List of source message IDs
        
    Returns:
        SummarizerOutput with structured summary data
    """
    if not text or not text.strip():
        return SummarizerOutput(
            summary_text="",
            key_facts=[],
            importance=0.0,
            source_message_ids=source_message_ids,
            lang="en"
        )
    
    try:
        summarizer = _load_local_model(model_name)
        
        # Truncate text if too long for the model
        max_length = min(1024, len(text))
        input_text = text[:max_length]
        
        # Generate summary
        result = summarizer(
            input_text,
            max_length=min(150, len(input_text) // 4),
            min_length=30,
            do_sample=False
        )
        
        summary = result[0]['summary_text'] if result else text[:200]
        
        return SummarizerOutput(
            summary_text=summary,
            key_facts=_extract_key_facts(text),
            importance=_estimate_importance(text),
            source_message_ids=source_message_ids,
            lang=_detect_language(text)
        )
        
    except Exception as e:
        logger.error(f"Local summarization failed: {e}")
        
        # Fallback to simple truncation
        return SummarizerOutput(
            summary_text=text[:200] + "..." if len(text) > 200 else text,
            key_facts=_extract_key_facts(text),
            importance=_estimate_importance(text),
            source_message_ids=source_message_ids,
            lang=_detect_language(text)
        )


class Summarizer:
    """
    Summarization abstraction supporting both LLM and local modes.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize summarizer with configuration.
        
        Args:
            config: Configuration dictionary containing:
                - mode: "llm" or "local"
                - llm_summarize: async function for LLM mode (if mode="llm")
                - local_model: model name for local mode (if mode="local")
        """
        self.config = config
        self.mode = config.get("mode", "llm")
        
        if self.mode == "llm":
            self.llm_func = config.get("llm_summarize")
            if not self.llm_func:
                raise ValueError("llm_summarize function required for LLM mode")
        elif self.mode == "local":
            self.local_model = config.get("local_model", "facebook/bart-large-cnn")
        else:
            raise ValueError(f"Invalid summarization mode: {self.mode}")
    
    async def summarize_chunk(
        self, 
        text_chunk: str, 
        source_message_ids: Optional[List[str]] = None
    ) -> SummarizerOutput:
        """
        Summarize a text chunk.
        
        Args:
            text_chunk: Text to summarize
            source_message_ids: Optional list of source message IDs
            
        Returns:
            SummarizerOutput with structured summary data
        """
        if source_message_ids is None:
            source_message_ids = []
        
        if self.mode == "llm":
            return await _llm_summarize_chunk(text_chunk, self.llm_func, source_message_ids)
        
        elif self.mode == "local":
            executor = _get_executor()
            return await asyncio.get_event_loop().run_in_executor(
                executor, _local_summarize_chunk, text_chunk, self.local_model, source_message_ids
            )
        
        else:
            raise ValueError(f"Invalid summarization mode: {self.mode}")
    
    async def merge_summaries(
        self, 
        existing_profile: str, 
        new_summaries: List[SummarizerOutput]
    ) -> MergeOutput:
        """
        Merge new summaries into an existing profile.
        
        Args:
            existing_profile: Existing profile text
            new_summaries: List of new SummarizerOutput objects to merge
            
        Returns:
            MergeOutput with updated profile and change log
        """
        if not new_summaries:
            return MergeOutput(
                updated_profile=existing_profile,
                change_log=[],
                lang="en"
            )
        
        change_log = []
        
        # Combine all new summary content
        new_content = []
        combined_facts = []
        total_importance = 0.0
        languages = []
        
        for summary in new_summaries:
            if summary.summary_text:
                new_content.append(summary.summary_text)
                combined_facts.extend(summary.key_facts)
                total_importance += summary.importance
                languages.append(summary.lang)
                
                change_log.append({
                    "action": "added_summary",
                    "content": summary.summary_text[:100],
                    "importance": summary.importance,
                    "source_messages": summary.source_message_ids
                })
        
        # Determine primary language
        primary_lang = max(set(languages), key=languages.count) if languages else "en"
        
        if self.mode == "llm" and new_content:
            # Use LLM to merge intelligently
            merge_prompt = f"""
Please merge the following conversation profile with new information:

Existing Profile:
{existing_profile}

New Information:
{chr(10).join(new_content)}

Please provide an updated profile that incorporates the new information while maintaining continuity with existing content. Focus on:
1. Updating facts that have changed
2. Adding new important information
3. Maintaining personality traits and preferences
4. Keeping the profile concise but comprehensive

Respond with just the updated profile text.
"""
            
            try:
                updated_profile = await self.llm_func(merge_prompt, "merge")
                
                change_log.append({
                    "action": "llm_merge",
                    "details": f"Merged {len(new_summaries)} summaries using LLM",
                    "avg_importance": total_importance / len(new_summaries)
                })
                
            except Exception as e:
                logger.error(f"LLM merge failed, using simple concatenation: {e}")
                updated_profile = self._simple_merge(existing_profile, new_content)
                
                change_log.append({
                    "action": "fallback_merge", 
                    "error": str(e),
                    "details": "Used simple concatenation due to LLM failure"
                })
        else:
            # Simple merge by concatenation
            updated_profile = self._simple_merge(existing_profile, new_content)
            
            change_log.append({
                "action": "simple_merge",
                "details": f"Concatenated {len(new_summaries)} summaries"
            })
        
        return MergeOutput(
            updated_profile=updated_profile,
            change_log=change_log,
            lang=primary_lang
        )
    
    def _simple_merge(self, existing_profile: str, new_content: List[str]) -> str:
        """
        Simple merge by concatenation with deduplication.
        
        Args:
            existing_profile: Existing profile text
            new_content: List of new content to add
            
        Returns:
            Merged profile text
        """
        if not new_content:
            return existing_profile
        
        # Start with existing profile
        result = existing_profile.strip() if existing_profile else ""
        
        # Add new content, avoiding obvious duplicates
        for content in new_content:
            content = content.strip()
            if content and content not in result:
                if result:
                    result += "\n\n" + content
                else:
                    result = content
        
        return result


# Convenience functions for backward compatibility
_default_summarizer = None

def _get_default_summarizer() -> Summarizer:
    """Get default summarizer instance."""
    global _default_summarizer
    if _default_summarizer is None:
        # Default to a local summarizer
        config = {
            "mode": "local",
            "local_model": "facebook/bart-large-cnn"
        }
        _default_summarizer = Summarizer(config)
    return _default_summarizer


async def summarize_chunk(text_chunk: str, source_message_ids: Optional[List[str]] = None) -> SummarizerOutput:
    """
    Convenience function to summarize a text chunk using default settings.
    
    Args:
        text_chunk: Text to summarize
        source_message_ids: Optional list of source message IDs
        
    Returns:
        SummarizerOutput with structured summary data
    """
    summarizer = _get_default_summarizer()
    return await summarizer.summarize_chunk(text_chunk, source_message_ids)


async def merge_summaries(existing_profile: str, new_summaries: List[SummarizerOutput]) -> MergeOutput:
    """
    Convenience function to merge summaries using default settings.
    
    Args:
        existing_profile: Existing profile text
        new_summaries: List of new SummarizerOutput objects to merge
        
    Returns:
        MergeOutput with updated profile and change log
    """
    summarizer = _get_default_summarizer()
    return await summarizer.merge_summaries(existing_profile, new_summaries)


def cleanup_models():
    """Clear model cache and clean up resources."""
    global _model_cache, _executor, _default_summarizer
    
    with _model_lock:
        _model_cache.clear()
    
    if _executor:
        _executor.shutdown(wait=True)
        _executor = None
    
    _default_summarizer = None
    
    logger.info("Cleaned up summarization models and resources")


# Export public API
__all__ = [
    'SummarizerOutput',
    'MergeOutput', 
    'Summarizer',
    'summarize_chunk',
    'merge_summaries',
    'cleanup_models'
]