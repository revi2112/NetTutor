import psycopg
import pytest

from app.retrieval.retrieve import retrieve
from app.retrieval.search import keyword_search
from tests.conftest import exact_chunk
from tests.fakes import FakeEmbedder

pytestmark = pytest.mark.db

MODES = ("vector", "keyword", "hybrid")


def test_modes_return_k_hits(ingested_conn: psycopg.Connection) -> None:
    for mode in MODES:
        result = retrieve(
            ingested_conn, FakeEmbedder(), "datagram checksums", mode=mode, k=3, threshold=0.0
        )
        ids = [h.chunk_id for h in result.hits]
        assert len(ids) <= 3
        assert len(ids) == len(set(ids))


def test_hybrid_contains_keyword_and_vector_winners(ingested_conn: psycopg.Connection) -> None:
    chunk_id, embed_text = exact_chunk(ingested_conn)
    keyword_winner = keyword_search(ingested_conn, embed_text, 1)[0].chunk_id
    result = retrieve(ingested_conn, FakeEmbedder(), embed_text, mode="hybrid", k=10, threshold=0.0)
    ids = {h.chunk_id for h in result.hits}
    assert chunk_id in ids
    assert keyword_winner in ids


def test_on_topic_uses_vector_similarity_in_every_mode(ingested_conn: psycopg.Connection) -> None:
    _, embed_text = exact_chunk(ingested_conn)
    for mode in MODES:
        on = retrieve(ingested_conn, FakeEmbedder(), embed_text, mode=mode, k=3, threshold=0.99)
        off = retrieve(
            ingested_conn, FakeEmbedder(), "zzz unrelated", mode=mode, k=3, threshold=0.99
        )
        assert on.on_topic is True
        assert off.on_topic is False


def test_empty_database(migrated_conn: psycopg.Connection) -> None:
    result = retrieve(migrated_conn, FakeEmbedder(), "tcp", mode="hybrid", k=5, threshold=0.5)
    assert result.hits == []
    assert result.top_similarity is None
    assert result.on_topic is False


def test_stopword_only_query_still_returns_hits(ingested_conn: psycopg.Connection) -> None:
    for mode in ("vector", "hybrid"):
        result = retrieve(
            ingested_conn, FakeEmbedder(), "what is it?", mode=mode, k=3, threshold=0.0
        )
        assert result.hits, mode
