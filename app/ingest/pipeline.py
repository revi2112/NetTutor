"""Ingest: parse -> chunk -> embed -> store, idempotently.

Two ideas make re-running safe and cheap:
- A document's `content_hash` is a hash of its chunk hashes. Parsing and chunking are fast
  (seconds for all RFCs), so every run recomputes the chunks, and an RFC is re-embedded only
  if its chunks would change: a new file, a parser fix, or new chunk sizes. A plain re-run
  embeds nothing.
- Each RFC is written and committed on its own (delete its old chunks, insert the new ones).
  A crash therefore leaves whole documents behind, never half of one, and the next run
  picks up where this one stopped.
"""

import hashlib
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import psycopg
from pgvector.psycopg import register_vector

from app.db.schema_check import check_schema
from app.ingest.chunk import Chunk, chunk_document
from app.ingest.parse import parse_rfc
from app.ingest.rfc_list import RfcEntry
from app.llm.embeddings import Embedder


class NotMigratedError(RuntimeError):
    """The database has no schema yet."""


@dataclass
class IngestSummary:
    ingested: list[int] = field(default_factory=list)
    unchanged: list[int] = field(default_factory=list)
    removed: list[int] = field(default_factory=list)
    chunks_written: int = 0
    seconds: float = 0.0


def _document_hash(chunks: Sequence[Chunk]) -> str:
    return hashlib.sha256("\n".join(c.content_hash for c in chunks).encode()).hexdigest()


def _prepare(conn: psycopg.Connection, embedder: Embedder) -> None:
    """Fail before writing anything if the schema is missing or made for another model."""
    row = conn.execute("SELECT to_regclass('chunks')").fetchone()
    if row is None or row[0] is None:
        raise NotMigratedError("database is not migrated; run `make migrate`")
    check_schema(conn, embedder.model_name, embedder.dim)
    register_vector(conn)


def _store_document(
    conn: psycopg.Connection,
    entry: RfcEntry,
    chunks: Sequence[Chunk],
    doc_hash: str,
    embedder: Embedder,
) -> None:
    vectors = embedder.embed_documents([c.embed_text for c in chunks])
    row = conn.execute(
        "INSERT INTO documents (rfc_number, title, url, content_hash)"
        " VALUES (%s, %s, %s, %s)"
        " ON CONFLICT (rfc_number) DO UPDATE SET title = EXCLUDED.title, url = EXCLUDED.url,"
        " content_hash = EXCLUDED.content_hash, ingested_at = now()"
        " RETURNING id",
        (entry.number, entry.title, entry.html_url, doc_hash),
    ).fetchone()
    assert row is not None
    document_id = row[0]
    conn.execute("DELETE FROM chunks WHERE document_id = %s", (document_id,))
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO chunks (document_id, section_id, section_title, text, token_count,"
            " embedding, content_hash) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            [
                (
                    document_id,
                    c.section_id,
                    c.section_title,
                    c.text,
                    c.token_count,
                    vector,
                    c.content_hash,
                )
                for c, vector in zip(chunks, vectors, strict=True)
            ],
        )


def ingest(
    conn: psycopg.Connection,
    entries: Sequence[RfcEntry],
    raw_dir: Path,
    embedder: Embedder,
    *,
    max_tokens: int,
    overlap_tokens: int,
) -> IngestSummary:
    started = time.monotonic()
    summary = IngestSummary()
    _prepare(conn, embedder)

    missing = [e.filename for e in entries if not (raw_dir / e.filename).exists()]
    if missing:
        raise FileNotFoundError(f"missing in {raw_dir}: {', '.join(missing)}; run `make fetch`")

    conn.execute(
        "INSERT INTO embedding_meta (model, dim) VALUES (%s, %s) ON CONFLICT (id) DO NOTHING",
        (embedder.model_name, embedder.dim),
    )
    removed = conn.execute(
        "DELETE FROM documents WHERE NOT (rfc_number = ANY(%s)) RETURNING rfc_number",
        ([e.number for e in entries],),
    ).fetchall()
    summary.removed = sorted(r[0] for r in removed)
    conn.commit()

    for entry in entries:
        sections = parse_rfc((raw_dir / entry.filename).read_text())
        chunks = chunk_document(
            entry.number,
            sections,
            count_tokens=embedder.count_tokens,
            max_tokens=max_tokens,
            overlap_tokens=overlap_tokens,
        )
        doc_hash = _document_hash(chunks)
        stored = conn.execute(
            "SELECT content_hash FROM documents WHERE rfc_number = %s", (entry.number,)
        ).fetchone()
        if stored is not None and stored[0] == doc_hash:
            summary.unchanged.append(entry.number)
            continue
        # Explicit commit/rollback rather than `with conn.transaction()`: the SELECT above
        # already opened a transaction, inside which transaction() would only be a savepoint.
        try:
            _store_document(conn, entry, chunks, doc_hash, embedder)
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        summary.ingested.append(entry.number)
        summary.chunks_written += len(chunks)

    summary.seconds = time.monotonic() - started
    return summary
