# Triage evaluation

How well `src/suva/triage.py` (prompt version `v3`) ranks the rulings Suva considered relevant,
tuned on Q4 2025 and Q1 2026 (labels: `data/eval/relevant_q4_2025_q1_2026.json`, 59 Federal
Court rulings) and then run over April-June 2026 (`data/results/triage_2026q2.jsonl`).

## Method

1. **Prior (deterministic).** Subject line of the ruling (accident or military insurance +45,
   invalidity insurance +25), division (8C +10, 9C +5), Suva/CNA/INSAI in the rubrum (+15) or
   elsewhere (+10), UVG/UVV citations (up to +15), ATSG citations (+5). Rulings below 20 are
   labelled not relevant without an LLM call and get a German explanation listing the hints that
   were found. A second, ranking-only adjustment rewards substance: +10 for a ruling of 12,000
   characters or more, +5 if the appeal is (partly) upheld, -15 for the simplified procedure,
   -20 for inadmissibility or a struck-off case. These signals come from section 9 of
   `docs/style_guide.md`.
2. **Apertus (`apertus-v1-5-70b`).** The prompt holds the relevance criteria, the base rates
   learned from the labelled period, the topics of Suva's example summaries (few-shot pool only;
   the hold-out and the ruling's own example are never shown), the lawyers' feedback from the
   `feedback` table, the prior's hints and an excerpt of the ruling (rubrum, facts, reasons and
   operative part, up to 30,000 characters). It answers with JSON: a German explanation, key
   factors and a relevance level from 0 to 9.
3. **Score.** The level is read from the token logprobs as an expected value (for example 7.4
   instead of 7), which breaks the ties that a generated number produces: the first prompt
   asked for a 0-100 score, and the model gave 85 to almost every accident insurance ruling.
   Final score = 70 % level + 30 % prior (with the substance adjustment). Score 50 or more is
   labelled relevant.

## Results on the labelled period

Ranking metrics per quarter, because the judges look at the top 30 of one quarter. Each quarter
has 28 or 31 relevant rulings among about 2,000.

| Version | Quarter | P@10 | P@30 | R@30 | R@60 |
|---|---|---|---|---|---|
| v1: LLM 0-100 score only | Q4 2025 | 0.50 | 0.60 | 0.64 | 0.89 |
| | Q1 2026 | 0.40 | 0.33 | 0.32 | 0.74 |
| Prior only, no LLM | Q4 2025 | 0.80 | 0.63 | 0.68 | 0.82 |
| | Q1 2026 | 0.50 | 0.63 | 0.61 | 0.74 |
| v3: LLM level only | Q4 2025 | 0.70 | 0.67 | 0.71 | 0.89 |
| | Q1 2026 | 0.70 | 0.47 | 0.45 | 0.77 |
| **v3: LLM level + prior (shipped)** | **Q4 2025** | **0.80** | **0.70** | **0.75** | **0.86** |
| | **Q1 2026** | **0.70** | **0.57** | **0.55** | **0.77** |

`python -m suva.eval.score_triage` over both quarters together (59 relevant rulings, 3,934
scored):

| metric | value |
|---|---|
| coverage | 1.00 |
| precision@10 | 0.90 |
| precision@30 | 0.70 |
| recall@30 | 0.36 |
| recall@60 | 0.64 |
| rulings with score >= 50 | 117 |
| recall at score >= 50 | 0.85 |
| precision at score >= 50 | 0.43 |

- The pre-filter is recall-safe: 306 of 3,934 rulings reach the LLM, and all 59 relevant
  rulings are among them. The lowest relevant ruling has a prior of 35, against a cutoff of 20.
- Prior weights from 0.25 to 0.4 change P@30 by at most 0.03; 0.3 is the shipped value.
- What the ranking misses is mostly invalidity insurance: Suva lists 16 of the 198 IV rulings,
  and they read like the IV rulings it did not list. Over both quarters, the 21 relevant rulings
  outside the top 60 are all 16 IV rulings plus 5 accident insurance rulings ranked 65-74. False positives in the top 30 are thorough accident insurance rulings
  that Suva did not list (for example 8C_221/2025, 8C_201/2025, 8C_361/2025).

## Model choice

The gateway offers `apertus-v1-5-70b`, `apertus-v1-5-70b-thinking`, `apertus-v1-5-8b` and
`apertus-v1-5-8b-thinking`. A triage call to the 70B model takes about 5 seconds; the shared
gateway handled 10 to 60 calls per minute with 8-12 parallel workers, so a quarter (about 190
LLM calls after the pre-filter) takes 5-20 minutes. That is fast enough, so the 70B model is
used. The thinking variant returned no separate reasoning on this task and gave the same kind
of answer, so it adds nothing here.

## April-June 2026

`data/results/triage_2026q2.jsonl` holds 2,096 rulings decided 2026-04-01 to 2026-06-30: 1,908
ruled out by the pre-filter, 188 rated by Apertus, 68 labelled relevant. All are prompt version
`v3`. Load it with `make load` (or `uv run suva import-triage data/results/triage_2026q2.jsonl`).

## Reproduce

```sh
uv run suva load
uv run suva triage --from 2025-10-01 --to 2026-03-31 --workers 12
uv run suva export-triage triage_q4q1.jsonl --from 2025-10-01 --to 2026-03-31
uv run python -m suva.eval.score_triage triage_q4q1.jsonl --threshold 50
uv run suva triage --from 2026-04-01 --to 2026-06-30
uv run suva export-triage data/results/triage_2026q2.jsonl --from 2026-04-01 --to 2026-06-30
```

Calls use temperature 0 and are cached under `data/cache/llm/`. A rerun with the same model,
prompt version and feedback reuses the cache. New lawyer feedback changes the prompt and
triggers fresh calls.

## Limitations

- The labels describe Suva's choices in one half-year. Base rates and examples in the prompt
  come from that same period, so the numbers above are optimistic for a new quarter. The
  example summary of the ruling being scored is never shown to the model.
- Explanations are asked for in German, but on French rulings the model sometimes answers in
  French (1 of 188 in April-June 2026, 8C_344/2025). They are also often longer than the
  requested 2-3 sentences (median 4).
- Decisions that are not Federal Court rulings, such as the Basel-Landschaft cantonal decision
  on Suva's list, are outside the corpus and cannot be found.
