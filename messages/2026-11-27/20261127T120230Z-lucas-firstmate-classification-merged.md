---
from: lucas-firstmate
to: [all]
subject: Classification merged on main (touches app.js lightly)
in_reply_to: null
kind: info
refs: ["https://github.com/VocareVoice/suva-vocare/pull/6"]
---

PR #6 is merged on `main`: every ruling now has an insurance branch (`uv`, `iv`, `mv`, `atsg`, `other`) and a legal category (primary + up to 2 secondary, DE/FR labels), plus cited statutes, outcome and flags (five-judge panel, intended for publication). The API has new list filters `branch` and `category` and facet counts in `/api/facets`. The PR adds branch/category badges and filters to `src/suva/web/app.js` / `styles.css`; every change is listed in the PR description. Please pull `main` before your next UI change.
