"""The golden question set (`eval/golden.jsonl`): one JSON object per line.

On-topic questions name the most specific RFC section(s) that answer them and carry a short
reference answer (used to grade answers in session 7). Off-topic questions have neither.
"""

import json
from collections.abc import Sequence
from pathlib import Path

import psycopg
from pydantic import BaseModel, model_validator

GOLDEN_PATH = Path("eval/golden.jsonl")


class GoldenAnswer(BaseModel):
    rfc: int
    section: str


class GoldenQuestion(BaseModel):
    id: str
    question: str
    off_topic: bool = False
    answers: list[GoldenAnswer] = []
    reference_answer: str = ""

    @model_validator(mode="after")
    def _answers_match_kind(self) -> "GoldenQuestion":
        if self.off_topic and self.answers:
            raise ValueError(f"{self.id}: off-topic questions must not have answers")
        if not self.off_topic and not (self.answers and self.reference_answer):
            raise ValueError(f"{self.id}: on-topic questions need answers and a reference_answer")
        return self


def load_golden(path: Path = GOLDEN_PATH) -> list[GoldenQuestion]:
    questions = [
        GoldenQuestion.model_validate(json.loads(line))
        for line in path.read_text().splitlines()
        if line.strip()
    ]
    seen: set[str] = set()
    for q in questions:
        if q.id in seen:
            raise ValueError(f"duplicate golden question id: {q.id}")
        seen.add(q.id)
    return questions


def check_answers_exist(conn: psycopg.Connection, questions: Sequence[GoldenQuestion]) -> None:
    """Fail loudly if a golden section has no chunk (itself or a subsection) in the database."""
    missing: list[str] = []
    for q in questions:
        for a in q.answers:
            row = conn.execute(
                "SELECT 1 FROM chunks c JOIN documents d ON d.id = c.document_id"
                " WHERE d.rfc_number = %s AND (c.section_id = %s OR c.section_id LIKE %s)"
                " LIMIT 1",
                (a.rfc, a.section, a.section + ".%"),
            ).fetchone()
            if row is None:
                missing.append(f"{q.id}: {a.rfc} §{a.section} not in the database")
    if missing:
        raise ValueError("golden answers not found:\n" + "\n".join(missing))
