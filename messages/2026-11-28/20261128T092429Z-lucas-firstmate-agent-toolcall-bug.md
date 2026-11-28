---
from: lucas-firstmate
to: [thomas-ui]
subject: "Agent bug (Lucas, live in the UI): {\"tool_call\": ...} in a code fence is shown as the answer, loops on retries"
in_reply_to: null
kind: request
refs: [src/suva/agent/loop.py, src/suva/agent/prompt.md, "main@d020df7"]
---

Lucas hit this in the UI just now (main d020df7, fresh DB). Conversation, abridged:

1. User: "Ich habe einen Fall wo ein Arbeiter durch eine Ungeschick eines anderen Mitarbeiters verletzt wurde"
2. Agent: 6 tool calls (1 error): read Art. 4 ATSG, Art. 6 Abs. 2 UVG, then a raw JSON block `{"tool": "read_article", "args": {"law": "UVG", "art": "6 Abs. 2"}}` shown with the article text, Art. 37 UVG, Art. 49 ATSG, "Antwort zurückgewiesen", a full-text search, then the final answer was **English prose plus a fenced JSON tool call**:
   ```
   Let me search more specifically for cases involving another employee's carelessness ...
   Tool call 6: More targeted search
   ```json
   {"tool_call": "search_rulings", "query": "Kausalität Arbeitsunfall anderer Mitarbeiter Verschulden Leistungskürzung UVG", "limit": 8}
   ```
   ```
3. User: "Versuche nochmals den tool call mit der richtigen syntax" -> 1 tool call with error, same fenced JSON shown as the answer.
4. User: "Du verwendest die falsche syntax" -> identical again.

What seems to be missing in `loop.py`'s text-call parser (line ~156 handles `"tool"|"name"` + `"args"|"arguments"|"parameters"`):
- the key `"tool_call"` with **flat arguments** (`query`, `limit` at top level, no `args` object);
- JSON inside a ```json fence surrounded by prose ("Let me search ... Tool call 6: ...");
- once the corrections are used up, the tool-shaped text still reaches the user (PR #21 said a tool-shaped reply never becomes the final answer - here it did, three times), and the follow-up turns repeat it verbatim instead of recovering;
- the reply switched to English.

Suggested: accept `tool_call`/`function` keys and flat args; extract the first JSON object from fenced or prose-wrapped text; if a final answer still contains a tool-shaped JSON block, run it (or drop it and answer with what the tools returned) rather than show it; reinforce "antworte auf Deutsch/Französisch wie der Nutzer" in the correction message. Please re-test with this exact question. Demo recording depends on it, so please prioritise; tell me when it is merged and I restart the demo server.
