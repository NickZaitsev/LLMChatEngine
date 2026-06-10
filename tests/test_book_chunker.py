from knowledge.chunker import chunk_text


class WordTokenCounter:
    def count_tokens(self, text: str) -> int:
        return len(text.split()) if text else 0


def test_chunk_text_returns_empty_for_blank_text():
    assert chunk_text("", token_counter=WordTokenCounter()) == []
    assert chunk_text(" \n\n ", token_counter=WordTokenCounter()) == []


def test_chunk_text_assigns_sequential_indices():
    text = "one two three\n\nfour five six\n\nseven eight nine"

    chunks = chunk_text(
        text,
        target_tokens=4,
        overlap_tokens=0,
        token_counter=WordTokenCounter(),
    )

    assert [chunk.chunk_index for chunk in chunks] == [0, 1, 2]


def test_chunk_text_packs_paragraphs_with_overlap():
    text = "alpha beta\n\ngamma delta\n\nepsilon zeta"

    chunks = chunk_text(
        text,
        target_tokens=4,
        overlap_tokens=2,
        token_counter=WordTokenCounter(),
    )

    assert [chunk.text for chunk in chunks] == [
        "alpha beta\n\ngamma delta",
        "gamma delta\n\nepsilon zeta",
    ]


def test_chunk_text_splits_oversized_paragraph_on_sentences():
    text = "One two three. Four five six. Seven eight nine."

    chunks = chunk_text(
        text,
        target_tokens=3,
        overlap_tokens=0,
        token_counter=WordTokenCounter(),
    )

    assert [chunk.text for chunk in chunks] == [
        "One two three.",
        "Four five six.",
        "Seven eight nine.",
    ]


def test_chunk_text_falls_back_to_word_split_for_long_sentence():
    text = "one two three four five six seven"

    chunks = chunk_text(
        text,
        target_tokens=3,
        overlap_tokens=0,
        token_counter=WordTokenCounter(),
    )

    assert [chunk.text for chunk in chunks] == ["one two three", "four five six", "seven"]
