import pytest
import pytest_asyncio
from sqlalchemy.exc import IntegrityError


@pytest_asyncio.fixture
async def sample_bot(storage):
    return await storage.bots.create_bot(
        token_encrypted="encrypted-token",
        name="BookBot",
        personality="Book-aware personality",
    )


@pytest.mark.asyncio
async def test_book_repo_crud_and_status_transitions(storage, sample_bot):
    book = await storage.books.create_book(
        bot_id=str(sample_bot.id),
        title="Thus Spoke Zarathustra",
        author="Friedrich Nietzsche",
        source_filename="zarathustra.txt",
        file_format="txt",
        file_hash="a" * 64,
    )

    assert book.status == "pending"
    assert book.chunk_count == 0
    assert book.char_count == 0

    loaded = await storage.books.get_book(str(book.id))
    assert loaded is not None
    assert loaded.title == "Thus Spoke Zarathustra"
    assert loaded.bot_id == sample_bot.id

    by_hash = await storage.books.find_by_hash(str(sample_bot.id), "a" * 64)
    assert by_hash.id == book.id

    processing = await storage.books.update_status(str(book.id), "processing")
    assert processing.status == "processing"
    assert processing.error is None

    ready = await storage.books.update_status(
        str(book.id),
        "ready",
        chunk_count=42,
        char_count=12345,
    )
    assert ready.status == "ready"
    assert ready.chunk_count == 42
    assert ready.char_count == 12345

    failed = await storage.books.update_status(str(book.id), "failed", error="Parse failed")
    assert failed.status == "failed"
    assert failed.error == "Parse failed"

    books = await storage.books.list_books(str(sample_bot.id))
    assert [listed.id for listed in books] == [book.id]

    assert await storage.books.delete_book(str(book.id)) is True
    assert await storage.books.get_book(str(book.id)) is None
    assert await storage.books.delete_book(str(book.id)) is False


@pytest.mark.asyncio
async def test_book_repo_hash_dedup_is_per_bot(storage, sample_bot):
    other_bot = await storage.bots.create_bot(
        token_encrypted="other-token",
        name="OtherBot",
        personality="Other personality",
    )

    await storage.books.create_book(
        bot_id=str(sample_bot.id),
        title="Book A",
        author=None,
        source_filename="book-a.txt",
        file_format="txt",
        file_hash="b" * 64,
    )

    duplicate = await storage.books.find_by_hash(str(sample_bot.id), "b" * 64)
    assert duplicate is not None

    await storage.books.create_book(
        bot_id=str(other_bot.id),
        title="Book A",
        author=None,
        source_filename="book-a.txt",
        file_format="txt",
        file_hash="b" * 64,
    )

    with pytest.raises(IntegrityError):
        await storage.books.create_book(
            bot_id=str(sample_bot.id),
            title="Duplicate Book",
            author=None,
            source_filename="duplicate.txt",
            file_format="txt",
            file_hash="b" * 64,
        )
