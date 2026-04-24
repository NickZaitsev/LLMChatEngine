"""
Adaptive token-aware conversation chunker.

Groups conversation messages into chunks based on token budget and message
count limits. Always groups messages in user+assistant pairs (turns).
No LLM calls — pure local computation.
"""

import logging
import math
from dataclasses import dataclass
from typing import List
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class ConversationChunk:
    """A chunk of conversation ready for embedding."""
    text: str                   # Formatted text block ("user: ...\nassistant: ...")
    message_ids: List[str]      # All source message IDs (for provenance)
    token_count: int            # Estimated total tokens
    chunk_index: int            # Position in the batch (0, 1, 2, ...)
    first_timestamp: datetime   # Timestamp of the earliest message
    last_timestamp: datetime    # Timestamp of the latest message


class AdaptiveChunker:
    """
    Groups conversation messages into token-aware chunks.

    Strategy:
    - Messages are paired into turns (user + assistant).
    - Turns are grouped until max_messages or target_tokens is reached.
    - Always breaks on turn boundaries — never splits a user+assistant pair.
    - A single oversized turn still gets its own chunk (never dropped).
    """

    def __init__(
        self,
        max_messages: int = 4,
        target_tokens: int = 300,
    ):
        """
        Initialize the AdaptiveChunker.

        Args:
            max_messages: Hard cap on messages per chunk (must be even for
                          complete turn pairs; rounded down to nearest even).
            target_tokens: Soft token target per chunk.  Once the running
                           token total of a chunk reaches this value, a new
                           chunk is started.
        """
        # Ensure max_messages is even (complete turns only)
        self.max_messages = max_messages if max_messages % 2 == 0 else max_messages - 1
        if self.max_messages < 2:
            self.max_messages = 2
        self.target_tokens = target_tokens

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_chunks(self, messages: list) -> List[ConversationChunk]:
        """
        Create adaptive chunks from a list of messages.

        Args:
            messages: List of Message objects (from storage) with at least
                      .role, .content, .id, .token_count, .created_at fields.

        Returns:
            List of ConversationChunk objects ready for embedding.
        """
        if not messages:
            return []

        # 1. Pair messages into turns
        turns = self._pair_into_turns(messages)
        if not turns:
            return []

        # 2. Group turns into chunks
        chunks = self._group_turns(turns)

        logger.info(
            "Created %d chunk(s) from %d turn(s) (%d messages)",
            len(chunks), len(turns), len(messages),
        )
        return chunks

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _pair_into_turns(self, messages: list) -> list:
        """
        Walk messages and pair consecutive user+assistant messages into turns.

        Orphan messages (user without a following assistant, or standalone
        assistant messages) are skipped — we only embed complete turns.

        Returns:
            List of (user_msg, assistant_msg) tuples.
        """
        turns = []
        i = 0
        while i < len(messages):
            msg = messages[i]
            if (
                msg.role == "user"
                and i + 1 < len(messages)
                and messages[i + 1].role == "assistant"
            ):
                turns.append((msg, messages[i + 1]))
                i += 2
            else:
                # Skip orphan / out-of-order messages
                i += 1
        return turns

    def _group_turns(self, turns: list) -> List[ConversationChunk]:
        """
        Group turns into chunks respecting both max_messages and
        target_tokens limits.
        """
        chunks: List[ConversationChunk] = []
        chunk_index = 0
        i = 0

        while i < len(turns):
            current_turns: list = []
            current_messages = 0
            current_tokens = 0

            while i < len(turns):
                user_msg, assistant_msg = turns[i]
                turn_messages = 2  # always a pair
                turn_tokens = self._turn_tokens(user_msg, assistant_msg)

                # Would adding this turn exceed limits?
                if current_turns and (
                    current_messages + turn_messages > self.max_messages
                    or current_tokens + turn_tokens > self.target_tokens
                ):
                    break  # Finalise current chunk, this turn starts the next

                current_turns.append((user_msg, assistant_msg))
                current_messages += turn_messages
                current_tokens += turn_tokens
                i += 1

            if current_turns:
                chunks.append(self._build_chunk(current_turns, chunk_index))
                chunk_index += 1

        return chunks

    @staticmethod
    def _turn_tokens(user_msg, assistant_msg) -> int:
        """
        Estimate the token count for a single turn.

        Uses the stored token_count when available, otherwise falls back
        to a simple character-based heuristic (~4 chars per token).
        """
        token_count = (
            (getattr(user_msg, "token_count", 0) or 0)
            + (getattr(assistant_msg, "token_count", 0) or 0)
        )
        if token_count > 0:
            return token_count
        # Fallback heuristic
        combined_len = len(user_msg.content) + len(assistant_msg.content)
        return max(1, math.ceil(combined_len / 4))

    @staticmethod
    def _build_chunk(turns: list, index: int) -> ConversationChunk:
        """Assemble a ConversationChunk from a list of (user, assistant) turns."""
        lines: List[str] = []
        message_ids: List[str] = []
        total_tokens = 0

        for user_msg, assistant_msg in turns:
            lines.append(f"user: {user_msg.content}")
            lines.append(f"assistant: {assistant_msg.content}")
            message_ids.append(str(user_msg.id))
            message_ids.append(str(assistant_msg.id))
            total_tokens += AdaptiveChunker._turn_tokens(user_msg, assistant_msg)

        return ConversationChunk(
            text="\n".join(lines),
            message_ids=message_ids,
            token_count=total_tokens,
            chunk_index=index,
            first_timestamp=turns[0][0].created_at,
            last_timestamp=turns[-1][1].created_at,
        )
