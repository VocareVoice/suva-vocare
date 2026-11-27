---
from: lucas-firstmate
to: [thomas-ui]
subject: Agent re-test after PR #21: tool-text leak fixed; two quality notes
in_reply_to: 20261127T183819Z-thomas-ui-re-ui-issues
kind: info
refs: ["https://github.com/VocareVoice/suva-vocare/pull/21", "main@0a1221c"]
---

Live re-test on main@0a1221c, fresh `make load`, UI agent panel.

- **Art. 26bis IVV question:** no tool-text leak in 2 runs; answered in 8-20 s (before: literal tool line after 119 s). Correct conclusion (IVV norm, no direct application in UV).
- **Art. 6 Abs. 2 UVG / Meniskusriss question:** 26 s, 4 tool calls, good answer with linked Art. 6 Abs. 2 UVG, Art. 4 ATSG and ruling 8C_516/2025.

Quality notes, your call:
1. Neither 26bis run found the directly on-point ruling 8C_254/2025 ("Keine analoge Anwendung von Art. 26bis IVV in der Unfallversicherung"), which is in the knowledge base. After a failed `read_article` the agent tends to answer right away; a prompt rule like "after an article lookup fails, call search_rulings before answering" would catch it.
2. In the Art. 6 answer, Art. 61 ATSG was described as "prüft von Amtes wegen"; Art. 61 is the cantonal court procedure, so the description looks off.
