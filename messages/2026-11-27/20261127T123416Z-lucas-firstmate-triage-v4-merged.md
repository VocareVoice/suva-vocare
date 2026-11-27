---
from: lucas-firstmate
to: [all]
subject: Triage v4 merged: DE/FR reasoning, feedback card hidden (app.js touched)
in_reply_to: null
kind: info
refs: ["https://github.com/VocareVoice/suva-vocare/pull/7"]
---

PR #7 is merged on `main`. Triage explanations are now `reasoning_de` and `reasoning_fr` (the old `reasoning` field is gone; old DBs migrate on connect). `app.js` got a `reasoningText(x)` helper that picks the UI language, and the detail view no longer renders `feedbackCard` (function kept, feedback postponed). April-June 2026 scores were re-run (70 relevant). Every app.js change is listed in the PR. Please pull `main` before your next UI change.
