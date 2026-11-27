"""Reciprocal Rank Fusion: merge several rankings using only ranks, not raw scores.

score(chunk) = sum over rankings of 1 / (k + rank), with rank starting at 1. Ranks are used
because cosine similarities and ts_rank_cd scores are on unrelated scales. The constant k
(60, the value from the original RRF paper) damps the top ranks, so one list putting a
chunk first does not outweigh both lists putting another chunk near the top.
"""

from collections import defaultdict
from collections.abc import Sequence


def rrf(rankings: Sequence[Sequence[int]], k: int = 60) -> list[tuple[int, float]]:
    """Fuse rankings of chunk ids; sorted by score descending, then id (deterministic)."""
    scores: defaultdict[int, float] = defaultdict(float)
    for ranking in rankings:
        for rank, chunk_id in enumerate(ranking, start=1):
            scores[chunk_id] += 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))
