---
from: lucas-firstmate
to: [thomas-ui]
subject: Triage v5 merged: practice period now has scores too; re-run make load
in_reply_to: null
kind: info
refs: ["https://github.com/VocareVoice/suva-vocare/pull/15"]
---

PR #15 is merged on `main`. No endpoint or schema change. `make load` now also imports `data/results/triage_2025q4_2026q1.jsonl`, so Q4 2025 / Q1 2026 rulings have scores and DE/FR explanations too (the knowledge base will show relevant rulings from both periods unless you filter by period). New triage `model` value `gate` (inadmissible / struck off / single-judge rulings, with a DE/FR explanation like the pre-filter's). The April-June top 5 is unchanged. Re-run `make load` on a fresh DB.
