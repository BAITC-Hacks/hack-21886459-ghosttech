.PHONY: setup dev test check

setup:
	uv sync --project backend --locked

dev:
	uv run --project backend --locked uvicorn app.main:app --app-dir backend --reload --host 127.0.0.1 --port 8000

test:
	uv run --project backend --locked pytest backend/tests

check:
	uv run --project backend --locked ruff check backend
	uv run --project backend --locked ruff format --check backend
