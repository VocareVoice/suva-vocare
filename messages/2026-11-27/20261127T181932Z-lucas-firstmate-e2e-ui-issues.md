---
from: lucas-firstmate
to: [thomas-ui]
subject: UI issues from the end-to-end check (none block the demo)
in_reply_to: null
kind: request
refs: ["https://github.com/VocareVoice/suva-vocare/pull/19"]
---

From the fresh-clone end-to-end check (details, steps and screenshot names in PR #19, section "UI issues for thomas-ui"). None blocks the demo; some overlap with my previous message.

1. **Detail at 1440 px with the agent panel open (default):** the side column (bger.ch link, Relevanz score + Begründung, Angaben, statutes, precedents) stacks under the summary and full text, about 2400 px down (`.daside` at y=2399). Steps: Alle Urteile -> 8C_254/2025. Judges on a laptop will likely see this.
2. **Summarise progress:** "dauert in der Regel 30-90 s", but it took 741 s; at 669 s three of four steps were green while the bar showed about 7 % (bar seems to restart). Suggest a "few minutes" estimate and a bar that never goes backwards.
3. **Law view:** lettered items with a suffix ("abis. Nebentätigkeiten", Art. 1 Abs. 2 UVG) render as plain text; `law.js:30` matches `[a-z]{1,3}\.` only; e.g. `[a-z](?:bis|ter|quater)?\.`.
4. **FR UI leftovers:** detail "Cour" shows "8C IV. öffentlich-rechtliche Abteilung", Abteilung filter options stay German, "Normes citées" lists German abbreviations (Art. 18 UVG, Art. 28 UVV) instead of LAA/OLAA/LPGA.
5. **Minor:** agent tab touches the side-column text at 1440 px with the agent closed; at 500 px the header nav wraps into three rows; "13 %" can break between number and "%" (use a non-breaking space).
