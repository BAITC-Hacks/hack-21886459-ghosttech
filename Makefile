.PHONY: setup dev migrate seed openapi test test-client check security-check

setup:
	uv sync --project backend --locked
	uv run --directory backend --locked python -m app.cli setup

migrate:
	uv run --directory backend --locked python -m app.cli migrate

seed:
	uv run --directory backend --locked python -m app.cli seed

openapi:
	uv run --directory backend --locked python -m app.cli openapi

dev:
	uv run --project backend --locked uvicorn app.main:app --app-dir backend --reload --host 127.0.0.1 --port 8000

test:
	uv run --project backend --locked pytest backend/tests

test-client:
	node --test frontend/tests/api.test.cjs

check:
	uv run --project backend --locked ruff check backend
	uv run --project backend --locked ruff format --check backend

security-check:
	uv run --directory backend --locked python security_check.py
