"""
Memory Chunker for extracting structured facts from conversation chunks.

This module provides the `MemoryChunker` class that takes a group of messages,
sends them to an LLM with a structured extraction prompt, and parses the output
into individual facts with categories.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from ai_handler import AIHandler

logger = logging.getLogger(__name__)


@dataclass
class MemoryFact:
    """A single distilled fact extracted from conversation."""
    fact: str
    category: str  # preference, personal_info, event, opinion, relationship, goal
    created_at: datetime = field(default_factory=datetime.utcnow)
    source_message_ids: List[str] = field(default_factory=list)


class MemoryChunker:
    """
    Extracts structured memory facts from conversation message chunks
    using an LLM.
    """

    VALID_CATEGORIES = {
        "preference", "personal_info", "event",
        "opinion", "relationship", "goal"
    }

    def __init__(self, ai_handler: AIHandler, extraction_prompt: str, max_facts: int = 5):
        """
        Initialize the MemoryChunker.

        Args:
            ai_handler: The AI handler for LLM requests.
            extraction_prompt: The prompt template with {text} placeholder.
            max_facts: Maximum number of facts to extract per chunk.
        """
        self._ai_handler = ai_handler
        self._extraction_prompt = extraction_prompt
        self._max_facts = max_facts

    async def extract_facts(self, messages: list) -> List[MemoryFact]:
        """
        Extract structured facts from a list of messages.

        Args:
            messages: List of message objects with .role and .content attributes.

        Returns:
            List of MemoryFact instances extracted from the conversation.
        """
        if not messages:
            return []

        # Format messages into text block
        text_block = "\n".join(
            f"{msg.role}: {msg.content}" for msg in messages
        )

        # Collect message IDs for provenance tracking
        message_ids = [str(msg.id) for msg in messages if hasattr(msg, 'id')]

        # Build the extraction prompt
        prompt = self._extraction_prompt.format(text=text_block)

        try:
            # Call LLM for fact extraction
            raw_response = await self._ai_handler.get_response(prompt)
            facts = self._parse_response(raw_response, message_ids)
            return facts[:self._max_facts]
        except Exception as e:
            logger.error(f"Failed to extract facts from conversation chunk: {e}", exc_info=True)
            return []

    def _parse_response(self, raw_response: str, message_ids: List[str]) -> List[MemoryFact]:
        """
        Parse the LLM response into MemoryFact objects.

        Args:
            raw_response: Raw LLM text output (expected JSON array).
            message_ids: Source message IDs for provenance.

        Returns:
            List of validated MemoryFact instances.
        """
        # Try to extract JSON from the response (handle markdown code blocks)
        cleaned = raw_response.strip()
        if cleaned.startswith("```"):
            # Remove markdown code block wrapping
            lines = cleaned.split("\n")
            # Remove first and last lines (``` markers)
            lines = [l for l in lines if not l.strip().startswith("```")]
            cleaned = "\n".join(lines).strip()

        # Find the JSON array in the response
        start_idx = cleaned.find("[")
        end_idx = cleaned.rfind("]")
        if start_idx == -1 or end_idx == -1:
            logger.warning(f"No JSON array found in LLM response: {cleaned[:200]}")
            return []

        json_str = cleaned[start_idx:end_idx + 1]

        try:
            parsed = json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON from LLM response: {e}")
            return []

        if not isinstance(parsed, list):
            logger.warning(f"Expected JSON array, got {type(parsed)}")
            return []

        facts = []
        for item in parsed:
            if not isinstance(item, dict):
                continue

            fact_text = item.get("fact", "").strip()
            category = item.get("category", "").strip().lower()

            if not fact_text:
                continue

            # Normalize category
            if category not in self.VALID_CATEGORIES:
                category = "personal_info"  # Default fallback

            facts.append(MemoryFact(
                fact=fact_text,
                category=category,
                source_message_ids=message_ids
            ))

        logger.info(f"Extracted {len(facts)} facts from conversation chunk")
        return facts
