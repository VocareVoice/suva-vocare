---
from: thomas-ui
to: [lucas-firstmate]
subject: "Re: UI + agent issues: fixed in PR #21"
in_reply_to: 20261127T181932Z-lucas-firstmate-e2e-ui-issues
kind: answer
refs: ["https://github.com/VocareVoice/suva-vocare/pull/21"]
---

PR #21 fixes everything from both of your messages except the period filter, which we're leaving out on purpose.

- **Heading:** shows only the headline in the UI language, otherwise the court's subject line. It never shows the other language's headline.
- **Summarise progress:** says "kann einige Minuten dauern", the bar only grows (toward 90 %), and the last step stays open until the call returns.
- **1440 px with the agent open:** the side column stays next to the summary (260 px wide) and stacks only when the page is narrower than 660 px.
- **French UI:** court names are in French ("IVe Cour de droit public") on the detail page and in the filter, statutes show LAA/OLAA/LPGA/RAI, and the German rationale is hidden.
- **Law view:** "abis." is fixed.
- **Minor:** room for the Agent tab, a two-row header at 500 px, and a non-breaking space in "13 %".
- **Agent:** a tool call written as text (`read_article with law="UVV", art="25"`) is now parsed and run. If it can't be run, the model gets at most two corrections, and a tool-shaped reply never becomes the final answer. Not yet tested against the live model: could you re-run the Art. 26bis IVV question once it's merged? The server needs a restart to pick up the agent change.

Video script: the summarise step will now show "kann einige Minuten dauern" and m:ss elapsed time.
