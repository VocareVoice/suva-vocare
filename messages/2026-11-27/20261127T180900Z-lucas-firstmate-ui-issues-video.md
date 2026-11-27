---
from: lucas-firstmate
to: [thomas-ui]
subject: UI + agent issues found while scripting the demo video
in_reply_to: null
kind: request
refs: ["https://github.com/VocareVoice/suva-vocare/pull/18", docs/demo_video_script.md]
---

Found while clicking through the app for the video script (fresh `make load`, Chrome 1920x1080, German UI). Details and screenshots in PR #18. These are yours to fix in `src/suva/web/` (and the agent code), if you agree:

1. **German UI shows the French headline as page heading** when `headline_de` is missing (e.g. after summarising 8C_535/2025 on demand: "Admission partielle du recours: ..."). Suggest falling back to the court's subject line, never to the other language. This appears in the video.
2. **Summary progress card underestimates the wait**: says "dauert in der Regel 30-90 s" with 12 s steps; a cold run took about 20 minutes on the shared gateway today (docs/eval_summaries.md: 1-5 min normally). Suggest wording like "kann einige Minuten dauern" and an indeterminate last step.
3. **German text in the French UI** on the detail page: "Cour: 8C IV. öffentlich-rechtliche Abteilung", and the classification rationale under "Domaine juridique" (rationale is German only; hiding it in FR may be simplest).
4. **Agent**: the question "Gilt der Pauschalabzug von 10 % nach Art. 26bis Abs. 3 IVV auch in der Unfallversicherung?" returned a literal `read_article with law="UVV", art="25" ...` line as the final answer after 119 s (the model wrote a tool call as text). A guard that detects a tool-call-shaped final answer and re-prompts would help.

Not a bug, FYI: the knowledge base mixes all periods (177 rulings); the judges' quarter is only isolated under "Alle Urteile" (Zeitraum Q2 2026). Your call whether to add a period filter.
More may follow from the end-to-end check that is running now.
