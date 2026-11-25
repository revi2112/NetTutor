"""Startup check: the database's embedding setup must match the configured embedding model."""

import logging

import psycopg

logger = logging.getLogger(__name__)

FIX_HINT = "re-run migrations on a fresh database and re-ingest"


class SchemaMismatchError(RuntimeError):
    """The stored embeddings can't be used with the configured embedding model."""


def check_schema(conn: psycopg.Connection, embed_model: str, embed_dim: int) -> None:
    """Raise SchemaMismatchError if the vector column or embedding_meta disagree with config.

    An unmigrated database is only a warning (`make migrate` fixes it); an empty
    embedding_meta is fine (nothing has been ingested yet).
    """
    row = conn.execute(
        "SELECT atttypmod FROM pg_attribute"
        " WHERE attrelid = to_regclass('chunks') AND attname = 'embedding'"
    ).fetchone()
    if row is None:
        logger.warning("database is not migrated yet; run `make migrate`")
        return
    column_dim = int(row[0])
    if column_dim != embed_dim:
        raise SchemaMismatchError(
            f"chunks.embedding has dimension {column_dim} but EMBED_DIM is {embed_dim}; {FIX_HINT}"
        )

    meta = conn.execute("SELECT model, dim FROM embedding_meta").fetchone()
    if meta is not None and (meta[0], meta[1]) != (embed_model, embed_dim):
        raise SchemaMismatchError(
            f"stored embeddings were made with {meta[0]} ({meta[1]}-d) but config is "
            f"{embed_model} ({embed_dim}-d); {FIX_HINT}"
        )
