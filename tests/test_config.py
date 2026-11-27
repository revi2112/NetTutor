import pytest
from pydantic import ValidationError

from app.config import Settings

ENV_VARS = [
    "DATABASE_URL",
    "ANTHROPIC_API_KEY",
    "LLM_PROVIDER",
    "LLM_MODEL",
    "JUDGE_MODEL",
    "EMBED_MODEL",
    "EMBED_DIM",
    "RETRIEVAL_MODE",
    "TOP_K",
    "ON_TOPIC_THRESHOLD",
    "EMBED_CACHE_DIR",
    "CHUNK_MAX_TOKENS",
    "CHUNK_OVERLAP_TOKENS",
    "RRF_K",
    "RETRIEVAL_CANDIDATES",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def make() -> Settings:
    return Settings(_env_file=None)  # type: ignore[call-arg]


def test_defaults() -> None:
    s = make()
    assert s.llm_model == "claude-haiku-5-5"
    assert s.judge_model == "claude-sonnet-5-5"
    assert s.embed_model == "BAAI/bge-small-en-v1.5"
    assert s.embed_dim == 384
    assert s.retrieval_mode == "hybrid"
    assert s.top_k == 6
    assert s.embed_cache_dir == ".cache/fastembed"
    assert s.chunk_max_tokens == 400
    assert s.chunk_overlap_tokens == 60
    assert s.rrf_k == 60
    assert s.retrieval_candidates == 50


def test_api_key_optional() -> None:
    assert make().anthropic_api_key is None


def test_api_key_not_in_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-secret")
    s = make()
    assert "sk-secret" not in repr(s)
    assert s.anthropic_api_key is not None
    assert s.anthropic_api_key.get_secret_value() == "sk-secret"


def test_invalid_provider_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    with pytest.raises(ValidationError):
        make()


def test_embed_dim_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMBED_DIM", "768")
    assert make().embed_dim == 768
    monkeypatch.setenv("EMBED_DIM", "0")
    with pytest.raises(ValidationError):
        make()


def test_blank_api_key_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    assert make().anthropic_api_key is None


def test_on_topic_threshold_bounds(monkeypatch: pytest.MonkeyPatch) -> None:
    for bad in ("-0.1", "1.5"):
        monkeypatch.setenv("ON_TOPIC_THRESHOLD", bad)
        with pytest.raises(ValidationError):
            make()
