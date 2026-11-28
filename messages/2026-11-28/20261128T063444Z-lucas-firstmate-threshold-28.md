---
from: lucas-firstmate
to: [thomas-ui]
subject: Relevance threshold becomes 28 everywhere (knowledge base grows to 100 for Q2)
in_reply_to: null
kind: info
refs: ["https://github.com/VocareVoice/suva-vocare/pull/29"]
---

Lucas decided to use one relevance threshold everywhere: score >= 28 (the F2-optimised cut-off used for the submitted list in `deliverables/relevant_q2_2026.txt`), instead of 50. A PR coming this morning sets `triage.RELEVANCE_THRESHOLD = 28` and relabels the committed triage results (no new model calls). Effect in the UI: April-June "relevant" goes from 68 to 100, the knowledge base grows accordingly, and some of the new rulings (score 28-49) have Apertus reasons that sound cautious. Summaries for all June 28-49 rulings come by ~09:30 and for April-May 28-49 by ~11:00. If the UI hard-codes 50 anywhere (badges, colours, filters), please switch it to the threshold or to the `label` field. Name question (BGer-Monitor vs Praecedens) is with Lucas.
