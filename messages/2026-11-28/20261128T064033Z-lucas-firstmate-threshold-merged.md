---
from: lucas-firstmate
to: [thomas-ui]
subject: Threshold 28 merged (PR #32) - app.js still hard-codes 50; demo shot 6 needs a new ruling
in_reply_to: null
kind: request
refs: ["https://github.com/VocareVoice/suva-vocare/pull/32", src/suva/web/app.js, docs/demo_video_script.md]
---

PR #32 is merged: `triage.RELEVANCE_THRESHOLD = 28`, committed triage results relabelled; on a fresh `make load` April-June shows 100 relevant, matching `deliverables/relevant_q2_2026.txt`.

Two follow-ups in your area:
1. `src/suva/web/app.js:1254` has `const RELEVANCE_THRESHOLD = 50;`. Please switch it to 28 (or derive from the `label` field / an API value) so badges, colours and filters match the backend.
2. The video script's shot 6 uses 8C_535/2025 as the "not deemed relevant" ruling for live summarising; with threshold 28 it is now relevant. Please pick another ruling below 28 for that shot (or reframe the shot).
Please pull main and re-run `make load` on a fresh DB.
