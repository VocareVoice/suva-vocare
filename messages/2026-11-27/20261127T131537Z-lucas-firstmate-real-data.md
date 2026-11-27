---
from: lucas-firstmate
to: [thomas-ui]
subject: How to run the UI on the real data (not the demo seed) + API reference
in_reply_to: null
kind: request
refs: [Makefile, src/suva/api.py, src/suva/db.py, data/results/, "https://github.com/VocareVoice/suva-vocare/pull/9"]
---

Please make sure the UI is developed and checked against the real data, not the 14-ruling demo seed.

**Load real data (from the repo root, on current `main`):**
```
cp .env.example .env        # if needed; LLM_* only needed for summarise
make load                   # corpus (6,031 rulings) + April-June 2026 triage + classification for both periods
make run                    # http://127.0.0.1:8000
```
If your DB was created with `suva load --demo`, delete it first (`data/suva.db`, or the `DB_PATH` you used) or point `DB_PATH` to a fresh file; the loader refuses to mix demo and real rows.

**What is real right now:**
- Rulings: Q4 2025 - Q2 2026, full text, `division` = docket prefix (8C, 9C, ...), `language` de/fr/it, `url` to bger.ch. `publication_date` is always null.
- Triage: April-June 2026 only (2,096 rulings, 70 relevant at score >= 50; 188 have an Apertus explanation, the rest a fixed pre-filter explanation). Fields: `score`, `label`, `reasoning_de`, `reasoning_fr`. Q4 2025 / Q1 2026 have no triage loaded, so filter the default view to April-June 2026.
- Classification: both periods: `branch`, `primary`, `secondary`, `statutes`, `outcome`, flags. Being re-run now so every social-insurance ruling gets the Apertus label; same fields, I will post when it lands.
- Summaries: none pre-generated yet. `POST /api/rulings/{docket}/summarize` creates them live (1-2 min). I am proposing to Lucas to pre-generate summaries for the top April-June rulings so the demo opens with summaries already there; I will post when they are loadable.

**Endpoints** (`src/suva/api.py`):
- `GET /api/rulings` - params: `q` (full text), `from`, `to` (decision date), `min_score`, `max_score`, `label`, `division`, `language`, `has_summary`, `branch`, `category`, `sort` (`score|date|docket|title|language|summary`), `order` (`asc|desc`), `limit`, `offset`. Returns `{total, items, stats}`; items carry triage, reasoning and classification.
- `GET /api/rulings/{docket}` - full detail: text, latest triage, `summaries.de` / `summaries.fr`, classification. Dockets contain a slash and go into the path as-is (`8C_129/2025`).
- `GET /api/facets` - divisions, languages, branches/categories with DE/FR labels and counts, date range, `demo` flag.
- `POST /api/rulings/{docket}/summarize` - no body, returns the updated detail.
- `GET /api/health`.

Please remove or clearly gate any hard-coded or sample data in the frontend so every view shows API data, and check the main views (knowledge base, all rulings, detail) against the real DB. Reply here if any field you need is missing; API changes go through my workers.
