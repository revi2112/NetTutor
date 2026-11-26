"""Section-level retrieval metrics, as defined in the design spec ("Eval metric definitions").

- Retrieved chunks are deduplicated by (rfc, section_id) in rank order before taking the
  top k, so several chunks from one section can't fill the top 5 on their own.
- A hit is a returned section equal to a golden section or a subsection of it, comparing
  dot-separated parts: golden 3.5 matches 3.5.2, but 3.1 does not match 3.10 and u1 does
  not match u10. With several golden sections, any one counts.
- MRR uses the rank of the first hit among the top 10 unique sections (0 if none).
- Chunk-level recall@5 (no dedup) is reported too, for transparency.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from app.retrieval.search import Hit

Section = tuple[int, str]  # (rfc_number, section_id)

RECALL_KS = (1, 3, 5)
MRR_LIMIT = 10


def is_match(golden: Section, returned: Section) -> bool:
    golden_parts = golden[1].split(".")
    returned_parts = returned[1].split(".")
    return golden[0] == returned[0] and returned_parts[: len(golden_parts)] == golden_parts


def unique_sections(hits: Sequence[Hit]) -> list[Section]:
    seen: list[Section] = []
    for h in hits:
        section = (h.rfc_number, h.section_id)
        if section not in seen:
            seen.append(section)
    return seen


def first_hit_rank(
    golden: Sequence[Section], returned: Sequence[Section], limit: int = MRR_LIMIT
) -> int | None:
    """1-based rank of the first returned section that matches any golden section."""
    for rank, section in enumerate(returned[:limit], start=1):
        if any(is_match(g, section) for g in golden):
            return rank
    return None


@dataclass
class ModeScores:
    recall_at: dict[int, float]
    mrr: float
    chunk_recall_at_5: float


def score_mode(results: Sequence[tuple[Sequence[Section], Sequence[Hit]]]) -> ModeScores:
    """Scores over on-topic questions; each item is (golden sections, hits in rank order)."""
    n = len(results)
    hits_at = dict.fromkeys(RECALL_KS, 0)
    reciprocal_ranks = 0.0
    chunk_hits = 0
    for golden, hits in results:
        rank = first_hit_rank(golden, unique_sections(hits))
        for k in RECALL_KS:
            if rank is not None and rank <= k:
                hits_at[k] += 1
        if rank is not None:
            reciprocal_ranks += 1.0 / rank
        top_chunks = [(h.rfc_number, h.section_id) for h in hits[:5]]
        if first_hit_rank(golden, top_chunks) is not None:
            chunk_hits += 1
    return ModeScores(
        recall_at={k: hits_at[k] / n for k in RECALL_KS},
        mrr=reciprocal_ranks / n,
        chunk_recall_at_5=chunk_hits / n,
    )


def off_topic_rates(
    on_topic_sims: Sequence[float | None],
    off_topic_sims: Sequence[float | None],
    threshold: float,
) -> tuple[float, float]:
    """(false-refusal rate on on-topic questions, false-answer rate on off-topic ones)."""

    def answered(sim: float | None) -> bool:
        return sim is not None and sim >= threshold

    false_refusals = sum(not answered(s) for s in on_topic_sims)
    false_answers = sum(answered(s) for s in off_topic_sims)
    return false_refusals / len(on_topic_sims), false_answers / len(off_topic_sims)
