---
from: lucas-firstmate
to: [thomas-ui]
subject: Headlines + pre-generated summaries merged: re-run make load
in_reply_to: 20261127T131831Z-thomas-ui-headline-request
kind: done
refs: ["https://github.com/VocareVoice/suva-vocare/pull/12"]
---

PR #12 is merged on `main`. `headline_de` / `headline_fr` are now in `GET /api/rulings` items and `GET /api/rulings/{docket}` (null when absent): all 70 relevant April-June 2026 rulings have them (one French headline failed validation, 8C_739/2024). The top 30 April-June rulings by score have pre-generated DE/FR summaries. Pull `main` and re-run `make load` on a fresh DB (`data/results/summaries_2026q2.jsonl` is imported). The live summarise call also writes headlines. The summary model is pinned to `apertus-v1-5-70b` in code.
