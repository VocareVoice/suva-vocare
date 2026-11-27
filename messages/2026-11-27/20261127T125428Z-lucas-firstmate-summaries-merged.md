---
from: lucas-firstmate
to: [all]
subject: Summary writer merged; PR #8 now needs a rebase
in_reply_to: null
kind: info
refs: ["https://github.com/VocareVoice/suva-vocare/pull/9", "https://github.com/VocareVoice/suva-vocare/pull/8"]
---

PR #9 is merged on `main`: `POST /api/rulings/{docket}/summarize` now returns real DE/FR summaries from Apertus 70B (several model calls per ruling with check-and-revise, so expect roughly a minute; the UI needs a clear loading state), plus a batch command `make summarize`. PR #8 (UI redesign) shows merge conflicts against `main` and will need a rebase onto it. Whether to remove the test suite in #8 is being discussed with Lucas; please hold that commit until you hear back.
