import shutil
from pathlib import Path

import numpy as np
import psycopg
import pytest

from app.db.schema_check import SchemaMismatchError
from app.ingest.chunk import chunk_document
from app.ingest.parse import parse_rfc
from app.ingest.pipeline import NotMigratedError, ingest
from app.ingest.rfc_list import RfcEntry
from tests.fakes import FakeEmbedder

FIXTURES = Path(__file__).parent / "fixtures"
ENTRIES = [
    RfcEntry(number=9999, title="Example Transfer"),
    RfcEntry(number=9997, title="Example Datagram"),
]
SIZES = {"max_tokens": 400, "overlap_tokens": 60}

pytestmark = pytest.mark.db


@pytest.fixture
def raw_dir(tmp_path: Path) -> Path:
    shutil.copy(FIXTURES / "rfc_old_paged.txt", tmp_path / "rfc9999.txt")
    shutil.copy(FIXTURES / "rfc_unnumbered.txt", tmp_path / "rfc9997.txt")
    return tmp_path


def count(conn: psycopg.Connection, sql: str, *params: object) -> int:
    row = conn.execute(sql, params).fetchone()
    assert row is not None
    return int(row[0])


def chunk_ids(conn: psycopg.Connection, rfc: int) -> list[tuple[int, str]]:
    return conn.execute(
        "SELECT c.id, c.content_hash FROM chunks c JOIN documents d ON d.id = c.document_id"
        " WHERE d.rfc_number = %s ORDER BY c.id",
        (rfc,),
    ).fetchall()


def test_first_run_writes_everything(migrated_conn: psycopg.Connection, raw_dir: Path) -> None:
    embedder = FakeEmbedder()
    summary = ingest(migrated_conn, ENTRIES, raw_dir, embedder, **SIZES)
    assert summary.ingested == [9999, 9997]
    expected = sum(
        len(
            chunk_document(
                e.number,
                parse_rfc((raw_dir / e.filename).read_text()),
                count_tokens=embedder.count_tokens,
                **SIZES,
            )
        )
        for e in ENTRIES
    )
    assert count(migrated_conn, "SELECT count(*) FROM chunks") == expected
    assert summary.chunks_written == expected
    meta = migrated_conn.execute("SELECT model, dim FROM embedding_meta").fetchone()
    assert meta == ("fake/embedder", 384)
    url = migrated_conn.execute("SELECT url FROM documents WHERE rfc_number = 9999").fetchone()
    assert url == ("https://www.rfc-editor.org/rfc/rfc9999",)


def test_stored_vector_matches_embed_text(migrated_conn: psycopg.Connection, raw_dir: Path) -> None:
    ingest(migrated_conn, ENTRIES, raw_dir, FakeEmbedder(), **SIZES)
    row = migrated_conn.execute(
        "SELECT section_id, section_title, text, embedding FROM chunks c"
        " JOIN documents d ON d.id = c.document_id WHERE d.rfc_number = 9999 LIMIT 1"
    ).fetchone()
    assert row is not None
    section_id, title, text, embedding = row
    expected = FakeEmbedder().embed_documents([f"RFC 9999 §{section_id} {title}\n{text}"])[0]
    assert np.allclose(embedding.to_numpy(), expected, atol=1e-6)


def test_rerun_changes_nothing(migrated_conn: psycopg.Connection, raw_dir: Path) -> None:
    embedder = FakeEmbedder()
    ingest(migrated_conn, ENTRIES, raw_dir, embedder, **SIZES)
    before = chunk_ids(migrated_conn, 9999) + chunk_ids(migrated_conn, 9997)
    calls = len(embedder.calls)
    summary = ingest(migrated_conn, ENTRIES, raw_dir, embedder, **SIZES)
    assert summary.unchanged == [9999, 9997]
    assert summary.ingested == []
    assert summary.chunks_written == 0
    assert len(embedder.calls) == calls
    assert chunk_ids(migrated_conn, 9999) + chunk_ids(migrated_conn, 9997) == before


def test_changed_file_reingests_only_that_document(
    migrated_conn: psycopg.Connection, raw_dir: Path
) -> None:
    ingest(migrated_conn, ENTRIES, raw_dir, FakeEmbedder(), **SIZES)
    untouched = chunk_ids(migrated_conn, 9997)
    with open(raw_dir / "rfc9999.txt", "a") as f:
        f.write("\n\nA.2.  Extra\n\n   More text.\n")
    summary = ingest(migrated_conn, ENTRIES, raw_dir, FakeEmbedder(), **SIZES)
    assert summary.ingested == [9999]
    assert summary.unchanged == [9997]
    assert chunk_ids(migrated_conn, 9997) == untouched


def test_reingests_when_chunking_changes(migrated_conn: psycopg.Connection, raw_dir: Path) -> None:
    ingest(migrated_conn, ENTRIES, raw_dir, FakeEmbedder(), max_tokens=400, overlap_tokens=60)
    before = count(migrated_conn, "SELECT count(*) FROM chunks")
    summary = ingest(
        migrated_conn, ENTRIES, raw_dir, FakeEmbedder(), max_tokens=5, overlap_tokens=60
    )
    assert summary.ingested == [9999, 9997]
    assert count(migrated_conn, "SELECT count(*) FROM chunks") > before


def test_removed_from_list(migrated_conn: psycopg.Connection, raw_dir: Path) -> None:
    ingest(migrated_conn, ENTRIES, raw_dir, FakeEmbedder(), **SIZES)
    summary = ingest(migrated_conn, ENTRIES[:1], raw_dir, FakeEmbedder(), **SIZES)
    assert summary.removed == [9997]
    assert count(migrated_conn, "SELECT count(*) FROM documents WHERE rfc_number = 9997") == 0
    assert chunk_ids(migrated_conn, 9997) == []


def test_crash_keeps_whole_documents(migrated_conn: psycopg.Connection, raw_dir: Path) -> None:
    with pytest.raises(RuntimeError, match="boom"):
        ingest(migrated_conn, ENTRIES, raw_dir, FakeEmbedder(fail_on="Datagram"), **SIZES)
    assert len(chunk_ids(migrated_conn, 9999)) > 0
    assert count(migrated_conn, "SELECT count(*) FROM documents WHERE rfc_number = 9997") == 0
    summary = ingest(migrated_conn, ENTRIES, raw_dir, FakeEmbedder(), **SIZES)
    assert summary.ingested == [9997]


def test_missing_raw_file(migrated_conn: psycopg.Connection, raw_dir: Path) -> None:
    (raw_dir / "rfc9997.txt").unlink()
    with pytest.raises(FileNotFoundError, match="rfc9997.txt"):
        ingest(migrated_conn, ENTRIES, raw_dir, FakeEmbedder(), **SIZES)
    assert count(migrated_conn, "SELECT count(*) FROM documents") == 0


def test_not_migrated(db_conn: psycopg.Connection, raw_dir: Path) -> None:
    with pytest.raises(NotMigratedError, match="make migrate"):
        ingest(db_conn, ENTRIES, raw_dir, FakeEmbedder(), **SIZES)


def test_other_model_refused(migrated_conn: psycopg.Connection, raw_dir: Path) -> None:
    migrated_conn.execute("INSERT INTO embedding_meta (model, dim) VALUES ('other/model', 384)")
    migrated_conn.commit()
    with pytest.raises(SchemaMismatchError):
        ingest(migrated_conn, ENTRIES, raw_dir, FakeEmbedder(), **SIZES)
    assert count(migrated_conn, "SELECT count(*) FROM documents") == 0
