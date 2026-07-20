"""Text normalization and splitting for outgoing Telegram messages."""

import re
import textwrap


def clean_ai_response(text: str) -> str:
    """
    Clean and normalize text by:
    - Stripping leading/trailing whitespace
    - Reducing multiple consecutive newlines to double newlines
    - Removing leading/trailing whitespace from each line
    """
    text = text.strip()

    # Reduce multiple consecutive newlines to double newlines
    text = re.sub(r'\n{3,}', '\n\n', text)

    # Remove leading/trailing whitespace from each line
    lines = text.split('\n')
    cleaned_lines = [line.strip() for line in lines]
    text = '\n'.join(cleaned_lines)

    # Additional cleanup for cases with remaining whitespace
    text = re.sub(r'\n{2,}\.\.\.', '\n\n', text)

    return text


def _split_ai_response(text: str) -> list:
    text = clean_ai_response(text)
    parts = text.split("\n\n")

    safe_parts = []
    for part in parts:
        chunks = textwrap.wrap(part, width=4000, break_long_words=False, break_on_hyphens=False)
        safe_parts.extend(chunks)

    return safe_parts
