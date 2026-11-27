"""Text embeddings, computed locally with fastembed (ONNX runtime, no torch).

Local because it is free, needs no second API account (Anthropic has no embeddings API),
and bge-small takes milliseconds per text on a laptop. Vectors are L2-normalized so that
cosine similarity is just a dot product, which is what pgvector's `<=>` assumes anyway.
"""

from collections.abc import Sequence
from typing import Any, Protocol

import numpy as np
import numpy.typing as npt
from fastembed import TextEmbedding
from tokenizers import Tokenizer

Vector = npt.NDArray[np.float32]

BATCH_SIZE = 64


class Embedder(Protocol):
    model_name: str
    dim: int

    def embed_documents(self, texts: Sequence[str]) -> list[Vector]: ...

    def embed_query(self, text: str) -> Vector: ...

    def count_tokens(self, text: str) -> int: ...


def normalize(v: npt.NDArray[Any]) -> Vector:
    """Scale to unit length (as float32); a zero vector is returned unchanged."""
    arr: Vector = np.asarray(v, dtype=np.float32)
    norm = float(np.linalg.norm(arr))
    if norm == 0.0:
        return arr
    unit: Vector = (arr / norm).astype(np.float32)
    return unit


class FastEmbedEmbedder:
    def __init__(self, model_name: str, dim: int, cache_dir: str | None = None) -> None:
        self._model = TextEmbedding(model_name, cache_dir=cache_dir)
        actual = self._model.embedding_size
        if actual != dim:
            raise ValueError(f"{model_name} produces {actual}-d vectors but EMBED_DIM is {dim}")
        self.model_name = model_name
        self.dim = dim
        # The ONNX model behind TextEmbedding holds the HuggingFace tokenizer it uses; fastembed
        # only declares it on that subclass, hence the ignore.
        self._tokenizer: Tokenizer = self._model.model.tokenizer  # type: ignore[attr-defined]

    def embed_documents(self, texts: Sequence[str]) -> list[Vector]:
        return [normalize(v) for v in self._model.passage_embed(list(texts), batch_size=BATCH_SIZE)]

    def embed_query(self, text: str) -> Vector:
        # bge models expect an instruction prefix on queries; query_embed adds it.
        return normalize(next(iter(self._model.query_embed(text))))

    def count_tokens(self, text: str) -> int:
        """Tokens the model sees for `text`, not counting [CLS]/[SEP]."""
        return len(self._tokenizer.encode(text, add_special_tokens=False).ids)
