from pathlib import Path

import psycopg
import pytest

from app.db.migrate import apply_migrations

pytestmark = pytest.mark.db


def _tables(conn: psycopg.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
    ).fetchall()
    return {r[0] for r in rows}


def _insert_document(conn: psycopg.Connection) -> int:
    row = conn.execute(
        "INSERT INTO documents (rfc_number, title, url, content_hash)"
        " VALUES (9293, 'TCP', 'https://www.rfc-editor.org/rfc/rfc9293', 'doc-hash') RETURNING id"
    ).fetchone()
    assert row is not None
    return int(row[0])


def _insert_chunk(conn: psycopg.Connection, doc_id: int, text: str, content_hash: str) -> None:
    conn.execute(
        "INSERT INTO chunks"
        " (document_id, section_id, section_title, text, token_count, content_hash)"
        " VALUES (%s, '3.5', 'Establishing a Connection', %s, 4, %s)",
        (doc_id, text, content_hash),
    )


def test_creates_all_tables(db_conn: psycopg.Connection) -> None:
    apply_migrations(db_conn, embed_dim=384)
    assert {
        "documents",
        "chunks",
        "quizzes",
        "quiz_questions",
        "embedding_meta",
        "schema_migrations",
    } <= _tables(db_conn)


def test_idempotent(db_conn: psycopg.Connection) -> None:
    assert apply_migrations(db_conn, embed_dim=384) == ["0001_init.sql"]
    assert apply_migrations(db_conn, embed_dim=384) == []


def test_embedding_dim_from_config(db_conn: psycopg.Connection) -> None:
    apply_migrations(db_conn, embed_dim=8)
    row = db_conn.execute(
        "SELECT atttypmod FROM pg_attribute"
        " WHERE attrelid = 'chunks'::regclass AND attname = 'embedding'"
    ).fetchone()
    assert row == (8,)


def test_indexes_exist(migrated_conn: psycopg.Connection) -> None:
    defs = [
        r[0]
        for r in migrated_conn.execute(
            "SELECT indexdef FROM pg_indexes WHERE tablename = 'chunks'"
        ).fetchall()
    ]
    assert any("hnsw" in d and "vector_cosine_ops" in d for d in defs)
    assert any("gin" in d and "tsv" in d for d in defs)


def test_tsv_generated(migrated_conn: psycopg.Connection) -> None:
    doc_id = _insert_document(migrated_conn)
    _insert_chunk(migrated_conn, doc_id, "TCP three-way handshake", "c1")
    row = migrated_conn.execute(
        "SELECT tsv @@ to_tsquery('english', 'handshake') FROM chunks"
    ).fetchone()
    assert row == (True,)


def test_content_hash_unique(migrated_conn: psycopg.Connection) -> None:
    doc_id = _insert_document(migrated_conn)
    _insert_chunk(migrated_conn, doc_id, "first", "same-hash")
    with pytest.raises(psycopg.errors.UniqueViolation):
        _insert_chunk(migrated_conn, doc_id, "second", "same-hash")


def test_failed_migration_not_recorded(db_conn: psycopg.Connection, tmp_path: Path) -> None:
    (tmp_path / "0001_ok.sql").write_text("CREATE TABLE a (id int);")
    (tmp_path / "0002_bad.sql").write_text("CREATE TABLE b (id int); SELEC 1;")

    with pytest.raises(psycopg.errors.SyntaxError):
        apply_migrations(db_conn, embed_dim=384, migrations_dir=tmp_path)

    tables = _tables(db_conn)
    assert "a" in tables
    assert "b" not in tables
    recorded = {r[0] for r in db_conn.execute("SELECT filename FROM schema_migrations")}
    assert recorded == {"0001_ok.sql"}
