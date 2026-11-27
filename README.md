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

```sh
make install   # uv sync
make load      # ingest data/corpus/rulings.jsonl.gz into data/suva.db
make triage    # score every ruling not triaged yet (Apertus)
make run       # API + UI on http://127.0.0.1:8000 (API docs at /docs)
make test      # pytest
make lint      # ruff
```

`uv run suva summarize 8C_129/2025` summarises a single ruling in German and French.

`data/corpus/rulings.jsonl.gz` holds every Federal Supreme Court ruling decided 2025-10-01 to
2026-06-30, fetched from the [entscheidsuche.ch](https://entscheidsuche.ch) mirror of bger.ch.
Refresh or extend it with `uv run python -m suva.fetch --from 2026-04-01 --to 2026-06-30`, which
caches raw downloads under `data/raw/` and replaces the corpus records in that date range.

With Docker: `docker compose up --build` serves on port 8000, with `./data` mounted as the
database and corpus directory. Load the corpus with `docker compose run --rm api suva load`.

Code lives in `src/suva/`: `config.py` (settings from env / `.env`), `llm.py` (OpenAI-compatible
Apertus client with an on-disk response cache), `db.py` (SQLite + FTS5 knowledge base),
`triage.py` and `summarize.py` (LLM steps), `api.py` (FastAPI), `web/` (frontend), `fetch/`
(ruling crawler).

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
