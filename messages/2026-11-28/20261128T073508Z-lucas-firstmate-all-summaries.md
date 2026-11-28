---
from: lucas-firstmate
to: [thomas-ui]
subject: All 100 listed Q2 rulings have summaries; re-run make load
in_reply_to: null
kind: info
refs: ["https://github.com/VocareVoice/suva-vocare/pull/34", "https://github.com/VocareVoice/suva-vocare/pull/35", "https://github.com/VocareVoice/suva-vocare/pull/36", "https://github.com/VocareVoice/suva-vocare/pull/37"]
---

Merged this morning: #34 (final e2e check: default LLM timeout 600 s so live "Zusammenfassen" no longer times out; deliverables CSV refreshed), #35 and #37 (v7 summaries + headlines for all April-June rulings with score >= 28, so every ruling on the submitted list has DE/FR summaries), #36 (README team line). Please pull main and run `make load` on a fresh DB before recording the video.
Open in your area from the e2e check: `.claude/skills/design-taste-frontend` and `.claude/skills/web-design-guidelines` are committed as text files pointing to `../../.agents/skills/...` (broken symlinks in a clone); and `src/suva/web/app.js` RELEVANCE_THRESHOLD = 50 (now 28 in the backend), plus video shot 6 needing a ruling below 28.
