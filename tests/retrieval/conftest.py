import shutil
from pathlib import Path

import psycopg
import pytest

from app.ingest.pipeline import ingest
from app.ingest.rfc_list import RfcEntry
from tests.fakes import FakeEmbedder

FIXTURES = Path(__file__).parent.parent / "ingest" / "fixtures"


@pytest.fixture
def ingested_conn(migrated_conn: psycopg.Connection, tmp_path: Path) -> psycopg.Connection:
    """The two fixture RFCs (9999 numbered, 9997 unnumbered) ingested with FakeEmbedder."""
    shutil.copy(FIXTURES / "rfc_old_paged.txt", tmp_path / "rfc9999.txt")
    shutil.copy(FIXTURES / "rfc_unnumbered.txt", tmp_path / "rfc9997.txt")
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
