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
    """The k chunks closest to the query vector; score = cosine similarity."""
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
    """Cosine similarity of the closest chunk, or None if there are no chunks."""
    register_vector(conn)
    row = conn.execute(
        "SELECT 1 - (embedding <=> %s) FROM chunks ORDER BY embedding <=> %s LIMIT 1",
        (query_vec, query_vec),
    ).fetchone()
    return None if row is None else float(row[0])
