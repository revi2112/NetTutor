.PHONY: install dev test lint typecheck check db-up db-down db-reset migrate fetch ingest eval eval-retrieval

install:
	uv sync

dev:
	uv run uvicorn app.api.main:app --reload

test:
	uv run pytest

lint:
	uv run ruff check .
	uv run ruff format --check .

typecheck:
	uv run mypy

check: lint typecheck test

db-up:
	docker compose up -d --wait

db-down:
	docker compose down

db-reset:
	docker compose down -v
	docker compose up -d --wait
	uv run python -m app.db.migrate

migrate:
	uv run python -m app.db.migrate

fetch:
	uv run python -m scripts.fetch_rfcs

ingest:
	uv run python -m scripts.ingest

eval: eval-retrieval

eval-retrieval:
	uv run python -m eval.run_retrieval
