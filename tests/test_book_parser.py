from pathlib import Path

import pytest

from knowledge.parser import BookParseError, extract_text


def test_extract_text_reads_utf8_txt(tmp_path: Path):
    file_path = tmp_path / "book.txt"
    file_path.write_text("First   paragraph.\n\nSecond\nparagraph.", encoding="utf-8")

    text = extract_text(str(file_path), "txt")

    assert text == "First paragraph.\n\nSecond paragraph."


def test_extract_text_reads_cp1251_txt(tmp_path: Path):
    file_path = tmp_path / "book.txt"
    file_path.write_bytes("Привет, мир!\n\nВторая строка.".encode("cp1251"))

    text = extract_text(str(file_path), "txt")

    assert text == "Привет, мир!\n\nВторая строка."


def test_extract_text_reads_fb2_body(tmp_path: Path):
    file_path = tmp_path / "book.fb2"
    file_path.write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">
  <body>
    <section>
      <p>First paragraph.</p>
      <p>Second paragraph.</p>
    </section>
  </body>
</FictionBook>
""",
        encoding="utf-8",
    )

    text = extract_text(str(file_path), "fb2")

    assert "First paragraph." in text
    assert "Second paragraph." in text


def test_extract_text_rejects_unsupported_format(tmp_path: Path):
    file_path = tmp_path / "book.docx"
    file_path.write_text("content", encoding="utf-8")

    with pytest.raises(BookParseError, match="Unsupported book format"):
        extract_text(str(file_path), "docx")


def test_extract_text_rejects_empty_text(tmp_path: Path):
    file_path = tmp_path / "empty.txt"
    file_path.write_text("   \n\n\t", encoding="utf-8")

    with pytest.raises(BookParseError, match="No text extracted"):
        extract_text(str(file_path), "txt")
