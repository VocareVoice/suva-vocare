install:
	uv sync

load:
	uv run suva load
	uv run suva import-triage data/results/triage_2026q2.jsonl
	uv run suva import-classification data/results/classification_2025q4_2026q1.jsonl
	uv run suva import-classification data/results/classification_2026q2.jsonl
	uv run suva import-summaries data/results/summaries_2026q2.jsonl

triage:
	uv run suva triage

classify:
	uv run suva classify

summarize:
	uv run suva summarize-relevant

run:
	uv run suva serve

lint:
	uv run ruff check .
	uv run ruff format --check .

.PHONY: install load triage classify summarize run lint
