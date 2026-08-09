.PHONY: install run test lint format typecheck check migrate up down

install:
	uv sync --extra dev

run:
	uv run uvicorn app.main:app --reload

test:
	uv run pytest --cov=app --cov-report=term-missing

lint:
	uv run ruff check .

format:
	uv run ruff format .

typecheck:
	uv run mypy app

check: lint typecheck test

migrate:
	uv run alembic upgrade head

up:
	docker compose up --build

down:
	docker compose down -v

