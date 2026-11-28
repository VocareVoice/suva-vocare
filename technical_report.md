# Technical report - Praecedens, Vocare

- **Challenge partner:** Suva
- **Challenge:** Identification of relevant Federal Court judgements and preparation of a legal summary
- **Event:** On-site Zurich
- **Team:** Vocare - Lucas Bernoulli, Thomas Frei
- **Project:** Praecedens
- **Demo:** `[PLACEHOLDER: link to the demo video, added before submission]`

## 1. Summary

Suva's lawyers read the Federal Supreme Court's new rulings by hand. They pick the rulings
that matter for accident insurance and write a short summary of each, in German and in French.
Praecedens, a pipeline plus a web application, does this first pass for them:

- It loads every ruling of a period (about 2,000 per quarter).
- It ranks the rulings by relevance to Suva and explains each rating in German and French.
- It sorts every social-law ruling into a two-level legal taxonomy.
- It writes a German and a French summary in Suva's house style for the top-ranked rulings,
  and stores everything in a searchable knowledge base.
- Lawyers can add any ruling by its number, correct a relevance score, and edit or regenerate
  a summary.
- A legal assistant agent answers case questions from the rulings and from the UVG, ATSG and UVV.

Every text the product shows comes from Apertus v1.5 70B. Everything else is plain code without
an LLM: fetching, segmentation, a keyword prior, a gate, fact extraction and rule checks.

- **Ranking.** We tuned it on the half-year Suva labelled: 59 listed rulings in Q4 2025 and
  Q1 2026. We kept a change only if it made neither quarter worse. All 59 pass the pre-filter
  and the gate. The top 60 holds 96 % of them in Q4 and 77 % in Q1. Most misses are invalidity
  insurance (IV) rulings.
- **Summaries.** We tested them on 10 hold-out rulings that the model never saw in a prompt.
  They follow the evaluator's structure, and the outcome is right in 20 of 20 texts. Their
  weak point is facts. A blind reading found 31 errors in the 20 texts (43 before v7's factual
  check). "Blind reading" means a reader who did not know which version wrote the text checked
  each sentence against the ruling. A lawyer must review each summary.
- **Deployment.** It runs on-premise or air-gapped, as Docker Compose with SQLite and one
  OpenAI-compatible Apertus API.

## 2. Architecture

![Architecture: build-time inputs, the batch pipeline, serving and the Apertus API](docs/architecture.svg)

*Figure 1 ([`docs/architecture.svg`](docs/architecture.svg)): grey boxes are plain code,
orange boxes call Apertus, blue boxes are data on disk. Every Apertus step calls one Apertus
API. Apart from that API, network access is needed only to refresh the data and to add a single
ruling by its number.*

| Component | Code | LLM | Role |
|---|---|---|---|
| Fetch | `src/suva/fetch/` | no | Downloads rulings from the entscheidsuche.ch mirror into `data/corpus/rulings.jsonl.gz` |
| Add a ruling | `ingest.py` | Apertus | One docket from entscheidsuche.ch: stored, classified and triaged |
| Segmenter | `segment.py` | no | Splits a ruling into rubrum, facts, numbered considerations (admissibility, substance, costs), operative part and signature, in DE/FR/IT |
| Triage | `triage.py` | Apertus | Keyword prior, merits gate, then a relevance level 0-9 with an explanation in DE and FR |
| Classification | `classify.py` | Apertus | Statutes, precedents, outcome and flags by rule; branch and legal category by Apertus |
| Summaries | `summarize.py`, `prompts/` | Apertus | DE and FR summaries plus one-line headlines, with rule checks, a factual check and revisions |
| Expert scores | `db.py`, `adjustments.py` | Apertus | Lawyers' score corrections, and a summary of what they have in common |
| Knowledge base | `db.py` | no | SQLite with FTS5 full-text search over rulings and summaries |
| API and UI | `api.py`, `web/` | no | FastAPI JSON API and a static DE/FR frontend served by the same process |
| Agent | `agent/` | Apertus | Legal assistant with tools over the laws and the knowledge base |
| Laws | `laws.py`, `data/laws/` | no | UVG, ATSG and UVV from Fedlex in DE and FR, committed as JSON |

**Fetch.** bger.ch blocks scripts with an Imperva/hCaptcha bot wall. So the crawler reads the
open-data mirror entscheidsuche.ch. It publishes one metadata file and one HTML file per
decision. The committed corpus holds all 6,030 rulings decided from 2025-10-01 to 2026-06-30.

**Triage** (prompt `v5`, `docs/eval_triage.md`) has four steps:

1. **Prior.** Code scores the subject line, the division, Suva/CNA in the rubrum, UVG/UVV/ATSG
   citations and insurance mentions. For ranking only, it adds points for substance: length,
   a five-judge panel, an IV appeal by the IV office or a pension fund, an upheld appeal. It
   subtracts points for the simplified procedure. Below 20 points a ruling is labelled not
   relevant without an LLM call. Its DE/FR explanation lists the hints found.
2. **Gate.** Code drops decisions that do not rule on the merits: not entertained, struck off,
   single-judge, or without a substantive consideration.
3. **Apertus 70B** gets the criteria, the base rates of the labelled period, the topics of
   Suva's few-shot examples, the matching DE=FR glossary terms, the prior's hints and up to
   30,000 characters of the ruling. It returns a level from 0 to 9 and a two-sentence
   explanation in each language. Each explanation is written in its own legal language and
   checked for it.
4. **Score.** The model returns, for each possible level, the probability it gives that token
   (its "logprobs"). We use the expected value of these, e.g. 7.4 instead of 7. We do this
   because a plain 0-100 score did not work: Apertus gave 85 to almost every accident insurance
   ruling. Final score = 70 % level + 30 % prior. A score of 28 or more means relevant. This
   cut-off has the best F2 on the labelled period (section 4).

**Classification** (prompt `v4`, `docs/eval_classification.md`).

- Code extracts statutes, precedents (BGE/ATF/DTF), the outcome and flags (five-judge panel,
  public deliberation, intended for publication).
- Apertus reads every ruling of the social-law divisions (8x/9x, 1,150 rulings). It picks a
  branch (UVG, IVG, MVG, ATSG/other, outside social insurance). It also picks a primary and up
  to two secondary categories from a closed list of 17. A JSON schema with enums limits the
  answer to these values.

**Summaries** (prompt `v7`, `docs/eval_summaries.md`, style in `docs/style_guide.md` section 11)
take 10 to 16 Apertus calls per ruling, plus about 25 short calls for the factual check:

1. **Source.** The ruling without costs, legal aid and the notification list (up to 70,000
   characters).
2. **Holdings.** Apertus lists the Court's conclusion for each numbered consideration. We added
   this step after the model once merged two considerations and inverted a holding.
3. **Two originals.** Apertus writes both languages from the ruling. The second uses the first
   as an outline. We do not translate, because Suva's own second-language texts are
   translations with artefacts. The style follows the expected evaluator VIL: facts, cantonal
   court, principles recalled, their application, outcome. A consideration reference closes
   each statement. Length: 150-200 words in German, 160-220 in French. Two of her summaries
   serve as few-shot examples.
4. **Rule checks.** Code checks the length; that references, statutes, figures and dates occur
   in the ruling; no names or birth years; Suva only as a party; no sentence that decides the
   appeal differently from the operative part; the target language's abbreviations and
   glossary terms. Failures go back to Apertus. An overlong text is shortened by Apertus. As a last resort,
   code cuts the sentences Apertus ranks as least needed.
5. **Consistency.** Apertus compares the two texts and names the version the ruling supports.
   The other one is revised.
6. **Factual check (v7).** For each sentence, Apertus copies the passage of the ruling it
   relies on. A passage that is not word for word in the ruling is dropped. Apertus
   then compares sentence and passage for the error types of the blind reading: who decided
   what, a rule with the wrong meaning, facts, figures of another stage. A flagged pair gets
   one more narrow question. Confirmed errors go to one revision. Then code checks the
   references against the segmented ruling, down to E. 3.3.2. A reference to a missing
   consideration or to the costs is repointed or removed. We tried asking for errors in the
   whole summary at once: Apertus found none in any of the 20 hold-out texts.
7. **Finishing.** Code normalises the text (section 3). Each run also writes a headline per
   language of at most about 12 words.

**Knowledge base and UI.** Results live in SQLite with an FTS5 full-text index. The UI (DE/FR):

- lists every ruling of a period with a sortable score, the explanation, badges and filters for
  the taxonomy (advanced filters behind "Erweitert");
- shows the original text, both summaries and headlines, and summarises any further ruling on
  demand;
- has "+ Urteil hinzufügen". It takes a ruling number (also `8c 129/2025` or `8C-129-2025`),
  looks it up on entscheidsuche.ch, stores, classifies and triages it, and opens it.

A lawyer can set their own score with a reason. It overrides the model's score and survives
later triage runs. It also moves the ruling into or out of the knowledge base. The view
"Anpassungen" lists the corrections next to the model's scores (section 4).

**Agent.** The agent has six tools: `read_article`, `list_rulings`, `search_rulings`,
`read_ruling`, `propose_summary` and `update_memory`. It makes at most 10 calls per question.
It answers in the user's language with clickable citations. If it cites a docket it has not
seen in a tool result, the answer is sent back once. A summary it proposes replaces the stored
one only when the lawyer accepts it. It is then marked `edited`.

### Target architecture (mandatory)

The project is deployable in all three settings. It is built for **a) on-premise** and
**b) air-gapped** operation. The same container also runs unchanged on **c) a sovereign Swiss
cloud** with a Swiss-hosted Apertus API.

- **One container plus the Apertus API.** `docker compose up --build` starts the API and UI on
  port 8000. It builds `data/suva.db` from the committed corpus and results (about 30 seconds).
  Every Apertus call goes to one OpenAI-compatible Apertus API, set by `LLM_BASE_URL`. We
  download no weights. For the hackathon this is the CSCS / Keera gateway. On-premise or
  air-gapped, the organisation serves the same API on its own GPUs, e.g. with vLLM (70B in
  BF16: about 140 GB, two 80 GB GPUs).
- **No other third-party calls at runtime.** No CDN, web fonts or analytics. The law texts are
  committed snapshots. "Open on bger.ch" is a plain hyperlink. The one exception is
  "+ Urteil hinzufügen", which reads entscheidsuche.ch. Air-gapped, new rulings come with the
  corpus transfer instead.
- **API features used:** chat completions, `logprobs`/`top_logprobs` (triage),
  `response_format: json_schema` (classification), and tool calls (agent).

| | Build time / data refresh (network) | Runtime |
|---|---|---|
| Code | Docker base images (Docker Hub, ghcr.io), PyPI packages pinned in `uv.lock` | none |
| Model | none, no weights are downloaded | the Apertus API (`LLM_BASE_URL`) |
| Rulings | `python -m suva.fetch` from entscheidsuche.ch; air-gapped: run it on a connected machine and transfer the corpus file | optional: one ruling by number |
| Laws | `python -m suva.laws` from Fedlex SPARQL | none |

**Transfer to Azure (bonus).** The image runs on Azure Container Apps or App Service, with
`./data` on an Azure Files volume. The three `LLM_*` variables point to an Apertus deployment,
e.g. vLLM on a GPU node in Switzerland North. No code changes are needed. Azure is a US-owned
provider. For Swiss jurisdiction (option c), a Swiss provider hosting Apertus fits better.

## 3. Use of Apertus

- **Model:** `swiss-ai/Apertus-v1.5-70B`, the regular instruct model (gateway id
  `apertus-v1-5-70b`, the default when `LLM_NAME` is empty). The app warns if `LLM_NAME` names a
  thinking variant.
- **How it is used:** inference (triage, classification, summaries, headlines, the corrections
  summary) and agents / tool use (the legal assistant). No fine-tuning, no adapters, no
  quantisation on our side.
- **Where it runs:** for the hackathon, the CSCS / Keera gateway (`https://gateway.keera.ch`).
  In production, any OpenAI-compatible server the organisation runs, set by `LLM_NAME`,
  `LLM_BASE_URL` and `LLM_API_KEY`.

| Step | Prompt | Calls | Parameters |
|---|---|---|---|
| Triage | `triage.py` (`v5`) | 1 per ruling that passes the gate | temperature 0, `logprobs`, top 10, 900 tokens |
| Classification | `classify.py` (`v4`) | 1 per 8x/9x ruling, up to 3 on an invalid reply | temperature 0, JSON schema with enums |
| Summaries | `prompts/summary_*.md` (`v7`) | 10-16 per ruling, plus about 25 for the factual check | temperature 0; 0.4 only to redraw a rejected shortening |
| Headlines | `prompts/headline.md` (`v3`) | 3-6 per ruling | temperature 0 |
| Corrections summary | `prompts/adjustments_summary.md` | 1 per request in "Anpassungen" | temperature 0, 1,200 tokens |
| Agent | `agent/prompt.md` | up to 10 tool steps per question | temperature 0.2, native tool calls |

All calls go through `src/suva/llm.py`. It is a thin OpenAI client with retries and an on-disk
response cache, keyed by model, messages and parameters.

**Model choice.** The thinking variant of the 70B reasoned on our long prompts only when we
prefilled the assistant turn. Its summaries were better on 3 rulings and worse on 4, and it
called the IV office "l'assureur-accidents". So all steps use the regular 70B.

**What we tried and dropped.** We tested each idea with the cross-quarter rule (keep it only if
neither quarter gets worse):

- Triage per consideration, then merged: no better than noise, for 6.4 times the calls. We kept
  its segmenter and gate; the gate saves 27 % of the calls.
- Cited statutes as a score component.
- An explicit invalidity insurance rule: it raised all IV rulings, listed or not.
- A third few-shot example chosen by similarity: the model copied its facts.
- Apertus as a judge of summaries: it rated a correct summary as reversing the outcome.
- In v7, moving every reference to the consideration of its passage: it broke six correct
  references while fixing one.

**Hackathon rule compliance: only Apertus generates text.** Every explanation, category,
summary, headline and agent answer the product shows comes from Apertus. No summary in
`data/results/` was written or corrected by hand or by another LLM. The UI can store a
lawyer's edit or score. It is then marked `edited` or "Von Fachperson angepasst", and none is in
the submitted results. After Apertus, only rule-based code changes the text:

- It replaces statute abbreviations of the other language from the glossary. It normalises
  citation format, Swiss amounts, "Suva" for "CNA" and French superscripts. It gives a word
  copied with a typo the ruling's spelling.
- It turns a closing sentence with the wrong result or party into a standard formula from the
  rubrum and the operative part. It repoints or removes a reference to a consideration that
  does not exist.
- It takes the insured person's gender from the parties block and replaces a leftover
  anonymised name with the role. It adds "Fünfer-Entscheid." / "Décision à cinq.".
- As a last resort, it deletes the sentences Apertus ranked as least needed.

The German few-shot examples (`src/suva/prompts/style_examples_de.json`) are German renderings
of VIL's French originals. They are prompt input, never output. Other models appear only in
evaluation: Gemini in the baseline below, and Claude sub-agents as blind readers in the summary
readings and the reading studies.

**Apertus against a frontier cloud model.** `docs/eval_baseline_gemini.md` reruns the same code
and prompts (summaries `v6`) with Gemini 3.8 Flash (thinking off). All prompts were tuned on
Apertus, so Gemini runs them untuned. In the table, P@30 is the share of the top 30 that Suva
listed (precision). R@60 is the share of Suva's listed rulings that are in the top 60 (recall).

| | Apertus 70B | Gemini 3.8 Flash |
|---|---|---|
| Triage P@30 / R@60, Q4 · Q1 (generated level for both) | 0.70 / 0.93 · 0.63 / 0.77 | 0.67 / 0.89 · 0.67 / 0.84 |
| Category, primary correct (55 examples) | 0.75 | 0.80 |
| Summaries v6, blind reading (20 texts) | outcome right 20/20; 36 factual errors; 2 error-free | outcome right 20/20; 2 factual errors; 18 error-free; preferred 20/20 |
| Time per summary (median) | 268 s on the shared gateway | 69 s |
| Sovereignty | open weights, on-premise or air-gapped | US cloud API only |

Ranking and categories are on par. For summaries, the cloud model is clearly ahead. v7 closes
part of the gap: stricter readers counted 43 errors for v6 and 31 for v7, and no text got
worse. We stay on Apertus because rulings, drafts and internal notes must not leave Suva's
network.

## 4. The challenge's measures and the bonus

**Recall and F2 on the delivered list.** Suva scores our list of relevant April-June 2026
rulings by recall and F2. Recall is the share of the rulings Suva wants that are on our list.
Precision is the share of our list that Suva wants. F2 combines both into one number and weighs
a missed ruling four times as much as an extra one. We chose the triage threshold of 28 for F2 on the labelled half-year:

- It is the best cut-off on Q1 2026 (F2 0.708).
- It keeps recall at 1.00 on the held-out Q4 2025 (F2 0.757).
- Both quarters together: recall 1.00, precision 0.35 (168 rulings), F2 0.73. The earlier
  threshold of 50 gave recall 0.85, precision 0.46 (109 rulings), F2 0.72.

The same threshold labels rulings relevant in the app, fills the knowledge base and cuts the
delivered list (`deliverables/`). April-June 2026 has 100 rulings at 28 or more (61
invalidity, 38 accident, 1 military insurance). 68 of them score 50 or more.

**Top 5 summaries of June 2026.** Suva compares our summaries of rulings it summarised in June
2026 with its own. The five highest-ranked rulings decided in June 2026 are 8C_254/2025 (rank
1, five-judge), 8C_17/2026, 8C_343/2025, 8C_184/2026 and 8C_365/2025. All have v7 summaries in
both languages. Every April-June ruling scored 50 or more (68) has a v7 summary. They average
about 168 words in German and 195 in French, and none is over the limit. We have no measure
that predicts Suva's verdict on these texts. The hold-out reading above is the closest one.

**Product.** One UI covers the four steps: original text (with a link to bger.ch), sortable
score, the reasoning in DE and FR, both summaries side by side, and "add another judgement" as
"+ Urteil hinzufügen" (by number) and "Zusammenfassen" (any stored ruling on demand).

**Bonus: redefine relevance, customise summaries, learn from changes.**

- **Redefine relevance:** lawyers set their own score per ruling.
- **Customise summaries:** lawyers edit a summary or accept the assistant's proposal.
- **Learn from changes:** a person always decides. The assistant's knowledge text changes only
  when a lawyer says "Merke dir". It can be read and reset on the "Agent-Wissen" page.
  "Anpassungen" collects the score corrections and turns them into proposed rules for the
  triage prompt.

Nothing feeds back into triage automatically. The labels reflect Suva's capacity as much as
relevance, one quarter holds only about 30 listed rulings, and our own tuning showed that a
rule that helps one quarter can hurt the other. A proposed change is adopted only after a person has reviewed it and the cross-quarter check
holds (`docs/feedback_loop.md`).

![Feedback loop: lawyers correct in the UI, export, feedback-review report, human decision, developer applies, evaluation, release](docs/feedback_loop.svg)

*Figure 2 ([`docs/feedback_loop.svg`](docs/feedback_loop.svg)): purple, people decide; grey,
plain code; orange, Apertus. The dashed box is a coding agent that only writes a report.*

**The feedback-review skill.** `uv run suva feedback-export` writes every correction as JSON
(no LLM). A quality supervisor then runs the `feedback-review` skill
(`.claude/skills/feedback-review/SKILL.md`) in a coding agent. The skill reads the export, the rulings and the current prompts. It traces
each correction to the prompt criterion or rule behind it. It counts how a candidate rule would
act on the labelled period and checks it against changes we already rejected. It then writes a
report: minimal suggested changes, evidence, expected effect, a validation plan, and questions
for the legal team. It changes no prompt and no output. Its first run used five synthetic score corrections and one
edited summary (`docs/examples/feedback_review_example.md`). Results:

- It traced three raised IV rulings to a criterion the prompt already has.
- It declined a general IV rule, because the labelled period does not support it (the rejected
  v4b).
- It proposed one narrow change: the IV helplessness allowance (3 of 9 listed, against 1 in 10
  for IV overall).
- It found a real UVG/UVV error in a summary, which points to the factual-check prompt.
- It passed the two lowered accident insurance rulings to the legal team as a policy question.

## 5. Data

| Data | Source | Licence / status | Personal data |
|---|---|---|---|
| 6,030 Federal Supreme Court rulings, 2025-10-01 to 2026-06-30 (`data/corpus/`) | entscheidsuche.ch open-data mirror of bger.ch | Court decisions are official acts, not protected by copyright (Art. 5 URG) | Anonymised by the Court ("A.________"); we do not de-anonymise |
| UVG, ATSG, UVV in DE and FR (`data/laws/`) | Fedlex SPARQL endpoint and HTML | Official legal texts (Art. 5 URG) | none |
| 55 example summaries in DE/FR and the list of 59 rulings Suva summarised in Q4 2025 / Q1 2026 (`judgements/`, parsed into `data/eval/`) | Suva, provided for the challenge | Challenge material | Authors identified by initials (FRT, LC4, VIL) |
| Glossary DE=FR (`data/eval/glossary.json`) and style guide | Derived by us from Suva's examples | Project licence | none |

The 55 examples are split into a few-shot pool and a hold-out of 10 that no prompt ever sees
(`data/eval/split.json`). Their rulings are in `data/eval/example_rulings.jsonl.gz`.
Summaries never name parties, doctors or other insurers, and omit birth years. Secrets, the
database and the response cache are not committed.

## 6. Limitations

- **Factual errors in summaries.** The rule checks secure the outcome, statutes, consideration
  numbers, figures and dates that occur in the ruling. The v7 factual check catches part of the
  rest. A blind reading of the 20 hold-out texts found 31 errors (v6: 43) and 3 texts without
  any (v6: 0). Still wrong in both versions: the rule of Art. 6 Abs. 2 UVG turned around in
  8C_78/2025, the adequacy criteria in 8C_356/2025, the stages of the procedure in 8C_313/2024
  and 8C_613/2025, and references to a consideration that exists but does not state the point.
  7 of the 136 April-June texts have no consideration reference. Summaries need a lawyer's
  review before use.
- **Invalidity insurance recall.** Suva lists about 8 % of IV rulings. Neither metadata,
  statutes nor Apertus separate them from the unlisted ones. Seven of the 8 listed rulings
  outside the top 60 are IV rulings. Apertus rates IV almost all-or-nothing.
- **Labels reflect capacity.** Suva summarised about the same number of accident insurance
  rulings per quarter, while the substantive ones nearly doubled. A blind reader rated 7 of the
  17 unlisted accident insurance rulings in v4's top 30 as worth a summary. So precision
  understates the ranking. One or two rulings per quarter are noise (about ±0.05).
- **Tuned on the evaluation period.** Base rates and examples in the triage prompt come from
  the labelled half-year, so its numbers are optimistic for a new quarter. April-June 2026 has
  no labels.
- **Evaluation is not lawyer-validated.** LLM sub-agents, not lawyers, did the blind readings
  and reading studies. They quote the ruling for every finding.
- **Coverage.** Only Federal Supreme Court rulings since October 2025; no cantonal decisions
  (one is on Suva's list).
- **Latency on a shared gateway.** A summary took a median of 268 s with v6. The v7 factual
  check adds about 25 short calls. Under load, some 20,000-token calls hit a 120 s client
  timeout, so the client now waits up to 600 s (`LLM_TIMEOUT`). The UI pre-computes the top
  summaries and runs the rest on demand with a progress state.
- **Not tested:** the 8B model, quantised weights, a vLLM deployment of our own, and load
  beyond one team.

## 7. Reproducibility

**Running it.** Setup, Docker and every command are in the README, section "Running it".
In short: `cp .env.example .env`, set `LLM_NAME`, `LLM_BASE_URL` and `LLM_API_KEY`, then run
`docker compose up --build` and open http://127.0.0.1:8000. Without Docker, use `make install
load run`. The committed results make the UI work without calling Apertus.

- **Hardware and runtime.** The app runs on a laptop (Python 3.12, uv). The model ran on the
  hackathon gateway. With 8-12 parallel calls, triage of a quarter took 5-40 minutes (about
  130-190 Apertus calls), classification of all nine months 14 minutes.
- **Seeds and determinism.** Temperature 0 except where section 3 says otherwise. The gateway
  is not bit-for-bit deterministic: a fresh triage run differed by one ruling in Q1. But every
  response is cached under `data/cache/llm/`, so a rerun with the same prompt version is exact.
  The committed `data/results/*.jsonl` are the reference outputs.
- **Commit.** The submission commit is `621e87d` (main, 2026-11-28). All results and numbers
  in this report are as of that commit. Later commits only add this report and its PDF.

```sh
make install load                                   # results as submitted, no LLM needed
uv run suva triage --from 2026-04-01 --to 2026-06-30
uv run suva classify --from 2026-04-01 --to 2026-06-30
uv run suva summarize-relevant --from 2026-04-01 --to 2026-06-30 --min-score 50
uv run python -m suva.eval.score_triage data/results/triage_2025q4_2026q1.jsonl --threshold 28
uv run python -m suva.eval.score_classification
uv run python -m suva.eval.score_summaries generated.jsonl   # hold-out, see docs/eval_summaries.md
```

**Results at a glance** (details in `docs/eval_*.md`). ROUGE-L and chrF measure word and
character overlap with Suva's summary.

| What | Measure | Result |
|---|---|---|
| Triage v5, Q4 2025 | P@10 / P@30 / R@30 / R@60 | 0.90 / 0.70 / 0.75 / 0.96 |
| Triage v5, Q1 2026 | P@10 / P@30 / R@30 / R@60 | 0.60 / 0.60 / 0.58 / 0.77 |
| Triage v5, both quarters | recall / precision / F2 at score ≥ 28 | 1.00 / 0.35 / 0.73 (168 rulings) |
| Triage, April-June 2026 | 2,096 rulings: pre-filter / gate / Apertus / relevant | 1,908 / 57 / 131 / 100; all top 30 accident insurance |
| Classification v4, 55 examples | primary category / branch | 0.75 / 0.98 (44 of 45) |
| Summaries v7, 10 hold-out × DE/FR | blind reading: outcome right / factual errors / error-free (v6) | 20 of 20 / 31 (43) / 3 (0) |
| | ROUGE-L / chrF / glossary recall, DE · FR | 0.19 / 43.1 / 0.63 · 0.25 / 41.1 / 0.69 |
| | style issues (foreign abbreviations, avoid-list terms, citation format) | 0 |
| Summaries v6, same hold-out | share of VIL's five structural markers, DE / FR (VIL herself: 0.80 / 0.93) | 0.68 / 0.80 |

## License

Creative Commons Attribution 4.0 (CC-BY-4.0). All HackApertus projects are open-sourced.
The code is under Apache-2.0 (`LICENSE`).

## References

1. Swiss AI Initiative, Apertus v1.5 70B: https://huggingface.co/swiss-ai/Apertus-v1.5-70B
2. Swiss Federal Supreme Court, case law: https://www.bger.ch
3. entscheidsuche.ch, open-data mirror of Swiss court decisions: https://entscheidsuche.ch
4. Fedlex, the publication platform for federal law (UVG SR 832.20, ATSG SR 830.1,
   UVV SR 832.202): https://www.fedlex.admin.ch
5. Bundesgesetz über das Urheberrecht (URG), Art. 5, SR 231.1.
6. vLLM, an OpenAI-compatible inference server: https://github.com/vllm-project/vllm
7. Project documents: `docs/eval_triage.md`, `docs/eval_classification.md`,
   `docs/eval_summaries.md`, `docs/eval_baseline_gemini.md`, `docs/style_guide.md`.
