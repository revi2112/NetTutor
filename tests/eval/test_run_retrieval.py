import psycopg
import pytest

from eval.golden import GoldenAnswer, GoldenQuestion, check_answers_exist
from eval.run_retrieval import render_markdown, run
from tests.fakes import FakeEmbedder

pytestmark = pytest.mark.db

THRESHOLDS = [0.5, 0.7, 0.9]


def on_topic(qid: str, question: str, rfc: int, section: str) -> GoldenQuestion:
    return GoldenQuestion(
        id=qid,
        question=question,
        answers=[GoldenAnswer(rfc=rfc, section=section)],
        reference_answer="ref",
    )


def chunk_embed_texts(conn: psycopg.Connection) -> list[tuple[int, str, str]]:
    rows = conn.execute(
        "SELECT d.rfc_number, c.section_id, c.section_title, c.text FROM chunks c"
        " JOIN documents d ON d.id = c.document_id ORDER BY c.id LIMIT 2"
    ).fetchall()
    return [(rfc, sid, f"RFC {rfc} §{sid} {title}\n{text}") for rfc, sid, title, text in rows]


def test_missing_golden_section_is_reported(ingested_conn: psycopg.Connection) -> None:
    with pytest.raises(ValueError, match=r"q1: 9999 §3\.55"):
        check_answers_exist(ingested_conn, [on_topic("q1", "x", 9999, "3.55")])
    check_answers_exist(ingested_conn, [on_topic("q2", "x", 9999, "A")])  # A.1 exists


def test_run_produces_scores_for_every_mode(ingested_conn: psycopg.Connection) -> None:
    questions = [
        on_topic(f"q{i}", text, rfc, sid)
        for i, (rfc, sid, text) in enumerate(chunk_embed_texts(ingested_conn))
    ]
    questions.append(GoldenQuestion(id="off", question="zzz", off_topic=True))
    report = run(ingested_conn, FakeEmbedder(), questions, thresholds=THRESHOLDS)
    assert set(report.scores) == {"vector", "keyword", "hybrid"}
    assert report.scores["vector"].recall_at[1] == 1.0
    assert [row[0] for row in report.sweep] == THRESHOLDS
    assert (report.n_on_topic, report.n_off_topic) == (2, 1)


def test_render_markdown(ingested_conn: psycopg.Connection) -> None:
    questions = [on_topic("q1", "datagrams", 9997, "u1")]
    questions.append(GoldenQuestion(id="off", question="zzz", off_topic=True))
    report = run(ingested_conn, FakeEmbedder(), questions, thresholds=THRESHOLDS)
    text = render_markdown(report, golden_sha256="abc123", commit="deadbee")
    assert "| hybrid |" in text
    assert "abc123" in text
    assert "deadbee" in text
