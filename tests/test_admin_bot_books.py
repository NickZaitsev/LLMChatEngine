from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from telegram.ext import ConversationHandler

from admin_bot import AdminBot, WAITING_BOOK_FILE, WAITING_BOOK_META


class FakeTelegramFile:
    def __init__(self, content: bytes):
        self.content = content

    async def download_to_drive(self, custom_path: str):
        with open(custom_path, "wb") as handle:
            handle.write(self.content)


def make_update(file_name="book.txt", file_size=12):
    update = MagicMock()
    update.effective_user.id = 1
    update.effective_chat.id = 100
    update.message.reply_text = AsyncMock()
    update.message.document = SimpleNamespace(
        file_name=file_name,
        file_size=file_size,
        file_id="file-1",
    )
    return update


def make_admin(tmp_path):
    admin = AdminBot("token", [1], "postgresql://u:p@h:5432/db")
    admin.storage = MagicMock()
    admin.storage.bots = MagicMock()
    admin.storage.books = MagicMock()
    return admin


@pytest.mark.asyncio
async def test_addbook_rejects_bad_extension(tmp_path, monkeypatch):
    admin = make_admin(tmp_path)
    update = make_update("book.docx")
    admin._pending_bot_data[admin._session_key(update)] = {"bot_id": str(uuid4())}
    context = MagicMock()

    state = await admin.addbook_file(update, context)

    assert state == WAITING_BOOK_FILE
    update.message.reply_text.assert_awaited_once_with(
        "❌ Unsupported file type. Send .txt, .pdf, .epub, or .fb2."
    )
    admin.storage.books.create_book.assert_not_called()


@pytest.mark.asyncio
async def test_addbook_rejects_oversized_file(tmp_path):
    admin = make_admin(tmp_path)
    update = make_update("book.txt", file_size=21 * 1024 * 1024)
    admin._pending_bot_data[admin._session_key(update)] = {"bot_id": str(uuid4())}
    context = MagicMock()

    state = await admin.addbook_file(update, context)

    assert state == WAITING_BOOK_FILE
    update.message.reply_text.assert_awaited_once_with(
        "❌ File is too large. Telegram book uploads are limited to 20 MB."
    )
    admin.storage.books.create_book.assert_not_called()


@pytest.mark.asyncio
async def test_addbook_happy_path_creates_book_and_enqueues(tmp_path, monkeypatch):
    bot_id = uuid4()
    book_id = uuid4()
    admin = make_admin(tmp_path)
    update = make_update("source.txt")
    admin._pending_bot_data[admin._session_key(update)] = {"bot_id": str(bot_id)}
    admin.storage.books.find_by_hash = AsyncMock(return_value=None)
    admin.storage.books.create_book = AsyncMock(
        return_value=SimpleNamespace(id=book_id, file_format="txt")
    )
    admin.storage.books.update_metadata = AsyncMock()
    context = MagicMock()
    context.bot.get_file = AsyncMock(return_value=FakeTelegramFile(b"book bytes"))
    monkeypatch.setattr("admin_bot.BOOKS_STORAGE_DIR", str(tmp_path))

    state = await admin.addbook_file(update, context)

    assert state == WAITING_BOOK_META
    assert (tmp_path / f"{book_id}.txt").read_bytes() == b"book bytes"
    pending = admin._pending_bot_data[admin._session_key(update)]
    assert pending["book_id"] == str(book_id)

    update.message.text = "Custom Title — Custom Author"
    delayed = MagicMock()
    with patch("knowledge.tasks.ingest_book") as ingest_book:
        ingest_book.delay = delayed
        final_state = await admin.addbook_meta(update, context)

    assert final_state == ConversationHandler.END
    admin.storage.books.update_metadata.assert_awaited_once_with(
        str(book_id),
        "Custom Title",
        "Custom Author",
    )
    delayed.assert_called_once_with(str(book_id))


@pytest.mark.asyncio
async def test_addbook_rejects_duplicate_hash(tmp_path, monkeypatch):
    bot_id = uuid4()
    admin = make_admin(tmp_path)
    update = make_update("source.txt")
    admin._pending_bot_data[admin._session_key(update)] = {"bot_id": str(bot_id)}
    admin.storage.books.find_by_hash = AsyncMock(
        return_value=SimpleNamespace(title="Existing Book")
    )
    context = MagicMock()
    context.bot.get_file = AsyncMock(return_value=FakeTelegramFile(b"same bytes"))
    monkeypatch.setattr("admin_bot.BOOKS_STORAGE_DIR", str(tmp_path))

    state = await admin.addbook_file(update, context)

    assert state == ConversationHandler.END
    admin.storage.books.create_book.assert_not_called()


@pytest.mark.asyncio
async def test_listbooks_outputs_book_status(tmp_path):
    bot_id = uuid4()
    book_id = uuid4()
    admin = make_admin(tmp_path)
    admin.storage.bots.get_bot = AsyncMock(return_value=SimpleNamespace(id=bot_id, name="Nietzsche"))
    admin.storage.books.list_books = AsyncMock(
        return_value=[
            SimpleNamespace(
                id=book_id,
                title="Zarathustra",
                author="Nietzsche",
                status="ready",
                chunk_count=12,
                error=None,
            )
        ]
    )
    update = MagicMock()
    update.effective_user.id = 1
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = [str(bot_id)]

    await admin.listbooks_command(update, context)

    text = update.message.reply_text.await_args.args[0]
    assert "Zarathustra" in text
    assert str(book_id) in text


@pytest.mark.asyncio
async def test_removebook_deletes_vectors_file_and_row(tmp_path, monkeypatch):
    book_id = uuid4()
    admin = make_admin(tmp_path)
    source_file = tmp_path / f"{book_id}.txt"
    source_file.write_text("content", encoding="utf-8")
    admin.storage.books.get_book = AsyncMock(
        return_value=SimpleNamespace(
            id=book_id,
            title="Book",
            file_format="txt",
        )
    )
    admin.storage.books.delete_book = AsyncMock(return_value=True)
    update = MagicMock()
    update.effective_user.id = 1
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = [str(book_id)]
    monkeypatch.setattr("admin_bot.BOOKS_STORAGE_DIR", str(tmp_path))

    vector_store = MagicMock()
    vector_store.delete_book = AsyncMock()
    with patch("admin_bot.BookVectorStore", return_value=vector_store):
        await admin.removebook_command(update, context)

    vector_store.delete_book.assert_awaited_once_with(str(book_id))
    admin.storage.books.delete_book.assert_awaited_once_with(str(book_id))
    assert not source_file.exists()
