from pathlib import Path

import pytest
from pydantic import ValidationError

from app.ingest.rfc_list import RfcEntry, load_rfc_list


def test_committed_list_loads() -> None:
    entries = load_rfc_list()
    numbers = [e.number for e in entries]
    assert len(entries) >= 30
    assert {9293, 768, 826, 8446} <= set(numbers)
    assert len(numbers) == len(set(numbers))


def test_entry_urls() -> None:
    entry = RfcEntry(number=768, title="UDP")
    assert entry.filename == "rfc768.txt"
    assert entry.txt_url == "https://www.rfc-editor.org/rfc/rfc768.txt"
    assert entry.html_url == "https://www.rfc-editor.org/rfc/rfc768"


def test_duplicate_number_rejected(tmp_path: Path) -> None:
    path = tmp_path / "list.yaml"
    path.write_text("rfcs:\n  - {number: 768, title: UDP}\n  - {number: 768, title: UDP again}\n")
    with pytest.raises(ValueError, match="duplicate RFC number: 768"):
        load_rfc_list(path)


def test_missing_title_rejected(tmp_path: Path) -> None:
    path = tmp_path / "list.yaml"
    path.write_text("rfcs:\n  - {number: 768}\n")
    with pytest.raises(ValidationError):
        load_rfc_list(path)
