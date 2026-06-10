"""Celery tasks for book ingestion."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from app_context import get_app_context
from config import BOOKS_KEEP_SOURCE_FILES, BOOKS_STORAGE_DIR
from knowledge.parser import extract_text
from memory.tasks import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="knowledge.tasks.ingest_book")
def ingest_book(book_id: str):
    """Celery entry point for book ingestion."""
    logger.info("Starting book ingestion task for book_id: %s", book_id)
    try:
        asyncio.run(ingest_book_async(book_id))
    except Exception as exc:
        logger.error("Error in book ingestion task for %s: %s", book_id, exc, exc_info=True)
        raise


async def ingest_book_async(book_id: str) -> None:
    """Parse, chunk, embed, and mark one uploaded book."""
    app_context = await get_app_context()
    if not app_context.conversation_manager:
        raise RuntimeError("Conversation manager is not initialized")
    if not app_context.book_knowledge_manager:
        raise RuntimeError("Book knowledge manager is not available")

    book_repo = app_context.conversation_manager.storage.books
    book = await book_repo.get_book(book_id)
    if not book:
        logger.error("Book %s not found", book_id)
        return

    file_path = Path(BOOKS_STORAGE_DIR) / f"{book.id}.{book.file_format}"
    await book_repo.update_status(str(book.id), "processing")

    try:
        text = extract_text(str(file_path), book.file_format)
        chunk_count = await app_context.book_knowledge_manager.ingest_book(
            book_id=str(book.id),
            bot_id=str(book.bot_id),
            title=book.title,
            author=book.author or "",
            text=text,
        )
        await book_repo.update_status(
            str(book.id),
            "ready",
            error=None,
            chunk_count=chunk_count,
            char_count=len(text),
        )
        if not BOOKS_KEEP_SOURCE_FILES:
            _delete_source_file(file_path)
        logger.info("Finished book ingestion for %s (%d chunks)", book.id, chunk_count)
    except Exception as exc:
        await book_repo.update_status(str(book.id), "failed", error=str(exc))
        raise


def _delete_source_file(file_path: Path) -> None:
    try:
        file_path.unlink(missing_ok=True)
    except Exception as exc:
        logger.warning("Failed to delete source book file %s: %s", file_path, exc)
