# Baseline: Apertus 70B against Gemini 3.8 Flash

What the same pipelines achieve with a different model, for comparison only. The product stays
100 % Apertus: every relevance decision, category and summary it shows comes from
`apertus-v1-5-70b`. This page swaps the model and nothing else, and states which side the setup
favours.

## Pitch table

| | Apertus 70B (shipped) | Gemini 3.8 Flash (same pipeline) |
|---|---|---|
| Relevance (P@30 / R@60 per quarter, Q4 · Q1, generated level for both) | 0.70 / 0.93 · 0.63 / 0.77 | 0.67 / 0.89 · 0.67 / 0.84: a tie, within 1-2 rulings per quarter |
| Summaries (10 hold-out rulings x DE/FR, blind reading) | outcome right in 20 of 20; 36 factual errors, 2 of 20 texts error-free | preferred in 20 of 20; outcome right in 20 of 20; 2 factual errors, 18 of 20 error-free |
| Categories (55 examples, primary correct) | 0.75 | 0.80 (3 rulings more) |
| Speed / cost | 268 s per summary (median), 3-5x slower on the shared hackathon gateway; about $0.08 per summary at Swiss hosting prices | 69 s per summary; about $0.08 per summary at Google's list price |
| Sovereignty | open weights, runs on-prem or air-gapped in Switzerland | US cloud API only; rulings and drafts leave Suva's network |

In short: relevance and categories are at par, and summaries are where a frontier cloud model
is clearly ahead, on legal accuracy as well as on style. The prompts were tuned on Apertus over
several rounds and were run unchanged on Gemini, so the setup favours Apertus; Gemini's numbers
are a lower bound for what a Gemini-tuned pipeline would reach. The summary reading was done by
an LLM, not by Suva's lawyers. Suva's labels partly reflect how many rulings the legal team had
time to summarise, so differences of one or two rulings per quarter are noise.

## Method

- **Same code, same prompts.** `python -m suva.eval.baseline` (`src/suva/eval/baseline.py`)
  calls the product functions `triage.triage_ruling` (prompt `v5`),
  `summarize.summarize_ruling` (summary `v6`, headlines `v3`) and `classify.classify_ruling`
  (`v4`) with a client for the chosen model. Gemini is reached through its OpenAI-compatible
  endpoint (`https://generativelanguage.googleapis.com/v1beta/openai/`), Apertus through the
  hackathon gateway. Temperature 0, token limits and retries as in the product.
- **Fresh runs for both models.** Each model has its own response cache
  (`data/cache/llm-baseline/<model>/`), started empty, so calls, tokens and time are measured for
  both in the same session (2026-11-27). Every endpoint call is logged with its prompt and
  output tokens and its duration. Results go to an output directory, never to the app database
  or `data/results/`.
- **Gemini without thinking.** Gemini 3.8 Flash thinks by default, and its thinking tokens count
  against `max_tokens`. With the product's limits (300 tokens for a classification, 900 for a
  triage answer) the default run spent the budget on thinking: 15 of 118 classification replies
  were empty and most others cut off mid-JSON, so 18 of 54 rulings fell back to the subject-line
  rule (primary correct 0.67, 2.2 calls per ruling). All runs below use
  `reasoning_effort=none`, which turns thinking off; Apertus 70B (instruct) does not think either.
- **Relevance level.** The product reads the level from the logprobs of the digit the model
  writes (an expected value, 7.4 instead of 7). Gemini's endpoint rejects `logprobs`, so its
  level is the generated digit. For an even comparison Apertus is scored the same way, from the
  same replies (`--scoring generated`); the shipped scoring (`expected`) is shown as well.
- **Inputs.** Triage: all 3,934 rulings of Q4 2025 and Q1 2026; 306 pass the prior, 224 the
  gate and reach the model, scored against Suva's 59 listed rulings
  (`data/eval/relevant_q4_2025_q1_2026.json`) with `suva.eval.score_triage`. Summaries: the 10
  hold-out rulings of `data/eval/split.json`, scored with `suva.eval.score_summaries` and read
  blind. Categories: the 55 labelled examples, scored with `suva.eval.score_classification`.

## Relevance

Per quarter, the judges look at the top 30 of one quarter:

| model | level | quarter | P@10 | P@30 | R@30 | R@60 |
|---|---|---|---|---|---|---|
| Apertus 70B | from logprobs (shipped) | Q4 2025 | 0.90 | 0.70 | 0.75 | 0.96 |
| | | Q1 2026 | 0.60 | 0.63 | 0.61 | 0.77 |
| **Apertus 70B** | **generated digit** | **Q4 2025** | **1.00** | **0.70** | **0.75** | **0.93** |
| | | **Q1 2026** | **0.50** | **0.63** | **0.61** | **0.77** |
| **Gemini 3.8 Flash** | **generated digit** | **Q4 2025** | **0.80** | **0.67** | **0.71** | **0.89** |
| | | **Q1 2026** | **0.70** | **0.67** | **0.65** | **0.84** |

The fresh Apertus run reproduces the committed v5 numbers in Q4 and differs by one ruling in Q1
(P@30 0.63 here, 0.60 committed); the gateway is not bit-for-bit deterministic. On the even
comparison (bold), Apertus is one ruling ahead in Q4 on P@30, R@30 and R@60 and Gemini two
rulings ahead in Q1 on R@60 and one on P@30 and R@30: no model wins on both quarters.

Pooled over both quarters (`score_triage --threshold 50`):

| metric | Apertus, logprobs | Apertus, generated | Gemini, generated |
|---|---|---|---|
| precision@10 | 0.70 | 0.70 | 1.00 |
| precision@30 | 0.67 | 0.73 | 0.70 |
| recall@30 | 0.34 | 0.37 | 0.36 |
| recall@60 | 0.68 | 0.66 | 0.64 |
| rulings with score >= 50 | 109 | 109 | 75 |
| recall at score >= 50 | 0.81 | 0.81 | 0.75 |
| precision at score >= 50 | 0.44 | 0.44 | 0.59 |

Gemini is stricter: it gives lower levels, labels a third fewer rulings relevant, and is more
precise and less complete at the threshold. The threshold of 50 was set for Apertus.

Listed rulings outside the top 60 (generated level):

| quarter | Apertus 70B | Gemini 3.8 Flash |
|---|---|---|
| Q4 2025 | 8C_531/2025, 9C_699/2024 | 9C_690/2024, 9C_382/2025, 8C_275/2025 |
| Q1 2026 | 8C_314/2025, 8C_149/2025, 8C_418/2025, 8C_272/2025, 8C_450/2025, 9C_65/2025, 9C_145/2025 | 8C_272/2025, 8C_368/2025, 9C_145/2025, 8C_418/2025, 8C_18/2026 |

Both miss mostly invalidity insurance (IV) rulings, the hard group of `docs/eval_triage.md`, but
not the same ones: Gemini finds four listed IV rulings in Q1 that Apertus misses (8C_314/2025,
8C_149/2025, 8C_450/2025, 9C_65/2025) and two in Q4 (8C_531/2025, 9C_699/2024), and misses two
other IV rulings in Q4 (9C_690/2024, 9C_382/2025). It also misses three accident insurance
rulings that Apertus ranks in the top 60: 8C_275/2025 (causality), 8C_368/2025 (cantonal
procedure) and 8C_18/2026 (daily allowance). Missing core accident insurance rulings costs Suva
more than missing borderline IV ones.

## Summaries

Both models ran the full v6 pipeline (holdings, two drafts, rule and claim checks, revisions,
consistency check, finishing) on the 10 hold-out rulings, never shown to either model.

`score_summaries` against Suva's human summaries:

| | lang | length ratio | ROUGE-L | chrF | glossary recall | style issues |
|---|---|---|---|---|---|---|
| Apertus 70B | de | 1.00 | 0.19 | 43.3 | 0.64 | 0 |
| | fr | 0.88 | 0.24 | 41.7 | 0.71 | 0 |
| Gemini 3.8 Flash | de | 1.07 | 0.21 | 43.5 | 0.61 | 0 |
| | fr | 1.00 | 0.24 | 42.0 | 0.73 | 0 |

A tie: wording overlap with one human reference does not separate the two.

### Blind reading

Two fresh Claude sub-agents, with no knowledge of the models or of earlier results, each read
five rulings in full and both models' German and French summaries, labelled A and B at random
per ruling (`baseline blind`, which writes the key outside the packet; opened only after both
readings).
For each summary they judged the outcome, listed every fact, figure, date, statute or
consideration reference the ruling does not support and every holding stated with the wrong
meaning, and scored coverage of the holdings, closeness to VIL's style (`docs/style_guide.md`,
sections 1, 3, 4 and 11) and the quality of the German or French from 1 to 5, then picked the
better summary. Gemini was side A for 2 rulings and B for 8.

| per summary (20 each) | Apertus 70B | Gemini 3.8 Flash |
|---|---|---|
| preferred | 0 | **20** |
| outcome stated correctly | 20 | 20 |
| error-free | 2 | **18** |
| factual errors | 36 (13 of them wrong consideration references) | **2** |
| coverage of holdings (1-5) | 3.15 | **4.55** |
| closeness to VIL's style (1-5) | 2.85 | **4.65** |
| German / French quality (1-5) | 3.25 | **4.60** |

The outcome is right for both because the pipeline checks the closing sentence against the
operative part and replaces a wrong one. Everything that check does not cover favours Gemini.
The most serious errors, all Apertus:

- **8C_78/2025, both languages:** the rule of Art. 6 Abs. 2 UVG turned around: "die
  Leistungspflicht ... für eine Listenverletzung ... voraussetzt, dass die Verletzung vorwiegend
  ... auf Abnützung oder Erkrankung zurückzuführen ist". The insurer is released when it is.
  The German text also keeps the anonymised "Dr. med. D.________" and "Dr. med. E.________",
  which the finishing step should replace by roles.
- **8C_508/2025, both languages:** "die Integritätsentschädigung [bemisst sich] nach dem
  aktuellen Gesundheitszustand" (E. 3.1), where Art. 36 Abs. 4 UVV (E. 3.3) requires
  foreseeable aggravations to be taken into account; the French adds "avec certitude" for
  a standard of preponderant probability.
- **8C_356/2025 de:** the adequacy test misstated (the ruling requires three of the seven
  criteria, or one in pronounced form).
- **8C_313/2024 and 8C_613/2025:** procedural history wrong: the cantonal court's reformatio
  in peius to 41 % presented as the IV office's decision; "verweigerte die beantragte
  Rückerstattung" for the refused waiver, and "hatte die Gutheissung der Einsprache aufgehoben"
  for an objection that was rejected.
- **8C_185/2025 de:** the reason the repayment was not time-barred stated wrongly (the
  Vorbescheid of 21 May 2024 stopped the time limit; it was not when the office learnt of the
  claim).

Gemini's two errors: 8C_313/2024 fr calls the cantonal pension "un quart de rente" where it is
27.5 % of a full pension, and 8C_613/2025 de writes CHF 16'751.- for CHF 16'751.65.

`docs/eval_summaries.md` found none of these error types in its reading of an earlier
Apertus run. This reading counts more strictly (every consideration reference is checked) and
reads a new v6 run; the gateway is not deterministic, so single errors vary between runs.

## Categories

| | Apertus 70B | Gemini 3.8 Flash |
|---|---|---|
| primary category correct | 0.75 | 0.80 |
| gold category among primary + secondary | 0.75 | 0.93 |
| branch correct (45 with a branch label) | 0.98 | 0.98 |
| rulings with secondary categories | 0 of 55 | 34 of 55 |

Committed v4 numbers (`docs/eval_classification.md`): 0.75 / 0.76 / 0.98; the fresh Apertus
run matches. Primary category is the fair measure: Gemini gets three more rulings right
(8C_313/2024, 8C_498/2024, 8C_458/2025) and none fewer. The second row favours Gemini, which
names one or two secondary categories for most rulings where Apertus names none; 7 of its hits
are only a secondary category. Both share the misses where Suva's summary focuses on a side
issue of the ruling (8C_607/2024, 8C_720/2024, 8C_44/2025, 8C_145/2025, 8C_241/2025,
9C_581/2024) and 4A_106/2025, which the routing rule classifies without a model. The prompt was
tuned on these 55 examples with Apertus.

## Speed, calls and cost

| task | model | calls | calls/ruling | prompt tokens | output tokens | wall time | seconds per call |
|---|---|---|---|---|---|---|---|
| triage (224 rulings) | Apertus 70B | 224 | 1.0 | 2,101,876 | 50,582 | 399 s | 13.8 |
| | Gemini 3.8 Flash | 224 | 1.0 | 2,090,042 | 61,406 | 136 s | 4.3 |
| categories (54 rulings) | Apertus 70B | 54 | 1.0 | 339,693 | 6,007 | 191 s | 27.8 |
| | Gemini 3.8 Flash | 54 | 1.0 | 338,779 | 4,876 | 39 s | 4.8 |
| summaries (10 rulings) | Apertus 70B | 144 | 14.4 | 739,326 | 65,669 | see below | 27.9 |
| | Gemini 3.8 Flash | 134 | 13.4 | 738,316 | 71,863 | 232 s | 5.4 |

A summary takes Gemini a median of 69 s (52-98 s, 9-18 calls) and Apertus 268 s (199-1,006 s,
12-19 calls), counting each ruling's calls back to back as the pipeline makes them. The first
Apertus summary run lost 5 of the 10 rulings to timeouts: under the team's load the gateway
took more than the client's 120 s for some 20,000-token calls, five times in a row. The rerun
resumed them from the cache with a 600 s timeout (`LLM_TIMEOUT=600`, 2 rulings in parallel),
1,967 s plus 462 s of wall time. Gemini needed no rerun.

Apart from those timeouts, no ruling failed in any run (no exception, no fallback). Triage and
categories ran with 8 rulings in parallel, summaries with 4. The Apertus gateway was shared with
the rest of the team during the runs, so its times are an upper bound.

Cost at list prices, per 1M tokens:

- Gemini 3.8 Flash, Google paid tier: $0.75 input, $3.75 output (thinking included) until
  2026-12-31, then $1.50 and $7.50 ([pricing](https://aistudio.google.com/docs/pricing)).
- Apertus 70B: free on the hackathon gateway. As a reference, Swiss hosting at Infomaniak is
  listed at about $0.8 input and $3 output per 1M tokens (aggregator listings, e.g.
  [Eden AI](https://www.edenai.co/models/apertus-v1-5-70b)).

| task | Apertus 70B (Infomaniak reference) | Gemini 3.8 Flash (Google list price) |
|---|---|---|
| triage, 224 rulings | $1.83 | $1.80 |
| summaries, 10 rulings | $0.79 | $0.82 |
| categories, 54 rulings | $0.29 | $0.27 |
| **per summary** | **$0.08** | **$0.08** |

Prompts dominate (the ruling text), and the input prices are almost the same, so the cost is a
tie. From 2027 Gemini's list price doubles.

At these prices a quarter of triage (about 115 rulings reach the model) costs under $1 with
either model. On-prem Apertus costs hardware instead of tokens.

## Fairness caveats

- **Prompts tuned on Apertus.** Every prompt, threshold and repair step was developed on
  Apertus output; the Gemini numbers come from an untuned transfer.
- **Thinking off.** Gemini runs without thinking to fit the product's token limits; with
  thinking and larger limits it may do better, at higher cost and latency.
- **Level without logprobs.** The product's triage reads Apertus' logprobs; Gemini cannot
  return them, so both are compared on the generated digit, which is not the shipped scoring.
- **Labels reflect capacity.** Suva lists about 30 rulings per quarter, partly because of time;
  unlisted rulings in a top 30 are often equally relevant, so precision understates both models.
- **LLM reader.** The blind reading was done by Claude sub-agents, not by Suva's lawyers. They
  quote the ruling for every error, so the errors can be checked, but a commercial model may
  share stylistic preferences with another commercial model.
- **Small samples.** 59 listed rulings, 10 summaries, 55 categories: one ruling moves a metric
  by 0.02 to 0.10.
- **Sovereignty.** Gemini is a US cloud service and cannot run on-prem or air-gapped; using it
  would send the rulings, drafts and any internal notes to Google. Apertus is open-weight and
  Swiss, and the product is built on it for that reason.

## Reproduce

```sh
cp <team .env with LLM_* and GEMINI_API_KEY> .env
A="--model apertus-v1-5-70b --out out/apertus"
G="--model gemini-3.8-flash --reasoning-effort none --out out/gemini"
for task in classify summaries; do
  uv run python -m suva.eval.baseline $task $A
  uv run python -m suva.eval.baseline $task $G
done
uv run python -m suva.eval.baseline triage $A
uv run python -m suva.eval.baseline triage $A --scoring generated  # same replies, from the cache
uv run python -m suva.eval.baseline triage $G --scoring generated
uv run python -m suva.eval.baseline usage out/apertus
uv run python -m suva.eval.baseline usage out/gemini
uv run python -m suva.eval.baseline blind out/apertus/summaries_apertus-v1-5-70b.jsonl \
  out/gemini/summaries_gemini-3.8-flash.jsonl --out out/blind --seed SEED
```
