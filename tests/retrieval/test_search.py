import psycopg
import pytest

from app.retrieval.search import keyword_search, top_similarity, vector_search
from tests.fakes import FakeEmbedder
from tests.retrieval.conftest import exact_chunk

pytestmark = pytest.mark.db


def test_vector_search_finds_exact_chunk(ingested_conn: psycopg.Connection) -> None:
    chunk_id, embed_text = exact_chunk(ingested_conn)
    vec = FakeEmbedder().embed_documents([embed_text])[0]
    hits = vector_search(ingested_conn, vec, 3)
    assert hits[0].chunk_id == chunk_id
    assert hits[0].score > 0.999
    assert len(hits) == 3


def test_keyword_search_matches_any_word(ingested_conn: psycopg.Connection) -> None:
    hits = keyword_search(ingested_conn, "Which datagrams use checksums?", 5)
    assert any(h.rfc_number == 9997 for h in hits)


def test_keyword_search_ranks_better_match_first(ingested_conn: psycopg.Connection) -> None:
    hits = keyword_search(ingested_conn, "Checksums are optional", 5)
    assert (hits[0].rfc_number, hits[0].section_id) == (9997, "u3")


def test_keyword_only_stopwords_is_empty(ingested_conn: psycopg.Connection) -> None:
    assert keyword_search(ingested_conn, "what is it?", 5) == []
    assert keyword_search(ingested_conn, "???", 5) == []


def test_keyword_operator_characters_are_safe(ingested_conn: psycopg.Connection) -> None:
    assert isinstance(keyword_search(ingested_conn, "C++ & TCP | !(x)", 5), list)
    assert isinstance(keyword_search(ingested_conn, "O'Reilly", 5), list)


def test_top_similarity(ingested_conn: psycopg.Connection) -> None:
    _, embed_text = exact_chunk(ingested_conn)
    vec = FakeEmbedder().embed_documents([embed_text])[0]
    sim = top_similarity(ingested_conn, vec)
    assert sim is not None and sim > 0.999


def test_top_similarity_empty_db(migrated_conn: psycopg.Connection) -> None:
    assert top_similarity(migrated_conn, FakeEmbedder().embed_query("x")) is None
