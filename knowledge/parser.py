"""Extract normalized text from supported book file formats."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Callable
from xml.etree import ElementTree


class BookParseError(ValueError):
    """Raised when a book file cannot be parsed into usable text."""


def extract_text(file_path: str, file_format: str) -> str:
    """Extract normalized text from a supported book file."""
    path = Path(file_path)
    fmt = file_format.lower().lstrip(".")
    extractors: dict[str, Callable[[Path], str]] = {
        "txt": _extract_txt,
        "pdf": _extract_pdf,
        "epub": _extract_epub,
        "fb2": _extract_fb2,
    }

    extractor = extractors.get(fmt)
    if extractor is None:
        raise BookParseError(f"Unsupported book format: {file_format}")
    if not path.exists():
        raise BookParseError(f"Book file does not exist: {file_path}")

    try:
        text = extractor(path)
    except BookParseError:
        raise
    except Exception as exc:
        raise BookParseError(f"Failed to parse {fmt} book: {exc}") from exc

    normalized = _normalize_text(text)
    if not normalized:
        raise BookParseError(f"No text extracted from {file_path}")
    return normalized


def _extract_txt(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8", "cp1251"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue

    try:
        from charset_normalizer import from_bytes
    except ImportError as exc:
        raise BookParseError(
            "Unable to detect text encoding. Install charset-normalizer."
        ) from exc

    match = from_bytes(raw).best()
    if match is None:
        raise BookParseError("Unable to detect text encoding")
    return str(match)


def _extract_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise BookParseError("PDF parsing requires pypdf") from exc

    reader = PdfReader(str(path))
    return "\n\n".join(page.extract_text() or "" for page in reader.pages)


def _extract_epub(path: Path) -> str:
    try:
        from bs4 import BeautifulSoup
        from ebooklib import ITEM_DOCUMENT, epub
    except ImportError as exc:
        raise BookParseError("EPUB parsing requires ebooklib and beautifulsoup4") from exc

    book = epub.read_epub(str(path))
    parts: list[str] = []
    for item in book.get_items_of_type(ITEM_DOCUMENT):
        soup = BeautifulSoup(item.get_content(), "html.parser")
        parts.append(soup.get_text("\n"))
    return "\n\n".join(parts)


def _extract_fb2(path: Path) -> str:
    root = ElementTree.parse(path).getroot()
    parts: list[str] = []
    for body in root.iter():
        if _local_name(body.tag) != "body":
            continue
        for element in body.iter():
            if element.text:
                parts.append(element.text)
            if element.tail:
                parts.append(element.tail)
    return "\n".join(parts)


def _normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    paragraphs = []
    for paragraph in re.split(r"\n\s*\n+", text):
        cleaned = re.sub(r"[ \t\f\v]+", " ", paragraph)
        cleaned = re.sub(r" *\n *", " ", cleaned).strip()
        if cleaned:
            paragraphs.append(cleaned)
    return "\n\n".join(paragraphs)


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]
