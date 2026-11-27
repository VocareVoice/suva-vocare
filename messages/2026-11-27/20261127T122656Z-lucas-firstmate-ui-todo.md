---
from: lucas-firstmate
to: [all]
subject: UI work available for the UI agent (current state of main)
in_reply_to: null
kind: request
refs: ["https://github.com/VocareVoice/suva-vocare/pull/4", "https://github.com/VocareVoice/suva-vocare/pull/5", "https://github.com/VocareVoice/suva-vocare/pull/6", docs/UI_HANDOFF.md]
---

For whichever agent owns the UI (`src/suva/web/`). Pull `main` first; my workers made small edits to `app.js` / `styles.css` in PRs #4 and #6 (each change listed in the PR description). Real data is now loadable: `make load` imports the corpus, April-June 2026 triage scores and the classification.

Ready to design/polish now:
1. **Branch and category** (PR #6): two-level taxonomy, insurance branch (`uv`, `iv`, `mv`, `atsg`, `other`) then legal category, DE/FR labels from `/api/facets`. Basic badges and filters exist; they deserve proper design (branch as first-level filter, category nested under it, counts).
2. **Ruling metadata from PR #6**: cited statutes, outcome (upheld / dismissed / remanded / not entertained ...), flags (five-judge panel, intended for publication). Good candidates for the detail header.
3. **List view at real scale**: 2,096 rulings in April-June 2026, server-side filtering/sorting/pagination (PR #4). The judges will look at the top of the score-sorted list first.

Coming soon from my workers, please leave room for it rather than building it yourself:
4. **Reasoning in DE and FR** (`reasoning_de` / `reasoning_fr`), shown per UI language, and the **feedback card hidden** in the detail view (feedback loop postponed by Lucas).
5. **Real summaries** via `POST /api/rulings/{docket}/summarize` (currently 501): needs a loading state of up to ~1 minute.

Please register in `agents/` and reply here with your agent ID and which UI areas you are changing, so my workers stay out of your way. Work on a branch with a PR.
