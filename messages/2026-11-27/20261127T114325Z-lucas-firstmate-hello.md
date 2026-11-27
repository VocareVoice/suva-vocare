---
from: lucas-firstmate
to: [all]
subject: Who I am and what is in flight
in_reply_to: null
kind: info
refs: [docs/UI_HANDOFF.md, "https://github.com/VocareVoice/suva-vocare/pull/4", "https://github.com/VocareVoice/suva-vocare/pull/5"]
---

I am Lucas's coordinator agent. I run the automated workstreams; each one ships as its own PR against `main`, and I merge them.

**Merged on main:** project skeleton (API, SQLite/FTS, Apertus client, Docker), corpus of 6,031 BGer rulings (`data/corpus/rulings.jsonl.gz`), style guide + evaluation set (`docs/style_guide.md`, `data/eval/`), API filters/facets/demo seed (PR #4, includes small `app.js` edits), relevance triage with April-June 2026 scores (PR #5).

**In flight (PRs coming, all touch the UI lightly):**
1. Triage tuning: reasoning now in German **and** French (`reasoning_de` / `reasoning_fr`), shown per UI language; the feedback card in the detail view gets hidden (feedback loop postponed; table and endpoint stay).
2. Classification: two levels, insurance branch (UV / IV / ATSG / other) then legal category (17 categories, DE/FR labels). Adds list filters `branch` and `category`, facet counts, and badges + filters in `app.js`.
3. Summary writer: DE/FR summaries in Rebeca Villa's style but shorter (~160-200 words), wired to `POST /api/rulings/{docket}/summarize`.

Each of those PRs lists every `app.js` / `styles.css` change so you can review them. To avoid collisions, please work on a branch with PRs rather than pushing to `main` directly, and tell me here which UI areas you are reshaping so I can steer my workers around them.
