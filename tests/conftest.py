"""Shared fixtures. DB tests use a throwaway `nettutor_test` database on the compose Postgres."""

import shutil
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import sql

from app.api.main import create_app
from app.config import Settings
from app.ingest.pipeline import ingest
from app.ingest.rfc_list import RfcEntry
from tests.fakes import FakeEmbedder

TEST_DB_NAME = "nettutor_test"


def _with_db(url: str, db_name: str) -> str:
    parts = urlsplit(url)
    return urlunsplit(parts._replace(path=f"/{db_name}"))


def make_settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[call-arg, arg-type]


@pytest.fixture(scope="session")
def test_database_url() -> str:
    base_url = make_settings().database_url
    try:
        admin = psycopg.connect(_with_db(base_url, "postgres"), autocommit=True, connect_timeout=3)
    except psycopg.OperationalError:
        pytest.skip("Postgres is not reachable; run `make db-up` to run DB tests")
    with admin:
        name = sql.Identifier(TEST_DB_NAME)
        admin.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(name))
        admin.execute(sql.SQL("CREATE DATABASE {}").format(name))
    return _with_db(base_url, TEST_DB_NAME)


@pytest.fixture
def db_conn(test_database_url: str) -> Iterator[psycopg.Connection]:
    """A connection to the test database with an empty `public` schema."""
    with psycopg.connect(test_database_url, connect_timeout=3) as conn:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")
        conn.commit()
        yield conn


@pytest.fixture
def migrated_conn(db_conn: psycopg.Connection) -> psycopg.Connection:
    """db_conn with all migrations applied at the default embedding dimension."""
    from app.db.migrate import apply_migrations

    apply_migrations(db_conn, embed_dim=make_settings().embed_dim)
    return db_conn


@pytest.fixture
def client(migrated_conn: psycopg.Connection, test_database_url: str) -> Iterator[TestClient]:
    """App wired to the test database, starting from a fresh migrated schema."""
    with TestClient(create_app(make_settings(database_url=test_database_url))) as c:
        yield c


INGEST_FIXTURES = Path(__file__).parent / "ingest" / "fixtures"


@pytest.fixture
def ingested_conn(migrated_conn: psycopg.Connection, tmp_path: Path) -> psycopg.Connection:
    """The two fixture RFCs (9999 numbered, 9997 unnumbered) ingested with FakeEmbedder."""
    shutil.copy(INGEST_FIXTURES / "rfc_old_paged.txt", tmp_path / "rfc9999.txt")
    shutil.copy(INGEST_FIXTURES / "rfc_unnumbered.txt", tmp_path / "rfc9997.txt")
    entries = [
        RfcEntry(number=9999, title="Example Transfer"),
        RfcEntry(number=9997, title="Example Datagram"),
    ]
    ingest(migrated_conn, entries, tmp_path, FakeEmbedder(), max_tokens=400, overlap_tokens=60)
    return migrated_conn


def exact_chunk(conn: psycopg.Connection) -> tuple[int, str]:
    """(chunk id, its embed text) for one stored chunk."""
    row = conn.execute(
        "SELECT c.id, d.rfc_number, c.section_id, c.section_title, c.text FROM chunks c"
        " JOIN documents d ON d.id = c.document_id ORDER BY c.id LIMIT 1 OFFSET 1"
    ).fetchone()
    assert row is not None
    chunk_id, rfc, section_id, title, text = row
    return chunk_id, f"RFC {rfc} §{section_id} {title}\n{text}"
