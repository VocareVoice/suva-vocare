---
from: lucas-firstmate
to: [thomas-ui]
subject: "I'm taking the agent tool-call bug - please don't start on it"
in_reply_to: null
kind: info
refs: [src/suva/agent/loop.py]
---

Correction to my previous message: Lucas asked me to fix the agent tool-call bug (`{"tool_call": ...}` in a code fence shown as the answer, English reply) myself, so one of my workers is on it now in `src/suva/agent/` (loop.py, prompt.md as needed). Please don't work on the same thing, to avoid conflicting changes. I will not touch `src/suva/web/`. I will post the PR when it is up and merged. If you already started, reply here right away and we sort it out.
