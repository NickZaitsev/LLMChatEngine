"""Chunk extracted book text for embedding and retrieval."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from config import BOOK_CHUNK_OVERLAP_TOKENS, BOOK_CHUNK_TARGET_TOKENS
from core.tokens import TokenCounter


@dataclass(frozen=True)
class BookChunk:
    """A single book text chunk."""

    text: str
    chunk_index: int


def chunk_text(
    text: str,
    *,
    target_tokens: int = BOOK_CHUNK_TARGET_TOKENS,
    overlap_tokens: int = BOOK_CHUNK_OVERLAP_TOKENS,
    token_counter: TokenCounter | None = None,
) -> list[BookChunk]:
    """Split normalized book text into overlapping chunks."""
    if not text or not text.strip():
        return []
    if target_tokens < 1:
        raise ValueError("target_tokens must be positive")
    if overlap_tokens < 0:
        raise ValueError("overlap_tokens cannot be negative")
    if overlap_tokens >= target_tokens:
        raise ValueError("overlap_tokens must be less than target_tokens")

    counter = token_counter or TokenCounter()
    paragraphs = _split_paragraphs(text)
    units = _split_oversized_paragraphs(paragraphs, target_tokens, counter)
    chunk_strings = _pack_units(units, target_tokens, overlap_tokens, counter)
    return [BookChunk(text=chunk, chunk_index=index) for index, chunk in enumerate(chunk_strings)]


def _split_paragraphs(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"\n\s*\n+", text) if part.strip()]


def _split_oversized_paragraphs(
    paragraphs: Iterable[str],
    target_tokens: int,
    counter: TokenCounter,
) -> list[str]:
    units: list[str] = []
    for paragraph in paragraphs:
        if counter.count_tokens(paragraph) <= target_tokens:
            units.append(paragraph)
            continue
        units.extend(_split_sentences_to_units(paragraph, target_tokens, counter))
    return units


def _split_sentences_to_units(
    paragraph: str,
    target_tokens: int,
    counter: TokenCounter,
) -> list[str]:
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", paragraph) if part.strip()]
    if not sentences:
        return _split_by_words(paragraph, target_tokens, counter)

    units: list[str] = []
    current: list[str] = []
    for sentence in sentences:
        if counter.count_tokens(sentence) > target_tokens:
            if current:
                units.append(" ".join(current))
                current = []
            units.extend(_split_by_words(sentence, target_tokens, counter))
            continue

        candidate = " ".join([*current, sentence]).strip()
        if current and counter.count_tokens(candidate) > target_tokens:
            units.append(" ".join(current))
            current = [sentence]
        else:
            current.append(sentence)

    if current:
        units.append(" ".join(current))
    return units


def _split_by_words(text: str, target_tokens: int, counter: TokenCounter) -> list[str]:
    units: list[str] = []
    current: list[str] = []
    for word in text.split():
        candidate = " ".join([*current, word]).strip()
        if current and counter.count_tokens(candidate) > target_tokens:
            units.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        units.append(" ".join(current))
    return units


def _pack_units(
    units: list[str],
    target_tokens: int,
    overlap_tokens: int,
    counter: TokenCounter,
) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []

    for unit in units:
        candidate = _join_units([*current, unit])
        if current and counter.count_tokens(candidate) > target_tokens:
            chunk = _join_units(current)
            chunks.append(chunk)
            current = _overlap_units(current, overlap_tokens, counter)
        current.append(unit)

    if current:
        chunk = _join_units(current)
        if not chunks or chunk != chunks[-1]:
            chunks.append(chunk)
    return chunks


def _overlap_units(units: list[str], overlap_tokens: int, counter: TokenCounter) -> list[str]:
    if overlap_tokens == 0:
        return []

    overlap: list[str] = []
    for unit in reversed(units):
        candidate = [unit, *overlap]
        if overlap and counter.count_tokens(_join_units(candidate)) > overlap_tokens:
            break
        overlap = candidate
    return overlap


def _join_units(units: list[str]) -> str:
    return "\n\n".join(unit.strip() for unit in units if unit.strip())
