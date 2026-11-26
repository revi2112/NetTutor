import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from eval.golden import load_golden

ON = {
    "id": "q1",
    "question": "How does TCP open a connection?",
    "answers": [{"rfc": 9293, "section": "3.5"}],
    "reference_answer": "With a three-way handshake.",
}
OFF = {"id": "q2", "question": "What's the weather?", "off_topic": True}


def write(tmp_path: Path, *rows: dict[str, object]) -> Path:
    path = tmp_path / "golden.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n\n")
    return path


def test_loads_and_validates(tmp_path: Path) -> None:
    questions = load_golden(write(tmp_path, ON, OFF))
    assert [q.id for q in questions] == ["q1", "q2"]
    assert questions[0].answers[0].section == "3.5"
    assert questions[1].off_topic


def test_on_topic_needs_answers(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        load_golden(write(tmp_path, {**ON, "answers": []}))


def test_off_topic_must_not_have_answers(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        load_golden(write(tmp_path, {**OFF, "answers": [{"rfc": 1, "section": "1"}]}))


def test_duplicate_id(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="q1"):
        load_golden(write(tmp_path, ON, ON))
