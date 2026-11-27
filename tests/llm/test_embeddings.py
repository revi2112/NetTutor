import numpy as np
import pytest

from app.llm.embeddings import FastEmbedEmbedder, normalize

MODEL = "BAAI/bge-small-en-v1.5"
CACHE = ".cache/fastembed"


@pytest.fixture(scope="module")
def embedder() -> FastEmbedEmbedder:
    return FastEmbedEmbedder(MODEL, 384, cache_dir=CACHE)


def test_vectors_are_normalized_384d(embedder: FastEmbedEmbedder) -> None:
    vectors = embedder.embed_documents(["TCP handshake", "DNS"])
    assert len(vectors) == 2
    for v in vectors:
        assert v.shape == (384,)
        assert abs(float(np.linalg.norm(v)) - 1.0) < 1e-5
    assert embedder.embed_query("x").shape == (384,)


def test_similar_texts_are_closer(embedder: FastEmbedEmbedder) -> None:
    q = embedder.embed_query("How does TCP open a connection?")
    handshake, bread = embedder.embed_documents(
        ["The three-way handshake: SYN, SYN-ACK, ACK", "Bake the bread for 40 minutes"]
    )
    assert float(q @ handshake) > float(q @ bread)


def test_count_tokens(embedder: FastEmbedEmbedder) -> None:
    assert embedder.count_tokens("") == 0
    text = "RFC 9293 §3.5 Establishing a Connection. The three-way handshake"
    assert embedder.count_tokens(text) == 19


def test_dim_mismatch_rejected() -> None:
    with pytest.raises(ValueError, match="384") as err:
        FastEmbedEmbedder(MODEL, 768, cache_dir=CACHE)
    assert "768" in str(err.value)


def test_normalize() -> None:
    result = normalize(np.array([3, 4], dtype=np.float32))
    assert np.allclose(result, [0.6, 0.8])
    zero = np.zeros(3, dtype=np.float32)
    assert np.array_equal(normalize(zero), zero)
