import pytest

from app.retrieval.rrf import rrf


def test_rrf_hand_made() -> None:
    fused = rrf([[1, 2, 3], [3, 1, 4]], k=60)
    assert [chunk_id for chunk_id, _ in fused] == [1, 3, 2, 4]
    assert fused[0][1] == pytest.approx(1 / 61 + 1 / 62)


def test_rrf_single_list_keeps_order() -> None:
    assert [c for c, _ in rrf([[5, 9, 7]])] == [5, 9, 7]


def test_rrf_ties_broken_by_id() -> None:
    assert [c for c, _ in rrf([[2], [1]])] == [1, 2]


def test_rrf_empty() -> None:
    assert rrf([]) == []
    assert rrf([[], []]) == []
