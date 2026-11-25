# NetTutor v2

A framework-free RAG tutor and quiz engine over IETF networking RFCs. No LangChain/LlamaIndex:
the owner wants to own the retrieval logic and be able to explain every part in interviews.

Design: `docs/superpowers/specs/2026-11-24-nettutor-v2-design.md` (amends `nettutor-claude-code-tasks.md`).
Plans per session: `docs/superpowers/plans/`.

## Stack
- Python 3.12 managed with uv; FastAPI; Postgres 16 + pgvector (psycopg 3); pydantic v2 + pydantic-settings.
- LLM: Claude via the official `anthropic` SDK (answers/quizzes `claude-haiku-5-5`, eval judge
  `claude-sonnet-5-5`). No Ollama, no OpenAI. Don't send `temperature` (current Claude models reject it).
- Embeddings: local fastembed (ONNX, no torch), `BAAI/bge-small-en-v1.5`, 384-d.
- Tooling: pytest, ruff, mypy (strict on `app/`).

## Layout
- `app/` — `api`, `config.py`, `db` (connection, SQL migrations, schema check), `ingest`, `retrieval`,
  `llm`, `qa`, `quiz`, `observability`
- `scripts/`, `eval/`, `tests/`, `web/`

## Local runtime
- `docker-compose.yml` runs only Postgres (`pgvector/pgvector:pg16`). The app runs natively.
- `make db-up`, `make migrate`, `make dev`. Postgres is published on host port 5433 (5432 is often taken by a local install). Tests use a separate `nettutor_test` database.

## Conventions
- Typed code, small modules, every feature has tests (write the failing test first).
- Config only via env vars (`app/config.py`); no secrets in code. See `.env.example`.
- Prefer plain, explainable code over clever abstractions.
- Run `make check` (ruff + mypy + pytest) before saying a task is done.

## Sessions
1 setup/scaffold/schema · 2 fetch+parse RFCs · 3 chunk/embed/ingest · 4 hybrid retrieval + retrieval eval ·
5 LLM layer + /ask · 6 quizzes · 7 answer-quality eval · 8 hardening (security, observability, CI) ·
9 frontend, Docker, README. AWS is parked until after session 9.
