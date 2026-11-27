"""Run every golden question through each retrieval mode and report the scores.

Run: make eval-retrieval  (writes eval/results/retrieval.md)
"""

import hashlib
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import get_args

import psycopg

from app.config import get_settings
from app.db.connection import connect
from app.llm.embeddings import Embedder, FastEmbedEmbedder
from app.retrieval.retrieve import Mode, retrieve
from eval.golden import GOLDEN_PATH, GoldenQuestion, check_answers_exist, load_golden
from eval.metrics import ModeScores, Section, off_topic_rates, pick_threshold, score_mode

RESULTS_PATH = Path("eval/results/retrieval.md")
# bge-small packs top similarities into a narrow band (on-topic and near-miss off-topic
# questions both land around 0.70-0.80), so a 0.05 grid is too coarse to place the cut.
THRESHOLDS = [round(0.60 + 0.01 * i, 2) for i in range(26)]  # 0.60 ... 0.85
MODES: tuple[Mode, ...] = get_args(Mode)
MAX_FALSE_REFUSAL = 0.05


@dataclass
class RetrievalReport:
    scores: dict[Mode, ModeScores]
    sweep: list[tuple[float, float, float]]  # (threshold, false refusal, false answer)
    n_on_topic: int
    n_off_topic: int


def run(
    conn: psycopg.Connection,
    embedder: Embedder,
    questions: Sequence[GoldenQuestion],
    *,
    thresholds: Sequence[float],
    k_candidates: int = 50,
    rrf_k: int = 60,
) -> RetrievalReport:
    on_topic = [q for q in questions if not q.off_topic]
    off_topic = [q for q in questions if q.off_topic]
    if not on_topic or not off_topic:
        raise ValueError("the golden set needs both on-topic and off-topic questions")

    scores: dict[Mode, ModeScores] = {}
    on_sims: list[float | None] = []
    for mode in MODES:
        results = []
        for q in on_topic:
            r = retrieve(
                conn,
                embedder,
                q.question,
                mode=mode,
                k=k_candidates,
                threshold=0.0,
                candidates=k_candidates,
                rrf_k=rrf_k,
            )
            golden: list[Section] = [(a.rfc, a.section) for a in q.answers]
            results.append((golden, r.hits))
            if mode == "vector":
                on_sims.append(r.top_similarity)  # same in every mode
        scores[mode] = score_mode(results)

    off_sims = [
        retrieve(conn, embedder, q.question, mode="vector", k=1, threshold=0.0).top_similarity
        for q in off_topic
    ]
    sweep = [(t, *off_topic_rates(on_sims, off_sims, t)) for t in thresholds]
    return RetrievalReport(scores, sweep, len(on_topic), len(off_topic))


def render_markdown(
    report: RetrievalReport,
    *,
    golden_sha256: str,
    commit: str,
    threshold: float,
    config: dict[str, str],
) -> str:
    lines = [
        "# Retrieval eval",
        "",
        f"{report.n_on_topic} on-topic and {report.n_off_topic} off-topic golden questions.",
        "Recall and MRR are over unique sections (chunks deduplicated by RFC section); a",
        "subsection of a golden section counts as a hit. Chunk R@5 skips the dedup.",
        "",
        "| mode | R@1 | R@3 | R@5 | MRR | chunk R@5 |",
        "|---|---|---|---|---|---|",
    ]
    for mode, s in report.scores.items():
        lines.append(
            f"| {mode} | {s.recall_at[1]:.2f} | {s.recall_at[3]:.2f} | {s.recall_at[5]:.2f} "
            f"| {s.mrr:.3f} | {s.chunk_recall_at_5:.2f} |"
        )
    lines += [
        "",
        "## On-topic threshold (top vector cosine similarity)",
        "",
        "| threshold | false refusal (on-topic refused) | false answer (off-topic answered) |",
        "|---|---|---|",
    ]
    for t, refusal, answer in report.sweep:
        lines.append(f"| {t:.2f} | {refusal:.2f} | {answer:.2f} |")
    pick = pick_threshold(report.sweep, max_false_refusal=MAX_FALSE_REFUSAL)
    rule = f"highest threshold with false refusal <= {MAX_FALSE_REFUSAL:.0%}"
    lines += ["", f"Configured `ON_TOPIC_THRESHOLD` = {threshold:.2f}."]
    if pick is not None and abs(pick - threshold) < 1e-9:
        lines.append(f"It is the rule's pick ({rule}).")
    else:
        shown = "none" if pick is None else f"{pick:.2f}"
        lines.append(f"**Warning:** it does not match the rule's pick ({rule}): {shown}.")
    lines += ["", "## Config", "", "| setting | value |", "|---|---|"]
    lines += [f"| {key} | {value} |" for key, value in config.items()]
    lines += ["", f"Golden set sha256: `{golden_sha256}`", f"Commit: `{commit}`", ""]
    return "\n".join(lines)


def _commit() -> str:
    head = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    # The report itself is the output, so an older copy of it doesn't make the tree dirty.
    dirty = subprocess.run(
        ["git", "status", "--porcelain", "--", ".", f":!{RESULTS_PATH}"],
        capture_output=True,
        text=True,
    ).stdout
    return head + ("-dirty" if dirty.strip() else "")


def main() -> None:
    settings = get_settings()
    embedder = FastEmbedEmbedder(settings.embed_model, settings.embed_dim, settings.embed_cache_dir)
    questions = load_golden()
    with connect(settings.database_url) as conn:
        check_answers_exist(conn, questions)
        report = run(
            conn,
            embedder,
            questions,
            thresholds=THRESHOLDS,
            k_candidates=settings.retrieval_candidates,
            rrf_k=settings.rrf_k,
        )
        (n_chunks,) = conn.execute("SELECT count(*) FROM chunks").fetchone() or (0,)
    config = {
        "chunks in DB": str(n_chunks),
        "embed model": settings.embed_model,
        "chunk max / overlap tokens (current env)": (
            f"{settings.chunk_max_tokens} / {settings.chunk_overlap_tokens}"
        ),
        "retrieval candidates per mode": str(settings.retrieval_candidates),
        "rrf_k": str(settings.rrf_k),
        "top_k (app, not used by the eval)": str(settings.top_k),
    }
    golden_sha = hashlib.sha256(GOLDEN_PATH.read_bytes()).hexdigest()
    text = render_markdown(
        report,
        golden_sha256=golden_sha,
        commit=_commit(),
        threshold=settings.on_topic_threshold,
        config=config,
    )
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(text)
    print(text)


if __name__ == "__main__":
    main()
