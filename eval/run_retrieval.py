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
from eval.metrics import ModeScores, Section, off_topic_rates, score_mode

RESULTS_PATH = Path("eval/results/retrieval.md")
THRESHOLDS = [round(0.50 + 0.05 * i, 2) for i in range(9)]  # 0.50 ... 0.90
MODES: tuple[Mode, ...] = get_args(Mode)


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
) -> RetrievalReport:
    on_topic = [q for q in questions if not q.off_topic]
    off_topic = [q for q in questions if q.off_topic]

    scores: dict[Mode, ModeScores] = {}
    on_sims: list[float | None] = []
    for mode in MODES:
        results = []
        for q in on_topic:
            r = retrieve(conn, embedder, q.question, mode=mode, k=k_candidates, threshold=0.0)
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


def render_markdown(report: RetrievalReport, *, golden_sha256: str, commit: str) -> str:
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
    for threshold, refusal, answer in report.sweep:
        lines.append(f"| {threshold:.2f} | {refusal:.2f} | {answer:.2f} |")
    lines += ["", f"Golden set sha256: `{golden_sha256}`", f"Commit: `{commit}`", ""]
    return "\n".join(lines)


def _commit() -> str:
    head = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True).stdout
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
        )
    golden_sha = hashlib.sha256(GOLDEN_PATH.read_bytes()).hexdigest()
    text = render_markdown(report, golden_sha256=golden_sha, commit=_commit())
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(text)
    print(text)


if __name__ == "__main__":
    main()
