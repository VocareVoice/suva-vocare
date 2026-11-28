# Hack Apertus Zurich — Challenge Partner: Suva

## 🎯 The Challenge

### Identification of relevant Federal Court judgements and preparation of a legal summary

`Add your team name`
<br>
<br>

Template repository for [Hack Apertus](https://hackapertus.ch/) submissions.
Every project keeps the same layout, so organizers and judges find the same
things in the same place.

Submissions must use the v1.5 Apertus model family.
The submission must comply with the [HackApertus T&C](https://hackapertus.ch/terms-and-conditions) and the [model and challenge requirements](https://hackapertus.notion.site/zurich-challenges-model-requirements)


## 🔧 Resources & Tools

Check our resources & tools page for more information:
[Resources & Tools](https://hackapertus.notion.site/zurich-resources-tools)

| Models           | URL                                      |
|------------------|------------------------------------------|
| Apertus v1.5 8B  | [huggingface.co/swiss-ai/Apertus-v1.5-8B](https://huggingface.co/swiss-ai/Apertus-v1.5-8B)  |
| Apertus v1.5 70B | [huggingface.co/swiss-ai/Apertus-v1.5-70B](https://huggingface.co/swiss-ai/Apertus-v1.5-70B) |

## The structure

Keep the files and directories as shown below — don't rename or move them.

| Path | What it is |
| --- | --- |
| `README.md` | The challenge description and submission requirements |
| `technical_report.md` | The deeper write-up: architecture, evaluation, limitations |
| `Vocare_Report.pdf` | The technical report as submitted: PDF of `technical_report.md`, A4, 6 pages plus references |
| `challenge_description.md` | Complete Challenge description incl. deliverables 
| `LICENSE` | Apache-2.0 |
| `src/` | Your code |

## Environment

- Include instructions for running the project in your technical report.
- Use the following environment variables:
```
LLM_NAME — name and version of the model
LLM_BASE_URL — endpoint base URL
LLM_API_KEY — your API key
```

## Running it

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/). Copy `.env.example` to `.env` and fill in the three `LLM_*` variables.
Every LLM step (triage, classification, summaries, the agent, the evaluation judge) uses `LLM_NAME`,
the model id as your endpoint names it: `apertus-v1-5-70b` on the gateway we used (also the default
when `LLM_NAME` is empty), `swiss-ai/Apertus-v1.5-70B` on Hugging Face-style gateways. All results
in `data/results/` and `docs/` come from the regular 70B model; the app warns when `LLM_NAME` names a
thinking variant.

```sh
make install   # uv sync
make load      # ingest data/corpus/rulings.jsonl.gz and the committed triage, classification and summary results
make triage    # score every ruling not triaged with the current prompt yet (Apertus)
make classify  # classify every ruling not classified with the current prompt yet (Apertus)
make summarize # DE + FR summaries and headlines of every relevant ruling without one yet, best first (Apertus)
make run       # API + UI on http://127.0.0.1:8000 (API docs at /docs)
make lint      # ruff
```

`uv run suva summarize 8C_129/2025` summarises a single ruling in German and French;
`uv run suva summarize-relevant [--from ... --to ...] [--limit 10]` summarises every ruling with a
triage score of at least 28 (`triage.RELEVANCE_THRESHOLD`) that has no summary of the current
prompt version, highest score first; `--limit N` takes the N highest-scored rulings and skips those already summarised, so after
a new triage `uv run suva summarize-relevant --from 2026-04-01 --to 2026-06-30 --limit 30`
writes only what the new top 30 lacks. Each summary run also
writes a one-line headline per language (`headline_de` / `headline_fr` in the API), and
`uv run suva headline-relevant` writes only the headlines, at a fraction of the cost.
`export-summaries` / `import-summaries` work like their triage counterparts;
`data/results/summaries_2026q2.jsonl` holds the summaries and headlines of every April-June 2026
ruling with a triage score of at least 50. How the summary writer works and how it scores:
`docs/eval_summaries.md`; the style it writes: `docs/style_guide.md`, section 11.

For UI work without the corpus or an LLM, `DB_PATH=data/demo.db uv run suva load --demo` loads 14 real
rulings with hand-written demo triage and Suva's reference summaries (marked as demo data).

Triage (`triage.py`, results and metrics in `docs/eval_triage.md`) runs in two stages: a
keyword prior from subject, statutes and parties drops rulings without an accident-insurance
link, and a gate drops decisions that do not rule on the merits (inadmissible, struck off,
single judge; sections from `segment.py`); then Apertus rates the rest and explains each rating
in German and in French.
`uv run suva triage --from 2026-04-01 --to 2026-06-30` scores
a period (resumable, responses cached), `uv run suva export-triage PATH --from ... --to ...`
writes the results as JSONL and `uv run suva import-triage PATH` loads them.
`data/results/triage_2026q2.jsonl` holds the April-June 2026 triage and
`data/results/triage_2025q4_2026q1.jsonl` the labelled Q4 2025 / Q1 2026 period, so the UI works
without calling Apertus.

Classification (`classify.py`, results in `docs/eval_classification.md`) sorts every ruling into a
closed two-level taxonomy, shown in the UI as badges and filters in German and French: the
insurance branch (UVG, IVG, MVG, ATSG, or outside social insurance) and a legal category (one
primary, up to two secondary, e.g. adequate causality or degree of invalidity). Statutes cited,
the outcome and flags (five-judge panel, public deliberation, cited as intended for publication)
are read from the text without an LLM. Every ruling of the social-law divisions (dockets 8x and
9x) is classified by Apertus 70B with enum-constrained JSON; every other ruling is outside social
insurance by its division.
`uv run suva classify --from ... --to ...` classifies a period (resumable, parallel),
`export-classification` / `import-classification` work like their triage counterparts, and
`data/results/classification_*.jsonl` hold the results for October 2025 to June 2026.

The relevance list for the challenge's recall / F2 evaluation is in `deliverables/`:
`uv run suva export-relevant deliverables/relevant_q2_2026 --from 2026-04-01 --to 2026-06-30`
writes every ruling with a triage score of at least 28 (the cut-off that maximises F2 on the
labelled period, `python -m suva.eval.cutoff`), highest score first, as one comma-separated line
(`.txt`) and as a table (`.csv`); `--by publication` selects by publication date instead.
`deliverables/README.md` explains the cut-off, the expected F2 and both variants.

`data/corpus/rulings.jsonl.gz` holds every Federal Supreme Court ruling decided 2025-10-01 to
2026-06-30, fetched from the [entscheidsuche.ch](https://entscheidsuche.ch) mirror of bger.ch.
Refresh or extend it with `uv run python -m suva.fetch --from 2026-04-01 --to 2026-06-30`, which
caches raw downloads under `data/raw/` and replaces the corpus records in that date range.
`uv run python -m suva.fetch.published --until 2026-07-03` then sets each record's
`publication_date` from the mirror's crawl log (empty for rulings published after `--until`).
The app and the `--from` / `--to` options select rulings by decision date.

With Docker: `cp .env.example .env`, fill in the `LLM_*` variables, then `docker compose up --build`
serves on http://127.0.0.1:8000, with `./data` mounted as the database and corpus directory.
The first start builds `data/suva.db` like `make load` (about 30 seconds); later starts reuse it.
Any other command runs in the same container, e.g. `docker compose run --rm api suva summarize 8C_129/2025`.

Code lives in `src/suva/`: `config.py` (settings from env / `.env`), `llm.py` (OpenAI-compatible
Apertus client with an on-disk response cache), `db.py` (SQLite + FTS5 knowledge base),
`triage.py`, `classify.py` and `summarize.py` (LLM steps), `segment.py` (parts of a ruling), `api.py` (FastAPI), `web/` (frontend), `fetch/`
(ruling crawler), `agent/` (legal assistant), `laws.py` (UVG, ATSG and UVV from Fedlex), `eval/` (scorers).
Architecture, target deployment, use of Apertus and evaluation: `technical_report.md`, with the
diagram in `docs/architecture.svg`.

Evaluation: `docs/style_guide.md` is the house style for the DE/FR summaries and the relevance
signals, derived from Suva's examples in `judgements/`. `data/eval/` holds the parsed examples,
the labelled Q4 2025 / Q1 2026 relevance list, the hold-out split, the DE/FR glossary and the full
text of the 55 example rulings (`example_rulings.jsonl.gz`, 23 of them predate the corpus).

```sh
uv run python -m suva.eval.examples          # re-parse judgements/ into data/eval/
uv run python -m suva.eval.score_summaries generated.jsonl [--judge]   # vs. hold-out summaries
uv run python -m suva.eval.score_triage triage.jsonl [--threshold 0.5] # vs. relevance list
uv run python -m suva.eval.score_classification       # vs. topic labels of the 55 examples
```

Feedback loop: the experts' score corrections and edited summaries feed a human-supervised
review, not the prompts directly. `uv run suva feedback-export --out feedback.json` writes them
as JSON (no LLM), the `feedback-review` skill (`.claude/skills/feedback-review/SKILL.md`) has a
coding agent draft a report with suggested prompt changes, and a developer applies and
evaluates the ones the team picks. Workflow and diagram: `docs/feedback_loop.md`; example
report (synthetic corrections): `docs/examples/feedback_review_example.md`.

## 📦 Submission Requirements & Deliverables

The submission must:
1. follow the template repo and include all prerequisite files and definitions
2. run end-to-end when judges try to run it

### Git repo (URL)
- Create your repo from this template (**Use this template**).
- Keep the layout as it is: don't rename or move its files.
- Set the repo to PUBLIC (Settings --> Collaborators --> Manage Visibility)
- Submit the URL of YOUR Git repo (keep it to 'public').

### Technical Report (pdf)
- Update [technical_report.md](technical_report.md) in this repository with all the details for your submission.
- Upload a pdf of your technical report to the root of the repo, named as `TeamName_Report.pdf`.
- Format: pdf, max. 6 pages w/o references
- Submit the pdf of the technical report.

### Demo video (URL)
- Max. 2 min demo video of your prototype
- Add the link to the **Demo** field at the top of [technical_report.md](technical_report.md)
- Submit the URL of the video.

### Pitch deck (pdf)
- Max. 10 slides

## Getting started

1. Click **Use this template** to create your own repository.

## License

All Hack Apertus projects are open-sourced. Please check our Terms & Conditions for specific licensing details (6. What you build is open source): https://hackapertus.ch/terms-and-conditions

## Support

### FAQ
💡 https://hackapertus.ch/faq

### Contact

💬 In case you have questions, join the conversation on Discord. Alternatively, send an email to “hello@hackapertus.ch”.
