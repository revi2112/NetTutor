import pytest

from app.retrieval.search import Hit
from eval.metrics import (
    first_hit_rank,
    is_match,
    off_topic_rates,
    score_mode,
    unique_sections,
)


def hit(rfc: int, section: str, chunk_id: int = 0) -> Hit:
    return Hit(chunk_id, rfc, section, "t", "x", 0.0)


def test_is_match_prefix_rule() -> None:
    assert is_match((9293, "3.5"), (9293, "3.5"))
    assert is_match((9293, "3.5"), (9293, "3.5.2"))
    assert not is_match((9293, "3.5"), (9293, "3"))
    assert not is_match((9293, "3.5"), (9293, "3.50"))
    assert not is_match((9293, "3.5"), (791, "3.5"))
    assert not is_match((1, "3.1"), (1, "3.10"))
    assert not is_match((1, "u1"), (1, "u10"))
    assert is_match((1, "A"), (1, "A.1"))


def test_unique_sections_keeps_first_occurrence() -> None:
    hits = [hit(1, "a"), hit(1, "a"), hit(1, "b"), hit(1, "a"), hit(1, "c")]
    assert unique_sections(hits) == [(1, "a"), (1, "b"), (1, "c")]


def test_first_hit_rank() -> None:
    assert first_hit_rank([(1, "2")], [(1, "1"), (1, "2.3")]) == 2
    assert first_hit_rank([(1, "2")], [(1, "1")]) is None
    eleven = [(1, f"x{i}") for i in range(10)] + [(1, "2")]
    assert first_hit_rank([(1, "2")], eleven, limit=10) is None


def test_score_mode() -> None:
    golden = [(1, "g")]
    q1 = [hit(1, "g")]
    q4 = [hit(1, "a"), hit(1, "b"), hit(1, "c"), hit(1, "g")]
    q_none = [hit(1, "a")]
    scores = score_mode([(golden, q1), (golden, q4), (golden, q_none)])
    assert scores.recall_at == pytest.approx({1: 1 / 3, 3: 1 / 3, 5: 2 / 3})
    assert scores.mrr == pytest.approx((1 + 1 / 4 + 0) / 3)


def test_section_dedup_vs_chunk_recall() -> None:
    hits = [hit(1, "wrong", i) for i in range(5)] + [hit(1, "right", 5)]
    scores = score_mode([([(1, "right")], hits)])
    assert scores.recall_at[5] == 1.0
    assert scores.chunk_recall_at_5 == 0.0


def test_off_topic_rates() -> None:
    assert off_topic_rates([0.9, 0.6, None], [0.7, 0.4], 0.65) == pytest.approx((2 / 3, 1 / 2))
