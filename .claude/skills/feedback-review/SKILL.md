---
name: feedback-review
description: Turn the legal experts' feedback in the app (score corrections, edited summaries) into a markdown report with suggested, minimal changes to the triage and summary prompts, each with evidence, expected effect and a validation plan. For a developer or quality supervisor; it changes no prompt and no product output. Use when asked to review expert feedback, analyse the "Anpassungen", or propose prompt improvements from corrections.
---

# Feedback review: expert corrections -> suggested prompt changes

The Suva lawyers correct the product in the UI: they override a triage score ("Anpassungen",
`PUT /api/rulings/{docket}/score`, with an optional reason) and edit summaries
(`PUT /api/rulings/{docket}/summaries/{lang}`, or by applying an agent proposal). This skill
reads those corrections, works out what they have in common and which prompt rule or criterion
probably caused them, and writes a report with concrete suggestions for a human to decide on.
The whole loop is in `docs/feedback_loop.md`; an example report is
`docs/examples/feedback_review_example.md`.

## Ground rules

- **Nothing is applied automatically.** You write a report and stop. Do not edit
  `src/suva/triage.py`, `src/suva/summarize.py`, `src/suva/prompts/`, `data/eval/` or any other
  file of the product, do not bump a prompt version, and do not commit. A person reads the
  report and decides; a developer applies the chosen changes and evaluates them.
- **Product outputs stay Apertus-only.** Relevance scores and summaries in the product are
  produced by Apertus (plus rule-based processing). You suggest changes to the prompts and
  rules that Apertus runs with; you never write or correct a score, a summary or a headline,
  never call the app's write endpoints, and never put text of yours into the database.
- **Read-only on the data.** Work on the export file and read the database or the API only
  with reads. A copy of the database is fine for experiments; the live one is not.
- **Evidence over generalisation.** One correction is an observation, not a pattern. Every
  claim about a ruling must be checked against the ruling's text, and every suggestion must
  name the corrections it rests on.

## Inputs

1. Export the feedback (deterministic, no LLM; same database, same file):

   ```sh
   DB_PATH=data/suva.db uv run suva feedback-export --out /tmp/feedback.json
   ```

   Write it outside the repository (a scratch or temporary directory). `--generated FILE ...`
   names the `export-summaries` files that hold the generated summaries an edit replaced
   (default `data/results/summaries_*.jsonl`); the database itself keeps no summary history.

2. The file holds:
   - `prompt_versions`, `relevance_threshold` (28), `counts`;
   - `score_corrections`, oldest first: the ruling (docket, date, language, title, headline,
     branch and primary category of the classification), the model's result (`model`,
     `model_score`, `model_label`, `model_prompt_version`, `model_reasoning_de`), the expert's
     (`expert_score`, `expert_label`, `expert_comment`, `adjusted_at`), `delta` (expert minus
     model) and `crosses_threshold` (the correction moves the ruling into or out of the
     knowledge base). `model` is `prefilter` or `gate` when rules in `triage.py` decided
     without an LLM call;
   - `feedback`: every row of the `feedback` table, including the history of corrections that
     were later replaced or reset;
   - `edited_summaries`: the edited text, the generated text it replaced with its prompt
     version and source file, a word diff (`[-removed-]`, `{+added+}`), word counts, and
     `edited_by` (`manual` for the editor, `agent` for an applied agent proposal);
   - `adjustment_summaries`: the summaries of the corrections that Apertus wrote on the
     "Anpassungen" page, if anyone generated them.

3. The current behaviour you are reviewing:
   - triage: `src/suva/triage.py` (`SYSTEM_PROMPT` with the relevance criteria and levels,
     `prior()` with the keyword and substance weights, `gate()`), method and history in
     `docs/eval_triage.md`;
   - summaries: `src/suva/summarize.py` (pipeline, rule checks) and `src/suva/prompts/`
     (`summary_style.md`, `summary_de.md`, `summary_fr.md`, `summary_holdings.md`,
     `summary_check.md`, `summary_facts.md`, `summary_references.md`,
     `summary_consistency.md`, `headline.md`), the glossary `data/eval/glossary.json`, the
     house style `docs/style_guide.md`, method and history in `docs/eval_summaries.md`;
   - the ruling texts: `SELECT text FROM rulings WHERE docket = ?` or
     `GET /api/rulings/{docket}`.

## Steps

### 1. Check the export

Note the counts and anything that limits the analysis: corrections made against an older
`model_prompt_version` than the current triage version (the current prompt may already behave
differently; say so and, if it matters, re-read the current reasoning after a re-run on a copy),
edits with `generated_text: null` (no source for the generated text; analyse the edited text
alone), corrections without a comment. If there are no corrections and no edits, say so and
stop.

### 2. Analyse every score correction

For each correction read the model's reasoning, the expert's comment and the ruling itself
(rubrum, subject, the decisive considerations, operative part). Decide which stage produced
the model's score and assign one cause:

| Cause | Typical sign | Where a fix would go |
|---|---|---|
| Pre-filter or gate | `model` is `prefilter` or `gate` | `prior()` weights or patterns, `gate()` in `triage.py` |
| Prompt criterion | the reasoning follows a rule of `SYSTEM_PROMPT` that the expert rejects (quote the rule) | that sentence of `SYSTEM_PROMPT` or the level scale |
| Missing criterion | the expert's reason is a consideration the prompt does not mention | a new, narrow sentence in `SYSTEM_PROMPT` |
| Prior weight | level and reasoning agree with the expert, the prior pulls the score across the threshold (28) | `prior()` (70 % level + 30 % prior) |
| Model error | the reasoning misreads the ruling (wrong branch, wrong party, wrong holding) | usually none; note it, check if it repeats |
| Threshold noise | model and expert scores within about 10 points of the threshold (28) | none; one prompt rewording moves levels by several steps |
| Policy question | the expert's reason is a choice about what Suva wants, not a reading error | a decision for the legal team before any prompt change |

When the expert gave no reason, infer it only as a hypothesis and mark it as such.

### 3. Analyse every edited summary

Read the generated text, the edited text and the word diff, and the passages of the ruling the
changed sentences refer to. Classify each change:

- **factual correction** (who decided what, a rule's content, a statute, a figure, a
  consideration number, the outcome): check against the ruling which version is right. A
  confirmed error the final factual check missed points to `summary_facts.md` or
  `summary_check.md` (the error list), a wrong conclusion to `summary_holdings.md`, a wrong
  reference to `summary_references.md`;
- **terminology or statute abbreviation**: `summary_de.md` / `summary_fr.md` or a glossary
  entry in `data/eval/glossary.json`;
- **style, structure, length, emphasis**: `summary_style.md` and the house style
  (`docs/style_guide.md`); a recurring length problem may be the rule checks in `summarize.py`;
- **added content** (a holding or fact the summary lacked): `summary_holdings.md` or the
  selection rules in `summary_style.md`;
- **personal preference**: only one editor, no rule in the style guide; record, do not propose.

Edits by `agent` were requested in the chat by a user; treat them like manual edits but say so.

### 4. Group into patterns

Group the corrections and edits by direction (raised / lowered), branch, category and cause.
A pattern needs at least two corrections pointing the same way, or one correction whose comment
states a general rule ("gilt für die UV genauso"); mark single cases as observations. Then look
for counter-evidence before you propose anything:

- the labelled period (`data/eval/relevant_q4_2025_q1_2026.json`, the rulings Suva listed in
  Q4 2025 and Q1 2026): how many rulings the pattern covers there, and how many of them Suva
  listed. A query over `triage` and `classification` of the period gives the numbers; a rule
  that would raise 40 rulings of which Suva listed 4 is a regression, however well it fits the
  corrections;
- earlier attempts in `docs/eval_triage.md` and `docs/eval_summaries.md`: several plausible
  rules were tried and rejected (an explicit invalidity insurance rule, v4b/v4c; "level 8 for a
  legal question, 7 for medical evidence", 4b). Say when a suggestion repeats one, and what is
  different this time.

Compare your patterns with the stored `adjustment_summaries` if there are any: note where you
agree, and where the Apertus summary claims something the corrections do not support.

### 5. Write suggestions

Each suggestion is one minimal change, small enough to test on its own:

- **Target**: file and location, with the current text quoted;
- **Change**: the proposed text as a diff, as short as possible (one sentence, one weight, one
  list entry); never a rewrite of a whole prompt;
- **Evidence**: the corrections or edits it rests on (dockets, expert comments) and the
  counter-evidence count from step 4;
- **Expected effect**: which rulings should move and in which direction, and what else could
  move (side effects on the other branch or on listed rulings);
- **Validation**: how to accept or reject it (next section), with the bar it has to pass;
- **Confidence**: high / medium / low, with one sentence why.

Order the suggestions by expected benefit and confidence. Also list the corrections that need
**no prompt change** (noise, model error without a pattern, preference) and the **policy
questions** the legal team should answer first.

### 6. Validation plan per type of change

- **Triage prompt or prior.** On a copy of the database, bump `PROMPT_VERSION` in `triage.py`,
  re-run both labelled quarters (`uv run suva triage --from 2025-10-01 --to 2025-12-31`, then
  `--from 2026-01-01 --to 2026-03-31`), export each quarter with `uv run suva export-triage` and
  score it with `uv run python -m suva.eval.score_triage`. Keep the change only under the
  cross-quarter rule of `docs/eval_triage.md`: neither quarter worse on P@10, P@30, R@30 or
  R@60. Also check the corrected rulings themselves: do they now land on the expert's side of
  the threshold (28)? A change that fixes the corrections and fails the rule is rejected.
- **Summary prompts.** Bump `PROMPT_VERSION` in `summarize.py`, regenerate the hold-out
  (`data/eval/split.json`) and the edited rulings on a copy, score the hold-out with
  `uv run python -m suva.eval.score_summaries generated.jsonl --judge` against the previous
  version (`docs/eval_summaries.md`), and compare the regenerated edited rulings with the
  experts' edits. Factual changes also need a blind reading: someone who does not know which
  version is which reads both against the ruling.
- **Glossary entry.** Re-run the summaries that use the term and check the term check of
  `score_summaries` (glossary usage, foreign statutes).

## Report

Write the report as markdown where the person running the skill asks (by default
`feedback_review_<YYYY-MM-DD>.md` outside the repository), with these sections:

1. **Summary**: three to five sentences: what the experts corrected, the main pattern, the
   suggestion with the best evidence, and what needs a decision.
2. **Data**: database, export file, date, prompt versions, counts, limits from step 1.
3. **Score corrections**: one table row per correction (docket, branch / category, model ->
   expert, stage, cause, the expert's reason or "none given"), then the patterns with their
   counter-evidence.
4. **Edited summaries**: per edit, the changed passages (quoted, short), the classification
   from step 3 and whether the ruling confirms the edit.
5. **Suggested changes**: the suggestions from step 5, numbered (S1, S2, ...).
6. **No change recommended** and **Questions for the legal team**.
7. **Next steps**: who decides, who applies, which evaluation runs, and the reminder that
   nothing in this report has been applied.

Then stop. Applying a suggestion is a separate, human decision.
