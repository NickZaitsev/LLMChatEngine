"""Guardrails for the persona-bot documentation and its README link."""

from pathlib import Path


def test_persona_doc_exists_and_is_linked_from_readme():
    assert Path("docs/persona-bots.md").exists()
    readme = Path("README.md").read_text(encoding="utf-8")
    assert "docs/persona-bots.md" in readme


def test_persona_doc_covers_required_commands_and_notes():
    doc = Path("docs/persona-bots.md").read_text(encoding="utf-8")
    for token in (
        "/addbot",
        "/togglefeature",
        "book_knowledge",
        "/addbook",
        "/listbooks",
        "/removebook",
        ".fb2",
        "20 МБ",  # 20 МБ size limit
        "MEMORY_EMBED_DIM",
        "book_files",
    ):
        assert token in doc, f"persona doc is missing {token!r}"
