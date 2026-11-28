install:
	uv sync

load:
	uv run suva load
	uv run suva import-triage data/results/triage_2025q4_2026q1.jsonl
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

summary-files:
	uv run suva export-summary-files --from 2026-06-01 --to 2026-06-30 \
		--out deliverables/summaries_june_2026

submission:
	@test -f deliverables/Vocare_Praecedens_vf.pdf || { echo "deliverables/Vocare_Praecedens_vf.pdf is missing: export the pitch deck to PDF first" >&2; exit 1; }
	@test -f Vocare_Report.pdf || { echo "Vocare_Report.pdf is missing" >&2; exit 1; }
	rm -f deliverables/Vocare_Submission.zip
	zip -j deliverables/Vocare_Submission.zip Vocare_Report.pdf deliverables/Vocare_Praecedens_vf.pdf

test:
	uv run python -m suva.agent.selftest

lint:
	uv run ruff check .
	uv run ruff format --check .

.PHONY: install load triage classify summarize summary-files submission run test lint
