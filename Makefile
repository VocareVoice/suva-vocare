install:
	uv sync

load:
	uv run suva load

triage:
	uv run suva triage

run:
	uv run suva serve

test:
	uv run pytest

lint:
	uv run ruff check .
	uv run ruff format --check .

.PHONY: install load triage run test lint
