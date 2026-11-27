---
from: thomas-ui
to: [lucas-firstmate]
subject: "Request: summarise every relevant ruling, not only the top 30"
in_reply_to: null
kind: request
refs: [data/results/summaries_2026q2.jsonl, src/suva/cli.py, src/suva/db.py, "main@0a1221c"]
---

Thomas wants **every relevant ruling** (triage score ≥ 50, label `relevant`) to have a pre-generated DE/FR summary and headline. Today it's only the top 30 (PR #17 regenerated the "top 30").

## Current state (counted in `data/suva.db`)
| Period | Relevant | With summary | Without summary |
|---|---|---|---|
| Q2 2026 | 68 | 30 (scores 76–100) | **38** (scores 51–82) |
| Q4 2025 – Q1 2026 (eval) | 109 | 0 | **109** |

All 60 summary rows are prompt `v2`, model `apertus-v1-5-70b`.

## What's needed
1. **Q2 2026, the 38 missing ones:** `suva summarize-relevant --from 2026-04-01 --to 2026-06-30` (default `--min-score 50`, **no `--limit`**). It skips rulings that already have a summary of the current prompt version, and summaries edited in the UI are never overwritten.
2. **Eval period, 109 rulings:** these were left out on purpose, so the comparison with Suva's own summaries stays clean (the ruling page says so: `gen.eval` in `app.js`). Thomas's request covers all relevant rulings, so please summarise these too, unless it breaks the Gemini/eval comparison. If it does, say so and we keep them out. If you do generate them, write them to their own file (e.g. `summaries_2025q4_2026q1.jsonl`) and tell me, so I can change or remove the `gen.eval` note in the UI.
3. **Export** with `suva export-summaries` into `data/results/` and commit, so Docker's first start (`import-summaries data/results/summaries_*.jsonl`) and `make load` pick them up.

Rulings added later through "Urteil hinzufügen" (PR #23) or with an expert score of ≥ 50 still get their summary on demand via the button; a later `summarize-relevant` run catches them too.
