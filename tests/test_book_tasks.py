from types import SimpleNamespace
from uuid import uuid4

import pytest

from knowledge.tasks import ingest_book_async


class FakeBookRepo:
    def __init__(self, book=None):
        self.book = book
        self.status_updates = []

    async def get_book(self, book_id):
        return self.book

    async def update_status(
        self,
        book_id,
        status,
        error=None,
        chunk_count=None,
        char_count=None,
    ):
        self.status_updates.append(
            {
                "book_id": book_id,
                "status": status,
                "error": error,
                "chunk_count": chunk_count,
                "char_count": char_count,
            }
        )
        return self.book


class FakeBookKnowledgeManager:
    def __init__(self):
        self.ingested = []

    async def ingest_book(self, book_id, bot_id, title, author, text):
        self.ingested.append(
            {
                "book_id": book_id,
                "bot_id": bot_id,
                "title": title,
                "author": author,
                "text": text,
            }
        )
        return 7


def make_context(book_repo, manager):
    return SimpleNamespace(
        conversation_manager=SimpleNamespace(
            storage=SimpleNamespace(books=book_repo),
        ),
        book_knowledge_manager=manager,
    )


def make_context_loader(book_repo, manager):
    async def load_context():
        return make_context(book_repo, manager)

    return load_context


@pytest.mark.asyncio
async def test_ingest_book_async_marks_ready_and_deletes_source(monkeypatch, tmp_path):
    book_id = uuid4()
    bot_id = uuid4()
    book = SimpleNamespace(
        id=book_id,
        bot_id=bot_id,
        title="Book Title",
        author="Author Name",
        file_format="txt",
    )
    source_file = tmp_path / f"{book_id}.txt"
    source_file.write_text("raw", encoding="utf-8")
    repo = FakeBookRepo(book)
    manager = FakeBookKnowledgeManager()

    monkeypatch.setattr("knowledge.tasks.settings", SimpleNamespace(books=SimpleNamespace(storage_dir=str(tmp_path), keep_source_files=False)))
    monkeypatch.setattr("knowledge.tasks.extract_text", lambda path, fmt: "parsed text")
    monkeypatch.setattr(
        "knowledge.tasks.get_app_context",
        make_context_loader(repo, manager),
    )

    await ingest_book_async(str(book_id))

    assert repo.status_updates == [
        {
            "book_id": str(book_id),
            "status": "processing",
            "error": None,
            "chunk_count": None,
            "char_count": None,
        },
        {
            "book_id": str(book_id),
            "status": "ready",
            "error": None,
            "chunk_count": 7,
            "char_count": 11,
        },
    ]
    assert manager.ingested == [
        {
            "book_id": str(book_id),
            "bot_id": str(bot_id),
            "title": "Book Title",
            "author": "Author Name",
            "text": "parsed text",
        }
    ]
    assert not source_file.exists()


@pytest.mark.asyncio
async def test_ingest_book_async_marks_failed_on_parse_error(monkeypatch, tmp_path):
    book_id = uuid4()
    book = SimpleNamespace(
        id=book_id,
        bot_id=uuid4(),
        title="Broken",
        author=None,
        file_format="txt",
    )
    repo = FakeBookRepo(book)

    def fail_parse(path, fmt):
        raise ValueError("bad parse")

    monkeypatch.setattr("knowledge.tasks.settings", SimpleNamespace(books=SimpleNamespace(storage_dir=str(tmp_path), keep_source_files=False)))
    monkeypatch.setattr("knowledge.tasks.extract_text", fail_parse)
    monkeypatch.setattr(
        "knowledge.tasks.get_app_context",
        make_context_loader(repo, FakeBookKnowledgeManager()),
    )

    with pytest.raises(ValueError, match="bad parse"):
        await ingest_book_async(str(book_id))

    assert repo.status_updates[-1] == {
        "book_id": str(book_id),
        "status": "failed",
        "error": "bad parse",
        "chunk_count": None,
        "char_count": None,
    }


@pytest.mark.asyncio
async def test_ingest_book_async_returns_when_book_is_missing(monkeypatch):
    repo = FakeBookRepo(book=None)
    monkeypatch.setattr(
        "knowledge.tasks.get_app_context",
        make_context_loader(repo, FakeBookKnowledgeManager()),
    )

    await ingest_book_async("missing-book")

    assert repo.status_updates == []
