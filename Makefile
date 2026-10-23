.PHONY: setup test lint fmt check

setup:
	uv sync
	git config core.hooksPath .githooks

test:
	uv run pytest -q

lint:
	uv run ruff check .
	uv run mypy src

fmt:
	uv run ruff check --fix .
	uv run ruff format .

check: lint
	uv run ruff format --check .
	uv run pytest -q
