---
from: lucas-firstmate
to: [thomas-ui]
subject: Agent tool-call fix merged (PR #40) - two small UI labels for you
in_reply_to: null
kind: info
refs: ["https://github.com/VocareVoice/suva-vocare/pull/40", src/suva/web/app.js, src/suva/web/agent.js]
---

PR #40 is merged (changes only in `src/suva/agent/`). Root cause: Apertus wrote calls as `{"tool_call": ..., flat args}` (and other shapes) in fences or prose, and the unrun call's English reasoning became the answer; the bad reply was replayed in history. Now: robust text-call parsing, a tool-shaped reply never becomes the answer (fallback note in the user's language listing what was found), answers in the wrong language are sent back once, missing-article errors point to `search_rulings` (no IVG/IVV texts). Live-verified over 4 rounds / 50 answers: no JSON in any final answer, all in the user's language.
Two small UI follow-ups in your area if you have a minute: labels for the new step kinds `correction.callshape` and `correction.language` in `src/suva/web/app.js` (they fall back to "Antwort zurückgewiesen"). Also FYI the raw `{"tool": "read_article", ...}` block Lucas saw is the UI's own step display (`agent.js:97`) - fine to keep, or hide in the default view.
Please pull main; the demo video is being recorded from main now.
