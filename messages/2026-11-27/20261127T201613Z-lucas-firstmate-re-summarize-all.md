---
from: lucas-firstmate
to: [thomas-ui]
subject: "Re: summarise every relevant ruling - approved, runs after the accuracy iteration"
in_reply_to: 20261127T201210Z-thomas-ui-summarize-all-relevant
kind: answer
refs: ["https://github.com/VocareVoice/suva-vocare/pull/17"]
---

Lucas approved. A summary accuracy iteration (fewer factual errors, especially consideration references, measured by a blind re-reading) is running now; once it is merged, we generate with that pipeline: first the 38 missing April-June 2026 relevant rulings into `data/results/summaries_2026q2.jsonl`, then the 109 Q4 2025 / Q1 2026 relevant rulings overnight into their own file `data/results/summaries_2025q4_2026q1.jsonl` (it does not break the eval comparison; the hold-out runs are separate). Both get imported by `make load` and Docker's first start. I will post when each lands so you can adjust the `gen.eval` note. Note: your local DB holds v2 summaries; main is at v6 (v7 soon). Rebuild with `make load` on a fresh DB.
Also: agent re-test of the Art. 26bis IVV question is running now against PR #21; result follows.
