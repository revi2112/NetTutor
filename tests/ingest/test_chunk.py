from app.ingest.chunk import Chunk, chunk_document, chunk_text
from app.ingest.parse import Section


def words(s: str) -> int:
    return len(s.split())


def para(tag: str, n: int) -> str:
    return " ".join(f"{tag}{i}" for i in range(n))


def test_short_text_is_one_chunk() -> None:
    chunks = chunk_text("one two\n\nthree", count_tokens=words, max_tokens=400, overlap_tokens=60)
    assert chunks == ["one two\n\nthree"]


def test_paragraph_packing_and_overlap() -> None:
    paragraphs = [para(f"p{k}_", 50) for k in range(10)]
    chunks = chunk_text(
        "\n\n".join(paragraphs), count_tokens=words, max_tokens=400, overlap_tokens=60
    )
    assert all(words(c) <= 400 for c in chunks)
    assert chunks[0] == "\n\n".join(paragraphs[:8])
    assert chunks[1].startswith(paragraphs[7])  # overlap: the last paragraph (50 <= 60)
    for p in paragraphs:
        assert any(p in c for c in chunks)
    assert chunks[-1].endswith(paragraphs[9])


def test_long_line_splits_into_words_with_overlap() -> None:
    chunks = chunk_text(para("w", 1000), count_tokens=words, max_tokens=400, overlap_tokens=60)
    assert all(words(c) <= 400 for c in chunks)
    assert chunks[1].split()[:60] == chunks[0].split()[-60:]


def test_unbreakable_run_terminates() -> None:
    def count(s: str) -> int:
        return len(s) // 4 + 1

    text = "a\n\n" + "x" * 5000 + "\n\nb"
    assert chunk_text(text, count_tokens=count, max_tokens=400, overlap_tokens=60) == [
        "a",
        "x" * 5000,
        "b",
    ]
    chunks = chunk_document(
        1, [Section("1", "T", text)], count_tokens=count, max_tokens=400, overlap_tokens=60
    )
    assert chunks[1].token_count == 5000 // 4 + 1


def test_chunks_never_cross_sections() -> None:
    sections = [Section("1", "A", para("a", 30)), Section("2", "B", para("b", 30))]
    chunks = chunk_document(9293, sections, count_tokens=words, max_tokens=400, overlap_tokens=60)
    assert len(chunks) == 2
    for chunk in chunks:
        tags = {w[0] for w in chunk.text.split()}
        assert len(tags) == 1
        assert chunk.section_id == {"a": "1", "b": "2"}[tags.pop()]


def test_empty_sections_skipped() -> None:
    chunks = chunk_document(
        1, [Section("2", "Protocol", "")], count_tokens=words, max_tokens=400, overlap_tokens=60
    )
    assert chunks == []


def test_embed_text_and_hash() -> None:
    chunk = Chunk(9293, "3.5", "Establishing a Connection", "SYN", 1)
    assert chunk.embed_text == "RFC 9293 §3.5 Establishing a Connection\nSYN"
    other = Chunk(9293, "3.6", "Establishing a Connection", "SYN", 1)
    assert chunk.content_hash != other.content_hash
    assert len(chunk.content_hash) == 64
    int(chunk.content_hash, 16)
