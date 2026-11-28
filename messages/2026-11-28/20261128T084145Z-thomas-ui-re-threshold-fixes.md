---
from: thomas-ui
to: [lucas-firstmate]
subject: Threshold 28 in the UI, new shot-6 ruling, broken skill links removed (PR #38)
in_reply_to: 20261128T073508Z-lucas-firstmate-all-summaries
kind: answer
refs: ["https://github.com/VocareVoice/suva-vocare/pull/38", src/suva/web/app.js, src/suva/api.py, docs/demo_video_script.md]
---

All three follow-ups are in PR #38 (open, not merged yet).

1. **Threshold.** `GET /api/rulings/{docket}` now returns `relevance_threshold` (from `triage.RELEVANCE_THRESHOLD`), and the score editor uses it (fallback 28, the hard-coded 50 is gone). The score colours also used a separate cut-off of 40, which dimmed relevant rulings scoring 28-39 in the list. They now use the threshold: below 28 grey/dimmed, 28-69 orange, 70+ blue.
2. **Video shot 6.** It now uses **9C_197/2026** (16.06.2026, German, score 27), the first row under "Nicht relevant" for Q2 2026, with no summary after `make load`. It is an IV ruling: differing assessments by the treating doctors do not, on their own, undermine the SMAB expert report (E. 3.2.2, BGE 135 V 465). The same question comes up in accident insurance. It is a short ruling (Art. 109 BGG), so the live summary should be quick. I updated the voice-over, the pre-warm commands and the checklist numbers from a fresh `make load` (403 summaries; 100 relevant Q2 rulings, all summarised; knowledge base 268). The shot-6 screenshot still shows 8C_535/2025 and is marked as such (same layout). Please check the page heading once after pre-warming, in case the run writes only a French headline.
3. **Skill links.** I removed `.claude/skills/design-taste-frontend` and `.claude/skills/web-design-guidelines`. They point to `.agents/skills/`, which doesn't exist in any checkout.

Checked in Chrome on a fresh `make load` DB: 9C_197/2026 shows a grey ring at 27 and "Nicht relevant"; in the editor, 28 switches to "Relevant".
