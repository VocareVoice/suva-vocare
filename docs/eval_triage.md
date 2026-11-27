# Triage evaluation

How well `src/suva/triage.py` (prompt version `v5`) ranks the rulings Suva considered relevant,
tuned on Q4 2025 and Q1 2026 (labels: `data/eval/relevant_q4_2025_q1_2026.json`, 59 Federal
Court rulings; results in `data/results/triage_2025q4_2026q1.jsonl`) and then run over
April-June 2026 (`data/results/triage_2026q2.jsonl`).

## Method

1. **Segmenter (deterministic).** `src/suva/segment.py` cuts each ruling into rubrum, facts,
   numbered considerations (each classed as admissibility, substantive, costs or facts),
   dispositive and signature, in German, French and Italian. It finds every boundary in 6,001
   of the 6,030 rulings of the corpus and in all 1,085 rulings of 8C/9C; the 29 others are
   withdrawals and notices without a reasons heading or numbered considerations. The prior and
   the excerpt below read their parts from it.
2. **Prior (deterministic).** Subject line of the ruling (accident or military insurance +45,
   invalidity insurance +25), division (8C +10, 9C +5), and, unless the subject is invalidity
   insurance, Suva/CNA/INSAI in the rubrum (+15) or elsewhere (+10), UVG/UVV citations (up to
   +15) and military or accident insurance mentioned (+10, +5); ATSG citations (+5). Rulings
   below 20 are labelled not relevant without an LLM call and get an explanation in German and
   in French listing the hints that were found. A second, ranking-only adjustment rewards
   substance: +10 for a ruling of 12,000 characters or more, +10 for a five-judge panel (Art. 20
   Abs. 2 BGG, questions of principle), +15 for an invalidity insurance appeal by the IV office,
   the BSV or a pension fund, +5 if the appeal is (partly) upheld, -15 for the simplified
   procedure, -20 for inadmissibility or a struck-off case. These signals come from section 9 of
   `docs/style_guide.md` and the reading studies summarised under "v5" below.
3. **Gate (deterministic).** A ruling that does not decide on the merits gets no LLM call: not
   entertained or struck off (first item of the operative part), a single-judge decision, or no
   substantive consideration. It is labelled not relevant with model `gate` and a German and
   French explanation naming the reason. None of the 82 gated rulings of the labelled period is
   on Suva's list.
4. **Apertus (`apertus-v1-5-70b`, set in `triage.MODEL`).** The prompt holds the relevance criteria, the base rates
   learned from the labelled period, the topics of Suva's example summaries (few-shot pool only;
   the hold-out and the ruling's own example are never shown), the German = French pairs of the
   glossary statutes and terms that occur in the ruling (`data/eval/glossary.json`), the prior's
   hints and an excerpt of the ruling (rubrum, facts, reasons and operative part, up to 30,000
   characters). It answers with JSON: an explanation in German and one in French (two sentences
   each, each written in its own legal language rather than translated), key factors and a
   relevance level from 0 to 9. Since v5 the prompt adds that a ruling on whether the insurer or
   the cantonal court had to hear an objection or appeal is a procedural question under the
   ATSG and is rated like a ruling on the merits, not like the Federal Court's own non-entry
   decisions. Lawyer feedback is not part of the prompt: that feature is
   deferred, the `feedback` table and its endpoint stay for later.
5. **Checks on the explanations.** Each explanation must be written in its language (counted
   function words). A wrong one gets one rewrite request; if it is still wrong, the ruling fails
   and the next `suva triage` run retries it. Statute abbreviations of the other language, or
   Italian ones from an Italian ruling, are replaced by their glossary counterpart ("Art. 73
   lit. b OLAA" becomes "Art. 73 lit. b UVV" in German), because the model keeps them even when
   asked to rewrite. A relevance level the model writes into the text ("Stufe 7.") is dropped.
6. **Score.** The level is read from the token logprobs as an expected value (for example 7.4
   instead of 7), which breaks the ties that a generated number produces: the first prompt
   asked for a 0-100 score, and the model gave 85 to almost every accident insurance ruling.
   Final score = 70 % level + 30 % prior (with the substance adjustment). Score 50 or more is
   labelled relevant.

v4 fixes a bug in step 6: the full-width digit "９" among the alternative tokens overwrote the
probability of "9", so a confident level 9 could count as about 2. Fixing it changed 78 of the
306 levels of the v4a run (23 by more than one step); in the v4c run it had put two listed
rulings that the model rated 9 at about 2. The v3 numbers below were measured with the bug.

## Results on the labelled period

Ranking metrics per quarter, because the judges look at the top 30 of one quarter. Each quarter
has 28 or 31 relevant rulings among about 2,000.

| Version | Quarter | P@10 | P@30 | R@30 | R@60 |
|---|---|---|---|---|---|
| v1: LLM 0-100 score only | Q4 2025 | 0.50 | 0.60 | 0.64 | 0.89 |
| | Q1 2026 | 0.40 | 0.33 | 0.32 | 0.74 |
| Prior only, no LLM | Q4 2025 | 0.80 | 0.63 | 0.68 | 0.82 |
| | Q1 2026 | 0.50 | 0.63 | 0.61 | 0.74 |
| v3: LLM level + prior (previous) | Q4 2025 | 0.80 | 0.70 | 0.75 | 0.86 |
| | Q1 2026 | 0.70 | 0.57 | 0.55 | 0.77 |
| v4: LLM level + prior (previous) | Q4 2025 | 0.90 | 0.67 | 0.71 | 0.89 |
| | Q1 2026 | 0.60 | 0.60 | 0.58 | 0.74 |
| **v5: segmenter, gate, IV prior, procedural sentence (shipped)** | **Q4 2025** | **0.90** | **0.70** | **0.75** | **0.96** |
| | **Q1 2026** | **0.60** | **0.60** | **0.58** | **0.77** |

v5 is better than v4 in Q4 on P@30, R@30 and R@60 (one, one and two more listed rulings) and in
Q1 on R@60 (one more), and worse on no metric in either quarter. Which change does what is in
"v5: changes checked across quarters".

v3 and v4 both use `apertus-v1-5-70b`. Every v4 metric is within one ruling of v3: in Q4 one
more listed ruling in the top 10 and in the top 60, one fewer in the top 30; in Q1 one more in
the top 30, one fewer in the top 10 and in the top 60. The tuning below did not find a change
that improves a held-out quarter, so v4 is about as good as v3 at ranking and adds the French
explanation, the checks on both texts and the fixed level.

`python -m suva.eval.score_triage` over both quarters together (59 relevant rulings, 3,934
scored):

| metric | v3 | v4 | v5 |
|---|---|---|---|
| coverage | 1.00 | 1.00 | 1.00 |
| precision@10 | 0.90 | 0.70 | 0.70 |
| precision@30 | 0.70 | 0.67 | 0.73 |
| recall@30 | 0.36 | 0.34 | 0.37 |
| recall@60 | 0.64 | 0.66 | 0.69 |
| rulings with score >= 50 | 117 | 124 | 109 |
| recall at score >= 50 | 0.85 | 0.83 | 0.85 |
| precision at score >= 50 | 0.43 | 0.40 | 0.46 |

Pooled over both quarters, the top 10 holds more thorough accident insurance rulings that Suva
did not list: with the fixed level, Apertus rates them 9 and they score 96-99.

- The pre-filter and the gate are recall-safe: 306 of 3,934 rulings pass the pre-filter and 224
  of them the gate, and all 59 relevant rulings are among them. The lowest relevant ruling has
  a prior of 35, against a cutoff of 20.
- What the ranking misses is mostly invalidity insurance (next sections).

## v5: changes checked across quarters

v5 implements the recommendations of four reading studies of the labelled period (segmenter,
accident insurance, invalidity insurance, cited statutes). Each change was run on both quarters
with `apertus-v1-5-70b` on top of the previous row and kept only if neither quarter got worse
on any of the four metrics.

| Step | Change | Q4 P@10 / P@30 / R@30 / R@60 | Q1 P@10 / P@30 / R@30 / R@60 | Decision |
|---|---|---|---|---|
| v4 | as shipped | 0.90 / 0.67 / 0.71 / 0.89 | 0.60 / 0.60 / 0.58 / 0.74 | baseline |
| 1 | Segmenter for the prior's sections and the excerpt | 0.90 / 0.67 / 0.71 / 0.89 | 0.60 / 0.60 / 0.58 / 0.74 | kept |
| 2 | Gate before the LLM (82 of 306 calls saved) | 0.90 / 0.67 / 0.71 / 0.89 | 0.60 / 0.60 / 0.58 / 0.74 | kept |
| 3a | IV subject: no Suva, UVG, military or accident insurance points | 0.90 / 0.70 / 0.75 / 0.89 | 0.60 / 0.60 / 0.58 / 0.74 | kept |
| 3b | 3a + IV appeal by the IV office, BSV or a pension fund +15 | 0.90 / 0.70 / 0.75 / 0.93 | 0.60 / 0.60 / 0.58 / 0.74 | kept |
| 3c | 3b + accident insurance appeal by the insurer +5 | 0.80 / 0.70 / 0.75 / 0.93 | 0.70 / 0.60 / 0.58 / 0.74 | rejected |
| 4a | 3b + procedural sentence (admissibility before the insurer or the cantonal court) | 0.90 / 0.70 / 0.75 / 0.96 | 0.60 / 0.60 / 0.58 / 0.77 | **kept: v5** |
| 4b | 3b + level 8 for a legal question, 7 for medical evidence only | 0.80 / 0.70 / 0.75 / 0.89 | 0.60 / 0.67 / 0.65 / 0.77 | rejected |
| 4c | 4a + 4b | 0.80 / 0.70 / 0.75 / 0.93 | 0.60 / 0.67 / 0.65 / 0.74 | rejected |

- **Step 1** changes no metric. It fixes three section bugs of the old regex split: the singular
  or colon-less heading "Erwägung" (4A_430/2025, 8C_258/2025, 7B_364/2026), French and Italian
  rulings with one heading for facts and law, whose rubrum was empty (so Suva in the rubrum
  counted as "Suva erwähnt" and the panel size was not read), and presidential orders whose
  operative part ("erkennt die Präsidentin", "ordonne") was not found. 36 candidates get a
  different prior; all of them are unlisted and stay far below the top 60.
- **Step 2** removes the inadmissible 8C_696/2025 from Q4's top 30 (replaced by the unlisted
  9C_358/2024) and saves 82 LLM calls in the labelled period and 57 of 188 in April-June 2026.
- **Step 3a.** None of the 17 IV rulings that name Suva is listed, and the Suva and accident
  insurance points had put three routine IV rulings that name Suva into Q4's top 30 (9C_64/2025,
  8C_397/2025, 9C_420/2025) and one into Q1's (9C_43/2025); all four drop below rank 30. **Step
  3b:** the appellant
  is the first party block of the rubrum ("Verfahrensbeteiligte" up to "gegen"); a named
  appellant (not "A.________") is an institution. This agrees with the reading studies on 200 of
  200 IV rulings and on 92 of 93 accident insurance rulings (the one difference is a military
  insurance appeal by Suva that the study had not counted; the gate removes it anyway).
  The listed IV office appeal 8C_185/2025 rises from Q4 rank 66 to 48.
- **Step 3c** fails the rule: it lifts the unlisted Allianz appeal 8C_29/2025 into Q4's top 10,
  in a band of scores 86-88 where one point reorders the list, and gains one listed ruling in
  Q1's top 10.
- **Step 4a** lifts 8C_368/2025 (listed; admissibility of an objection) from Q1 rank 102 to 36,
  which the accident insurance study predicted. The new sentence also moves three other listed
  rulings by wording noise: 8C_531/2025 and 8C_314/2025 rise, 8C_418/2025 falls out of Q1's top
  60.
- **Step 4b** encodes how Suva chose when its capacity was short (Q1: 4 of 18 rulings on medical
  evidence only listed) but not when it had room (Q4: 7 of 10). It helps Q1 P@30 and costs Q4
  two listed rulings in the top 60, the same quarter asymmetry as v4b and v4c.
- The `_UPHELD` signal now reads the outcome from the first item of the operative part
  (`classify.outcome`) instead of any "gutgeheissen" in its first 600 characters, which had
  counted granted legal aid as an upheld appeal. It changes one ruling's prior (8C_272/2025, by
  one point) and no metric.
- The invalidity insurance paragraph of the prompt is v4's. Earlier rewrites (v4b, v4c) raised
  all IV rulings, and the segmenter study found that Apertus cannot judge novelty or
  transferability to accident insurance reliably (24-30 % agreement with blind readers).
- The cited statutes are not part of the score: the statute study found that they restate the
  branch and the outcome, which the prior already holds, and that a citation boost would
  reinforce v4's false positives rather than fix its misses.

## Tuning, checked across quarters

Each change was judged on both quarters and kept only if it did not make either one worse. All
numbers are with the fixed level and a prior weight of 0.3. The tuning runs (v4a to v4d) used
`apertus-v1-5-70b-thinking`, the model configured in the team's `.env` at the time; the shipped
v4 was then run with `apertus-v1-5-70b` like v3. The final prompt scores about the same on both
models.

| Run | Change | Q4 P@10 / P@30 / R@30 / R@60 | Q1 P@10 / P@30 / R@30 / R@60 | Decision |
|---|---|---|---|---|
| v4a | v3 criteria, explanation in German and French, no feedback | 0.80 / 0.67 / 0.71 / 0.89 | 0.60 / 0.60 / 0.58 / 0.77 | baseline |
| v4b | Explicit rule for invalidity insurance (transferable rulings on level 5-6, five-judge panel 7-8), base rates removed, weight boosters (five judges, publication, change of case law) | 0.90 / 0.67 / 0.71 / 0.86 | 0.60 / 0.57 / 0.55 / 0.74 | rejected |
| v4c | Base rates replaced by a qualitative criterion ("for IV it does not matter whether Suva is a party"), five-judge panel as an example of level 9 | 1.00 / 0.67 / 0.71 / 0.93 | 0.70 / 0.57 / 0.55 / 0.65 | rejected |
| v4d | v4a plus five-judge panel in the prior, both abbreviation lists in the prompt, no level in the explanation | 0.70 / 0.67 / 0.71 / 0.89 | 0.60 / 0.63 / 0.61 / 0.77 | kept |
| v4 | v4d with `apertus-v1-5-70b` | 0.90 / 0.67 / 0.71 / 0.89 | 0.60 / 0.60 / 0.58 / 0.74 | shipped |

- v4b and v4c raised many invalidity insurance rulings to level 7-8 and pushed listed accident
  insurance rulings down. v4c improved Q4 but cost Q1 four listed rulings in the top 60. The
  prompt therefore keeps v3's criteria, including the base-rate paragraph: v4c replaced it
  together with two other changes and lost recall in Q1.
- Prior weight 0.2 to 0.5 and five-judge boost 0 to 20, choosing by P@30 + R@60 on the rounded
  scores that the database stores: on v4's levels, tuning on Q4 picks weight 0.5 and tuning on
  Q1 picks 0.5 with boost 15, and neither changes the held-out quarter. On the v4a and v4d
  levels the winners are 0.2, 0.3, 0.4 and 0.5. Weight 0.4 looked better before rounding and
  worse after it. No weight change transfers, so 0.3 stays.
- The five-judge boost changes no P@30 or R@60 in any run (v4: Q4 P@10 0.80 without it, 0.90
  with it). It stays because it is a general legal signal (Art. 20 Abs. 2 BGG, style guide
  section 9.4), not a fitted one.
- The scores cluster, so thresholds from 45 to 60 change the number labelled relevant by at
  most three per quarter. At 50: Q4 49 (recall 0.86), Q1 75 (recall 0.81). The threshold stays
  at 50.
- The differences between versions are one to three rulings per quarter, while a rewording of
  the prompt moves single levels by several steps. Treat the per-quarter numbers as accurate to
  about ±0.05.

## Invalidity insurance: listed and not listed

Suva lists 16 of the 200 invalidity insurance (IV) rulings of the labelled period. Features of
the 8C/9C rulings with an IV subject, from `triage.prior` and the corpus:

| Feature | Listed (16) | Not listed (184) | Listed among rulings with the feature |
|---|---|---|---|
| Five-judge panel | 3 | 3 | 3 of 6 |
| Appeal (partly) upheld | 7 | 26 | 7 of 33 |
| Simplified procedure | 0 | 65 | 0 of 65 |
| Inadmissible or struck off | 0 | 27 | 0 of 27 |
| 12,000 characters or more | 12 | 100 | 12 of 112 |
| ATSG/LPGA cited | 16 | 123 | 16 of 139 |
| UVG cited or accident insurance mentioned | 2 | 31 | 2 of 33 |
| Suva named | 0 | 17 | 0 of 17 |
| Division 8C (rest 9C) | 10 | 117 | 10 of 127 |
| French | 2 | 55 | 2 of 57 |

The usable signals (five judges, appeal upheld, simplified procedure, inadmissibility) are in
the prior; a link to accident insurance or to Suva does not separate the two groups. Suva's
example summaries of IV rulings state a rule on a topic that accident insurance shares:
revision (8C_313/2024), helplessness (8C_185/2025, 8C_314/2025, 8C_531/2025), the weight of
expert opinions (8C_450/2025), employability on the labour market (8C_535/2024), Soziallohn
(9C_382/2025), delay and costs under the ATSG (9C_65/2025). The unlisted IV rulings cover the
same topics. Apertus decides almost all-or-nothing for IV: the same topic gets level 7 in one
ruling and 2-3 in the next, with explanations such as "Suva is not a party". Making the rule
explicit (v4b, v4c) did not separate listed from unlisted rulings; it raised all of them.

## Misses and false positives (v5)

Listed rulings outside the top 60:

| Quarter | Rank | Docket | Score | Subject |
|---|---|---|---|---|
| Q4 2025 | 69 | 9C_699/2024 | 30 | Invalidenversicherung (Invalidenrente) |
| Q1 2026 | 65 | 9C_311/2025 | 62 | Invalidenversicherung |
| Q1 2026 | 67 | 8C_418/2025 | 51 | Unfallversicherung |
| Q1 2026 | 68 | 8C_149/2025 | 39 | Invalidenversicherung (Invalidenrente) |
| Q1 2026 | 79 | 8C_450/2025 | 34 | Invalidenversicherung (Invalidenrente; berufliche Massnahmen) |
| Q1 2026 | 86 | 8C_272/2025 | 31 | Invalidenversicherung (Invalidenrente) |
| Q1 2026 | 94 | 9C_65/2025 | 28 | Assicurazione per l'invalidità (diniego di giustizia e ritardata giustizia; spese giudiziarie in procedura cantonale) |
| Q1 2026 | 95 | 9C_145/2025 | 28 | Invalidenversicherung |

v4 missed 11; v5 brings 8C_185/2025, 8C_531/2025, 8C_314/2025 and 8C_368/2025 into the top 60
and loses 8C_418/2025 (rank 67).

Not listed, in the top 30: Q4 2025 8C_221/2025, 8C_679/2024, 8C_151/2025, 8C_29/2025,
8C_512/2025 (accident insurance) and 9C_45/2025, 8C_104/2025, 8C_400/2025, 9C_234/2025
(invalidity insurance; 9C_45/2025 and 9C_234/2025 are IV office appeals that the IV study counts
among the unlisted rulings as quotable as the listed ones); Q1 2026 8C_201/2025, 8C_361/2025,
8C_56/2025, 8C_308/2025, 8C_564/2025, 8C_157/2025, 8C_384/2025, 8C_186/2025, 8C_322/2025,
8C_382/2025, 8C_246/2025, 8C_401/2025 (all accident insurance). The accident insurance study
read all of them: most are full judgments like the listed ones, and the Q1 ones cluster in
February 2026, when Suva listed 2 of 10 substantive accident insurance rulings.

## Checked against the labels, not changed

Under Art. 1 UVG the ATSG applies to accident insurance, so an IV ruling that interprets a
shared ATSG concept can matter to Suva. Three rules that follow from this were checked against
the labelled period (statutes from `data/results/classification_2025q4_2026q1.jsonl`, subjects
from the corpus). None was adopted:

| Candidate rule | Listed | Not listed | Listed share |
|---|---|---|---|
| All 8C/9C IV rulings (base rate) | 16 | 185 | 8 % |
| IV ruling citing Art. 8 / 16 / 17 ATSG | 6 / 3 / 2 | 45 / 46 / 43 | 12 / 6 / 4 % |
| IV ruling on helplessness (Art. 9 ATSG; Art. 26-27 UVG), from the subject | 3 | 4 | 43 % |
| UV/IV ruling with a procedural subject, decided on the merits | 2 | 16 | 11 % |

- **Shared ATSG articles** (invalidity, assessment of invalidity, revision) do not separate
  listed from unlisted rulings any better than the base rate.
- **Procedure.** Suva lists few rulings on ATSG procedure (cantonal procedure, admissibility,
  costs, delay), so a rule raising them would add mostly false positives. The two listed ones
  (8C_351/2025, 9C_65/2025) stay hard cases.
- **Helplessness** separates (3 of 7), but the prompt already names helplessness among the IV
  topics that carry over, and seven rulings are too few to tune on without fitting the same
  period that is used for evaluation. Worth checking again once a later quarter is labelled.

## Model choice

The gateway offers `apertus-v1-5-70b`, `apertus-v1-5-70b-thinking`, `apertus-v1-5-8b` and
`apertus-v1-5-8b-thinking`. A triage call to the 70B model takes 5 to 10 seconds; the shared
gateway handled 5 to 60 calls per minute with 8-12 parallel workers, so a quarter (about 190
LLM calls after the pre-filter) takes 5-40 minutes. That is fast enough, so the 70B model is
used. The thinking variant returned no separate reasoning on this task and gave the same kind
of answer, so it adds nothing here.

## April-June 2026

`data/results/triage_2026q2.jsonl` holds 2,096 rulings decided 2026-04-01 to 2026-06-30: 1,908
ruled out by the pre-filter, 57 by the gate, 131 rated by `apertus-v1-5-70b`, 68 labelled
relevant (v4: 70). All are prompt version `v5`, with the explanation in German and in French.
All of the top 30 are accident insurance rulings; 28 of them were also in v4's top 30
(8C_739/2025 and 8C_580/2025 replace 8C_27/2026 and the invalidity insurance ruling
8C_526/2025, now ranks 31 and 35), and the top 5 are the same five rulings.

`data/results/triage_2025q4_2026q1.jsonl` holds the v5 results for the labelled period (3,934
rulings, 224 rated by Apertus, 82 gated), so the UI shows the triage for that period too.
`make load` imports both files (or `uv run suva import-triage PATH`).

## Reproduce

```sh
uv run suva load
uv run suva triage --from 2025-10-01 --to 2026-03-31 --workers 12
uv run suva export-triage data/results/triage_2025q4_2026q1.jsonl --from 2025-10-01 --to 2026-03-31
uv run python -m suva.eval.score_triage data/results/triage_2025q4_2026q1.jsonl --threshold 50
uv run suva triage --from 2026-04-01 --to 2026-06-30
uv run suva export-triage data/results/triage_2026q2.jsonl --from 2026-04-01 --to 2026-06-30
```

Calls use temperature 0 and are cached under `data/cache/llm/`. A rerun with the same model and
prompt version reuses the cache.

## Limitations

- The labels describe Suva's choices in one half-year. Base rates and examples in the prompt
  come from that same period, so the numbers above are optimistic for a new quarter. The
  example summary of the ruling being scored is never shown to the model.
- Explanations have a median of 42 words in German and 48 in French; 12 of the 494 German ones
  (3 French) run to four sentences instead of two or three.
- Decisions that are not Federal Court rulings, such as the Basel-Landschaft cantonal decision
  on Suva's list, are outside the corpus and cannot be found.
