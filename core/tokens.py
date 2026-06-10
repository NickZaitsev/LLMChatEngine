"""Shared token counting helpers."""

import logging
import math
from typing import List, Optional, Protocol

logger = logging.getLogger(__name__)


class Tokenizer(Protocol):
    """Protocol for tokenizer implementations."""

    def encode(self, text: str) -> List[int]:
        """Encode text to tokens."""
        ...

    def count_tokens(self, text: str) -> int:
        """Count tokens in text."""
        ...


class TokenCounter:
    """Count tokens with tiktoken when available and a stable fallback."""

    def __init__(self, tokenizer: Optional[Tokenizer] = None, auto_tiktoken: bool = True):
        self.tokenizer = tokenizer

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
            except Exception as e:
                logger.debug("tiktoken unavailable, using heuristic token counting: %s", e)

    def count_tokens(self, text: str) -> int:
        """Count tokens in text."""
        if not text:
            return 0

        if self.tokenizer:
            try:
                return self.tokenizer.count_tokens(text)
            except Exception as e:
                logger.warning("Tokenizer failed, using fallback: %s", e)

        return max(1, math.ceil(len(text) / 4))

    def estimate_tokens(self, text: str) -> int:
        """Compatibility alias for repository callers."""
        return self.count_tokens(text)
