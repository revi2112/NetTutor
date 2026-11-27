"""The two base searches over `chunks`: vector (pgvector cosine) and keyword (full-text).

Keyword search matches chunks containing ANY of the question's words, ranked by
`ts_rank_cd`. Postgres's usual `websearch_to_tsquery` ANDs every word. Measured on the real
corpus, "What private IPv4 address ranges exist?" matched 0 chunks that way, because no
chunk says "exist", and "How does the TCP three-way handshake work?" matched 1. ORing the
stemmed, stopword-free words (plainto_tsquery's `&` turned into `|`) lets the ranking do the
work: chunks with more of the words, closer together, rank higher.
"""

from dataclasses import dataclass
from typing import Any

import psycopg
from pgvector.psycopg import register_vector

from app.llm.embeddings import Vector

_COLUMNS = "c.id, d.rfc_number, c.section_id, c.section_title, c.text"
_FROM = "FROM chunks c JOIN documents d ON d.id = c.document_id"


@dataclass(frozen=True)
class Hit:
    chunk_id: int
    rfc_number: int
    section_id: str
    section_title: str
    text: str
    score: float


def _hit(row: tuple[Any, ...]) -> Hit:
    chunk_id, rfc_number, section_id, section_title, text, score = row
    return Hit(chunk_id, rfc_number, section_id, section_title, text, float(score))


def vector_search(conn: psycopg.Connection, query_vec: Vector, k: int) -> list[Hit]:
    """The k chunks closest to the query vector; score = cosine similarity.

    The `c.id` tie-break makes Postgres do an exact scan instead of using the approximate
    HNSW index. That is intended: at ~4k chunks it takes milliseconds, the on-topic threshold
    sits in a band 0.01 wide, and HNSW would also cap results at `hnsw.ef_search` (40).
    """
    register_vector(conn)
    rows = conn.execute(
        f"SELECT {_COLUMNS}, 1 - (c.embedding <=> %s) AS score {_FROM}"
        " ORDER BY c.embedding <=> %s, c.id LIMIT %s",
        (query_vec, query_vec, k),
    ).fetchall()
    return [_hit(row) for row in rows]


def keyword_search(conn: psycopg.Connection, query: str, k: int) -> list[Hit]:
    """The k best full-text matches for any of the query's words; score = ts_rank_cd."""
    rows = conn.execute(
        "WITH q AS (SELECT replace(plainto_tsquery('english', %s)::text, '&', '|')::tsquery AS q)"
        f" SELECT {_COLUMNS}, ts_rank_cd(c.tsv, q.q) AS score {_FROM}, q"
        " WHERE c.tsv @@ q.q ORDER BY score DESC, c.id LIMIT %s",
        (query, k),
    ).fetchall()
    return [_hit(row) for row in rows]


def top_similarity(conn: psycopg.Connection, query_vec: Vector) -> float | None:
    """Cosine similarity of the closest chunk (exact, as in vector_search), or None if empty."""
    best = vector_search(conn, query_vec, 1)
    return best[0].score if best else None
