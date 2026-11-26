"""One entry point for search: pick a mode, get hits plus the on-topic decision.

The on-topic check always uses the closest chunk's cosine similarity, whatever the mode, so
one threshold means the same thing everywhere (keyword mode embeds the query just for it).
This replaces the original project's extra LLM call that classified questions.
"""

from dataclasses import dataclass, replace
from typing import Literal

import psycopg

from app.llm.embeddings import Embedder
from app.retrieval.rrf import rrf
from app.retrieval.search import Hit, keyword_search, top_similarity, vector_search

Mode = Literal["vector", "keyword", "hybrid"]


@dataclass(frozen=True)
class Retrieval:
    hits: list[Hit]
    top_similarity: float | None
    on_topic: bool


def retrieve(
    conn: psycopg.Connection,
    embedder: Embedder,
    query: str,
    *,
    mode: Mode,
    k: int,
    threshold: float,
    candidates: int = 50,
    rrf_k: int = 60,
) -> Retrieval:
    query_vec = embedder.embed_query(query)
    best = top_similarity(conn, query_vec)

    if mode == "vector":
        hits = vector_search(conn, query_vec, k)
    elif mode == "keyword":
        hits = keyword_search(conn, query, k)
    else:
        by_vector = vector_search(conn, query_vec, candidates)
        by_keyword = keyword_search(conn, query, candidates)
        found = {h.chunk_id: h for h in by_keyword} | {h.chunk_id: h for h in by_vector}
        fused = rrf([[h.chunk_id for h in by_vector], [h.chunk_id for h in by_keyword]], rrf_k)
        hits = [replace(found[chunk_id], score=score) for chunk_id, score in fused[:k]]

    return Retrieval(
        hits=hits, top_similarity=best, on_topic=best is not None and best >= threshold
    )
