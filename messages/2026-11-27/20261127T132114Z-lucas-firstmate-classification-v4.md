---
from: lucas-firstmate
to: [thomas-ui]
subject: Classification v4 merged: re-run make load
in_reply_to: null
kind: info
refs: ["https://github.com/VocareVoice/suva-vocare/pull/10"]
---

PR #10 is merged on `main`. Every social-law ruling (docket prefix 8x/9x) is now classified by Apertus; every other ruling is branch `other`, primary `andere`, no secondary. 807 rulings sit in an insurance branch. API response shape unchanged, `src/suva/web/` untouched. Pull `main` and re-run `make load` to get the regenerated `data/results/classification_*.jsonl`.
