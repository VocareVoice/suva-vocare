---
from: lucas-firstmate
to: [thomas-ui]
subject: Overnight status, project name BGer-Monitor, pitch review
in_reply_to: null
kind: info
refs: ["https://github.com/VocareVoice/suva-vocare/pull/26", "https://github.com/VocareVoice/suva-vocare/pull/27", "https://github.com/VocareVoice/suva-vocare/pull/28"]
---

- **Project name:** Lucas confirmed **BGer-Monitor** (as in the UI header and deck). The report will use it.
- **Merged tonight:** summaries v7 (#26: blind-read factual errors 43 -> 31 on 20 hold-out texts), report v2 (#27), feedback-review skill (#28: `.claude/skills/feedback-review`, `suva feedback-export`, `docs/feedback_loop.md`; reads your expert corrections / Anpassungen and edited summaries, writes a report with suggested prompt changes for a human to review; nothing applied automatically).
- **Running overnight:** summaries for all relevant rulings (38 April-June first, then 109 Q4 2025/Q1 2026 in `data/results/summaries_2025q4_2026q1.jsonl`; I will post when it lands so you can adjust the `gen.eval` note); an F2-optimised relevance list deliverable in `deliverables/` (the challenge scores Recall/F2 on a delivered list of Q2 rulings), including a check of publication vs decision dates.
- **Pitch review** of `Vocare_Pitch_v3.pptx` against the challenge deck is written for Lucas (not committed). Main points for the deck owners: show how Suva scores us (Recall/F2 list, top-5 June 2026 summaries, "+ Urteil hinzufügen" for "add another judgement"); remove accuracy overclaims ("0 invented", "every statement traceable") since blind reading still finds about 1.5 factual errors per summary; refresh the v6 excerpt and the pre-#23 screenshot; say the corpus comes from the entscheidsuche.ch mirror.
