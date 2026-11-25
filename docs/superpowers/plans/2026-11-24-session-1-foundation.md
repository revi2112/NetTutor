# Session 1: Foundation (setup, scaffold, schema) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A git repo with a typed Python 3.12 project, Postgres+pgvector in Docker, a migrated schema, and a FastAPI `/health` endpoint, where `make db-up && make check` passes.

**Architecture:** The app runs natively via uv and talks to a single `pgvector/pgvector:pg16` container. Schema changes are plain SQL files applied in order by a ~50-line runner that records them in a `schema_migrations` table. The embedding dimension is substituted into the SQL from config at migration time, and checked against config at app startup.

**Tech Stack:** Python 3.12, uv, FastAPI, uvicorn, psycopg 3, pydantic v2, pydantic-settings, pytest, ruff, mypy, Docker Compose, Postgres 16 + pgvector.

**Spec:** `docs/superpowers/specs/2026-11-24-nettutor-v2-design.md` (amends `nettutor-claude-code-tasks.md`, Tasks 0–2)

## Global Constraints

- Python `>=3.12,<3.13`, managed with uv. No LangChain/LlamaIndex, ever.
- Config only via env vars (pydantic-settings); no secrets in code. Dev DB credentials `nettutor`/`nettutor` live only in `.env.example` and compose defaults.
- Typed code: `mypy --strict` on `app/`. Small modules. Every feature has tests.
- Compose runs **only** Postgres (`pgvector/pgvector:pg16`), healthcheck + named volume, port 5432. No `ollama` service.
- Config names and defaults exactly: `DATABASE_URL`, `ANTHROPIC_API_KEY` (optional), `LLM_PROVIDER=anthropic|fake` (default `anthropic`), `LLM_MODEL=claude-haiku-5-5`, `JUDGE_MODEL=claude-sonnet-5-5`, `EMBED_MODEL=BAAI/bge-small-en-v1.5`, `EMBED_DIM=384`, `RETRIEVAL_MODE=vector|keyword|hybrid` (default `hybrid`), `TOP_K=6`, `ON_TOPIC_THRESHOLD=0.5`. No `OPENAI_API_KEY`, no `EMBED_PROVIDER`.
- Don't add dependencies a later session needs (no `anthropic`, `fastembed`, `pgvector` adapter yet).
- `make check` = ruff lint + ruff format check + mypy + pytest. A task is done only when it passes.
- Commit messages end with: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`

## Review Focus

1. **Postgres not running when the app starts** → the app still starts, logs a warning, and `/health` returns 503 (not a crash at import or startup). Test in Task 4.
2. **A migration file with an error** → nothing from that file is applied and it is not recorded, so fixing it and re-running works. Test in Task 3.
3. **`EMBED_DIM` changed after the schema was created** → app refuses to start with a message naming both dimensions and saying to re-ingest. Test in Task 4.
4. **`/health` when the DB is unreachable** → the response body never contains the DB password or full `DATABASE_URL`. Test in Task 2.
5. **No `ANTHROPIC_API_KEY` set** → settings load fine (the key is only needed from session 5). Test in Task 1.

---

### Task 0: Repo, tooling, CLAUDE.md, README

**Files:**
- Create: `.gitignore`, `pyproject.toml`, `Makefile`, `CLAUDE.md`, `README.md`, `app/__init__.py`, `tests/__init__.py`, `tests/test_smoke.py`
- Create empty packages (each with `__init__.py`): `app/api`, `app/db`, `app/ingest`, `app/retrieval`, `app/llm`, `app/qa`, `app/quiz`, `app/observability`; empty dirs with `.gitkeep`: `scripts/`, `eval/`, `web/`

**Interfaces:**
- Produces: `make install|dev|test|lint|check|db-up|ingest|eval`; package `app`.

- [ ] **Step 1:** `git init -b main`, commit the existing `nettutor-claude-code-tasks.md`, `docs/superpowers/specs/…`, and this plan as `docs: add task list, v2 design, session 1 plan`. Then `git switch -c session-1-foundation`.
- [ ] **Step 2:** Write `pyproject.toml`: project `nettutor`, `requires-python = ">=3.12,<3.13"`, deps `fastapi`, `uvicorn[standard]`, `psycopg[binary]`, `pydantic`, `pydantic-settings`; dev group `pytest`, `httpx`, `ruff`, `mypy`. Tool config: ruff line-length 100, rules `E,F,I,UP,B`; mypy `strict = true`, `files = ["app"]`, pydantic plugin; pytest `testpaths = ["tests"]`, marker `db: needs the compose Postgres`.
- [ ] **Step 3:** Write `Makefile`: `install` → `uv sync`; `dev` → `uv run uvicorn app.api.main:app --reload`; `test` → `uv run pytest`; `lint` → `uv run ruff check . && uv run ruff format --check .`; `typecheck` → `uv run mypy`; `check` → `lint typecheck test`; `db-up` → `docker compose up -d --wait`; `db-down` → `docker compose down`; `migrate` → `uv run python -m app.db.migrate`; `ingest` and `eval` → print `not implemented yet (session 3 / session 4)` and `exit 1`.
- [ ] **Step 4:** Write `tests/test_smoke.py::test_package_imports` (`import app` succeeds). Run `make install && make check`. Expected: all pass.
- [ ] **Step 5:** Write `CLAUDE.md` with the content the source Task 0 lists, amended by the spec: Claude via the `anthropic` SDK (no Ollama/OpenAI), local fastembed embeddings, Postgres+pgvector, the 9-session plan, "run `make check` before saying a task is done", and "the owner must be able to explain every change: prefer plain code". Write `README.md` stub: one paragraph saying this is v2 of a CS course team project, rebuilt independently, linking https://github.com/revi2112/Agent-Based-Tutor_Quiz-Bot, and a "Status: in progress" line. `.gitignore`: `.venv/`, `__pycache__/`, `.env`, `.mypy_cache/`, `.ruff_cache/`, `.pytest_cache/`, `data/raw/`.
- [ ] **Step 6:** Commit `chore: scaffold project, tooling, CLAUDE.md`.

### Task 1: Settings

**Files:**
- Create: `app/config.py`, `.env.example`, `tests/test_config.py`

**Interfaces:**
- Produces: `class Settings(BaseSettings)` with fields per Global Constraints (`anthropic_api_key: SecretStr | None = None`, `llm_provider: Literal["anthropic", "fake"]`, `retrieval_mode: Literal["vector", "keyword", "hybrid"]`, `embed_dim: int` with `gt=0`, `database_url: str` default `postgresql://nettutor:nettutor@localhost:5432/nettutor`), reading `.env`; `def get_settings() -> Settings` cached with `functools.lru_cache`.

- [ ] **Step 1: Write failing tests** in `tests/test_config.py` (use `monkeypatch` to set/clear env; construct `Settings(_env_file=None)` so a local `.env` can't interfere):
  - `test_defaults`: `llm_model == "claude-haiku-5-5"`, `judge_model == "claude-sonnet-5-5"`, `embed_model == "BAAI/bge-small-en-v1.5"`, `embed_dim == 384`, `retrieval_mode == "hybrid"`, `top_k == 6`.
  - `test_api_key_optional`: with `ANTHROPIC_API_KEY` unset, `Settings().anthropic_api_key is None`.
  - `test_api_key_not_in_repr`: with it set to `"sk-secret"`, `"sk-secret" not in repr(Settings())`.
  - `test_invalid_provider_rejected`: `LLM_PROVIDER=ollama` raises `ValidationError`.
  - `test_embed_dim_from_env`: `EMBED_DIM=768` → `768`; `EMBED_DIM=0` raises `ValidationError`.
- [ ] **Step 2:** Run `uv run pytest tests/test_config.py -v`. Expected: FAIL (module not found).
- [ ] **Step 3:** Implement `app/config.py`; write `.env.example` listing every variable with its default and `ANTHROPIC_API_KEY=` blank.
- [ ] **Step 4:** Run `make check`. Expected: PASS.
- [ ] **Step 5:** Commit `feat: add env-based settings`.

### Task 2: Postgres in Docker and `/health`

**Files:**
- Create: `docker-compose.yml`, `app/db/connection.py`, `app/api/main.py`, `app/api/health.py`, `tests/conftest.py`, `tests/api/__init__.py`, `tests/api/test_health.py`

**Interfaces:**
- Consumes: `get_settings()`.
- Produces: `def connect(database_url: str) -> psycopg.Connection` (autocommit off, `connect_timeout=3`); `def create_app(settings: Settings | None = None) -> FastAPI`; module-level `app = create_app()` in `app/api/main.py`; `GET /health`.
- Test fixtures (`tests/conftest.py`): `test_database_url` (session scope) — derived from `DATABASE_URL` with the database name `nettutor_test`; drops and recreates that database once per test session via the `postgres` maintenance DB; skips all `db`-marked tests with a clear message if Postgres is unreachable. `client` → `TestClient(create_app(Settings(database_url=test_database_url, _env_file=None)))`.

- [ ] **Step 1:** Write `docker-compose.yml`: service `db`, image `pgvector/pgvector:pg16`, env `POSTGRES_USER/PASSWORD/DB` from `${POSTGRES_USER:-nettutor}` etc., `ports: ["5432:5432"]`, volume `pgdata:/var/lib/postgresql/data`, healthcheck `pg_isready -U nettutor -d nettutor` every 5s. Run `make db-up`. Expected: container `healthy`.
- [ ] **Step 2: Write failing tests** in `tests/api/test_health.py`:
  - `test_health_ok` (marked `db`): `GET /health` → 200, body `{"status": "ok", "db": "ok"}`.
  - `test_health_db_down`: app built with `database_url="postgresql://nettutor:hunter2@localhost:1/nope"` → 503, body `{"status": "degraded", "db": "unreachable"}`, and `"hunter2" not in response.text` and `"localhost:1" not in response.text`.
- [ ] **Step 3:** Run them. Expected: FAIL.
- [ ] **Step 4:** Implement `connect`, `create_app`, and the health route (`SELECT 1`; on `psycopg.OperationalError` return the 503 body and log the error class name only, never the URL).
- [ ] **Step 5:** Run `make check`. Expected: PASS.
- [ ] **Step 6:** Commit `feat: add compose Postgres and /health`.

### Task 3: Migration runner and initial schema

**Files:**
- Create: `app/db/migrate.py`, `app/db/migrations/0001_init.sql`, `tests/db/__init__.py`, `tests/db/test_migrate.py`
- Modify: `tests/conftest.py` (add `migrated_db` fixture: runs `apply_migrations` on the test DB once per session)

**Interfaces:**
- Consumes: `connect()`, `Settings.embed_dim`.
- Produces: `def apply_migrations(conn: psycopg.Connection, embed_dim: int, migrations_dir: Path = DEFAULT_DIR) -> list[str]` returning the filenames applied this run; `python -m app.db.migrate` applies to `DATABASE_URL` and prints them.

Runner behavior: create `schema_migrations(filename text primary key, applied_at timestamptz default now())` if missing; for each `*.sql` in sorted order not yet recorded, replace the literal `{embed_dim}` with the integer and run the file **and** its `schema_migrations` insert in one transaction. Why plain SQL over Alembic (goes in a docstring): no ORM models to autogenerate from, the whole mechanism fits on one screen, and it's easy to explain.

`0001_init.sql`: `CREATE EXTENSION IF NOT EXISTS vector;` then the tables from the source plan's Task 2 — `documents`, `chunks` (`embedding vector({embed_dim})`, `tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED`, `content_hash text UNIQUE NOT NULL`, `document_id` FK `ON DELETE CASCADE`), `quizzes`, `quiz_questions` (`chunk_ids int[]`, FK to quizzes `ON DELETE CASCADE`, `type` checked `IN ('mcq','true_false','open')`) — plus `embedding_meta(id int primary key default 1 check (id = 1), model text not null, dim int not null)`. Indexes: `USING hnsw (embedding vector_cosine_ops)` and `USING gin (tsv)` on `chunks`; unique on `documents.rfc_number`.

- [ ] **Step 1: Write failing tests** in `tests/db/test_migrate.py` (all `db`-marked; each uses a fresh schema-isolated DB or drops tables in setup):
  - `test_creates_all_tables`: after applying, `information_schema.tables` includes `documents, chunks, quizzes, quiz_questions, embedding_meta, schema_migrations`.
  - `test_idempotent`: second call returns `[]`.
  - `test_embedding_dim_from_config`: apply with `embed_dim=8`; `SELECT atttypmod FROM pg_attribute WHERE attrelid='chunks'::regclass AND attname='embedding'` → `8`.
  - `test_indexes_exist`: `pg_indexes.indexdef` for `chunks` contains one `hnsw` with `vector_cosine_ops` and one `gin`.
  - `test_tsv_generated`: insert a document and a chunk with text `"TCP three-way handshake"`; `tsv @@ to_tsquery('english','handshake')` is true.
  - `test_content_hash_unique`: inserting two chunks with the same `content_hash` raises `psycopg.errors.UniqueViolation`.
  - `test_failed_migration_not_recorded`: using a `tmp_path` dir containing `0001_ok.sql` (creates table `a`) and `0002_bad.sql` (`CREATE TABLE b (...); SELEC 1;`), `apply_migrations` raises; table `a` exists and is recorded, table `b` does not exist, `0002_bad.sql` is not in `schema_migrations`.
- [ ] **Step 2:** Run `uv run pytest tests/db -v`. Expected: FAIL.
- [ ] **Step 3:** Implement `apply_migrations` and `0001_init.sql`.
- [ ] **Step 4:** Run `make check`, then `make migrate` against the dev DB. Expected: PASS; prints `0001_init.sql`; a second `make migrate` prints nothing applied.
- [ ] **Step 5:** Commit `feat: add SQL migration runner and initial schema`.

### Task 4: Startup schema check

**Files:**
- Create: `app/db/schema_check.py`, `tests/db/test_schema_check.py`
- Modify: `app/api/main.py` (FastAPI lifespan calls the check)

**Interfaces:**
- Consumes: `connect()`, `Settings.embed_model`, `Settings.embed_dim`, migrated schema.
- Produces: `class SchemaMismatchError(RuntimeError)`; `def check_schema(conn: psycopg.Connection, embed_model: str, embed_dim: int) -> None`. Session 3 will write the `embedding_meta` row; this task only reads it.

Behavior: raise `SchemaMismatchError` if the `chunks.embedding` column dimension ≠ `embed_dim`, or if an `embedding_meta` row exists whose `model`/`dim` differ from config. Message names the configured and stored values and says: "re-run migrations on a fresh database and re-ingest". An empty `embedding_meta` is fine. In the lifespan: if Postgres is unreachable, log a warning and continue (so `/health` can report it); if `SchemaMismatchError`, let it propagate so startup fails.

- [ ] **Step 1: Write failing tests:**
  - `test_ok_when_meta_empty` (db): migrated with 384, `check_schema(conn, "BAAI/bge-small-en-v1.5", 384)` returns `None`.
  - `test_column_dim_mismatch` (db): migrated with 384, check with `768` raises `SchemaMismatchError` whose message contains `"384"` and `"768"`.
  - `test_meta_model_mismatch` (db): insert meta `("other/model", 384)`; check with `"BAAI/bge-small-en-v1.5"` raises, message contains both model names.
  - `test_startup_fails_on_mismatch` (db): `with TestClient(create_app(Settings(..., embed_dim=768)))` raises `SchemaMismatchError`.
  - `test_startup_survives_db_down`: `with TestClient(create_app(Settings(database_url="postgresql://x:y@localhost:1/z", _env_file=None))) as c:` → `c.get("/health").status_code == 503`.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Implement `check_schema` and the lifespan hook.
- [ ] **Step 4:** Run `make db-up && make check`. Expected: PASS. Run `make dev` and `curl localhost:8000/health`. Expected: `{"status":"ok","db":"ok"}`.
- [ ] **Step 5:** Commit `feat: check embedding schema against config at startup`.

---

**Session done when:** `make db-up && make check` passes from a clean clone (after `make install` and `make migrate`), and the owner has read the session's diff (`git log -p main..session-1-foundation`) before merging into `main`.
