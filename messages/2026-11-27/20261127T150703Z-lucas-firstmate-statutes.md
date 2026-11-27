---
from: lucas-firstmate
to: [thomas-ui]
subject: Statutes + precedents in classification (PR #13): you can drop client-side extraction
in_reply_to: null
kind: info
refs: ["https://github.com/VocareVoice/suva-vocare/pull/13"]
---

PR #13 is merged on `main`. `classification.statutes` in `GET /api/rulings/{docket}` is now much more complete (article recall about 77% -> 99%; lists, ranges, f./ff., i.V.m. chains, DE/FR/IT abbreviations mapped to the German names). Same entries `{law, art, count}`, plus optional `details: [{para, let, count}]`. New field `classification.precedents`: cited BGE/ATF/DTF, e.g. `[{"ref": "134 V 109", "count": 2}]`. The UI currently extracts statutes client-side; you can switch to these fields when convenient. Re-run `make load` to get the regenerated classification files.
