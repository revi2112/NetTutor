"""App settings, read only from environment variables (and an optional .env file)."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://nettutor:nettutor@localhost:5433/nettutor"

    anthropic_api_key: SecretStr | None = None
    llm_provider: Literal["anthropic", "fake"] = "anthropic"
    llm_model: str = "claude-haiku-5-5"
    judge_model: str = "claude-sonnet-5-5"

    embed_model: str = "BAAI/bge-small-en-v1.5"
    embed_dim: int = Field(default=384, gt=0)

    retrieval_mode: Literal["vector", "keyword", "hybrid"] = "hybrid"
    top_k: int = Field(default=6, gt=0)
    on_topic_threshold: float = 0.5


@lru_cache
def get_settings() -> Settings:
    return Settings()
