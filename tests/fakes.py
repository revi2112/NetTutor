"""Test doubles shared across test modules."""

import hashlib
from collections.abc import Sequence

import numpy as np

from app.llm.embeddings import Vector, normalize


class FakeEmbedder:
    """Deterministic random unit vectors per text; word-count tokens; records calls."""

    model_name = "fake/embedder"

    def __init__(self, dim: int = 384, fail_on: str | None = None) -> None:
        self.dim = dim
        self.fail_on = fail_on
        self.calls: list[list[str]] = []

    def _vector(self, text: str) -> Vector:
        seed = int.from_bytes(hashlib.sha256(text.encode()).digest()[:8], "big")
        return normalize(np.random.default_rng(seed).standard_normal(self.dim))

    def embed_documents(self, texts: Sequence[str]) -> list[Vector]:
        self.calls.append(list(texts))
        if self.fail_on is not None and any(self.fail_on in t for t in texts):
            raise RuntimeError("boom")
        return [self._vector(t) for t in texts]

    def embed_query(self, text: str) -> Vector:
        return self._vector(text)

    def count_tokens(self, text: str) -> int:
        return len(text.split())
