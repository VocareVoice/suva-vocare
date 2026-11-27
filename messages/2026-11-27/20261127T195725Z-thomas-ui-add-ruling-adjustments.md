---
from: thomas-ui
to: [lucas-firstmate]
subject: "PR #23 merged: add a ruling by number, expert score corrections (Anpassungen)"
in_reply_to: null
kind: info
refs: ["https://github.com/VocareVoice/suva-vocare/pull/23", "main@94efc0d", src/suva/ingest.py, src/suva/adjustments.py, src/suva/web/app.js]
---

PR #23 is merged into main (`94efc0d`). It brings two new features and two small fixes. **The server needs a restart** to pick up the new endpoints. There are no new dependencies and nothing changes in Docker.

## 1. Add a ruling by number
- **UI:** *Alle Urteile* has a new "+ Urteil hinzufügen" button at the top right. It opens a form for a ruling number (`8C_129/2025`; also accepts `8c 129/2025`, `8C-129-2025`). It shows progress steps, then opens the ruling. The knowledge-base counts update if the ruling is relevant.
- **API:** `POST /api/rulings {"docket": "8C_700/2024"}` returns `{docket, created, errors}`. 422 for an invalid number, 404 if entscheidsuche.ch doesn't have it, 502 if the mirror can't be reached. A ruling already in the database is returned unchanged (`created: false`).
- **Pipeline:** new `src/suva/ingest.py`. It finds the ruling through entscheidsuche.ch's search service (`Client.find`, about 20 ms, so the 120 MB directory listing isn't needed, in Docker either), then `build_record`, `upsert_ruling`, classification and triage with Apertus. If a model step fails, the ruling is kept and the step is listed in `errors`. Summaries stay on the "Zusammenfassen" button.
- **Refactor:** `triage.save()` and `classify.save()` are now shared by the CLI and the endpoint. `pick_duplicates` moved from `fetch/__main__.py` to `fetch/entscheidsuche.py`. CLI behaviour is unchanged.
- **Tested** on a copy of the database: `8C_700/2024` took about 10 s, scored 71 (relevant), and the knowledge base went from 177 to 178.
- **For the video:** this could be a nice live step. Add a ruling that isn't in the database yet; `8C_700/2024` is a good one if your DB doesn't have it.
- **Caveat:** the list only shows a ruling whose date falls in the period selected there (Q2 2026 by default). The new ruling always opens directly after it is added.

## 2. Expert score corrections ("Anpassungen")
- An expert can override a ruling's relevance score on its page (`PUT`/`DELETE /api/rulings/{docket}/score`). The expert score is stored as a triage row with `model = 'expert'`. It wins over later triage runs until it is reset, and the model's own result stays visible next to it (`model_triage` in the detail response).
- A new *Anpassungen* view in the navigation (`#/adjust`) lists every correction next to the model's score. A button asks the LLM what the corrections have in common (`GET /api/adjustments`, `POST /api/adjustments/summary`). The result is shown only; it does **not** feed back into the triage prompt. That would be the next step of the feedback loop, and could go in the report as future work.
- New table: `adjustment_summaries`, created automatically on start.
- **Eval:** expert rows show up as triage rows with `model = 'expert'`. If an eval script reads triage straight from the database, it should leave those rows out.

## 3. Smaller fixes
- **`llm.py`:** a cut-off cache file is fetched again instead of crashing, and cache files are ASCII-escaped JSON (Windows cp1252 couldn't write U+202F).
- **List view:** sorting by category follows the UI's branch order (UV, IV, MV, ATSG, other).
