# Technical report - `[TODO: project name]`, `[TODO: team name]`

A deeper write-up than the README: what we built, how it works, and what the
numbers say.

- **Challenge partner:** Suva
- **Challenge:** Identification of relevant Federal Court judgements and preparation of a legal summary
- **Event:** On-site Zurich
- **Team:** `[TODO: team name]` - `[TODO: member]`, `[TODO: member]`, `[TODO: member]`
- **Demo:** `[TODO: link to video]`

## 1. Summary

Suva's lawyers search the Federal Supreme Court's publications by hand, pick the rulings that
matter for accident insurance and write a short summary of each in German and in French. We
built a pipeline and a web application that do the first pass for them. It loads every ruling
of a period (about 2,000 per quarter), ranks them by relevance to Suva and explains each rating
in German and French. It sorts every social-law ruling into a two-level legal taxonomy, writes a
German and a French summary in Suva's house style for the top-ranked rulings, and stores all of
it in a searchable knowledge base. A legal assistant agent answers case questions from the
rulings and from the UVG, ATSG and UVV. Every text the product shows comes from Apertus v1.5 70B.
Everything else is deterministic code: fetching, segmentation, a keyword prior and a gate,
fact extraction and rule checks.

The ranking is tuned and evaluated on the half-year Suva labelled (59 listed rulings in Q4 2025
and Q1 2026). A change was kept only if it made neither quarter worse. All 59 listed rulings
pass the deterministic pre-filter and gate. The top 30 holds 70 % (Q4) and 60 % (Q1) listed
rulings, and the top 60 holds 96 % and 77 % of each quarter's listed rulings. The misses are
mostly invalidity insurance rulings. On 10 hold-out rulings never shown to the model, the
summaries follow the evaluator's structure, and their stated outcome is right in 20 of 20
texts. Their main weakness is factual: a blind reading found errors in most of them. The system
runs on-premise or air-gapped, as Docker Compose with SQLite and one OpenAI-compatible Apertus
endpoint.

## 2. Architecture

![Architecture: build-time inputs, the batch pipeline, serving and the Apertus endpoint](docs/architecture.svg)

*Figure 1 ([`docs/architecture.svg`](docs/architecture.svg)): grey boxes are deterministic
code, orange boxes call Apertus, blue boxes are data on disk. Network access is needed only at
build time and to refresh the data.*

| Component | Code | LLM | Role |
|---|---|---|---|
| Fetch | `src/suva/fetch/` | no | Downloads rulings from the entscheidsuche.ch mirror into `data/corpus/rulings.jsonl.gz` |
| Segmenter | `segment.py` | no | Splits a ruling into rubrum, facts, numbered considerations (admissibility, substance, costs), operative part and signature, in DE/FR/IT |
| Triage | `triage.py` | Apertus | Keyword prior, merits gate, then a relevance level 0-9 with an explanation in DE and FR |
| Classification | `classify.py` | Apertus | Statutes, precedents, outcome and flags by rule; branch and legal category by Apertus |
| Summaries | `summarize.py`, `prompts/` | Apertus | DE and FR summaries plus one-line headlines, with rule checks and revisions |
| Knowledge base | `db.py` | no | SQLite with FTS5 full-text search over rulings and summaries |
| API and UI | `api.py`, `web/` | no | FastAPI JSON API and a static DE/FR frontend served by the same process |
| Agent | `agent/` | Apertus | Legal assistant with tools over the laws and the knowledge base |
| Laws | `laws.py`, `data/laws/` | no | UVG, ATSG and UVV from Fedlex in DE and FR, committed as JSON |

**Fetch.** bger.ch blocks scripted access with an Imperva/hCaptcha bot wall. The crawler
therefore reads the open-data mirror of entscheidsuche.ch, which publishes one metadata and one
HTML file per decision. The committed corpus holds all 6,030 rulings decided from 2025-10-01 to
2026-06-30.

**Triage** (prompt `v5`, `docs/eval_triage.md`) runs in four steps:

1. A deterministic prior scores the subject line, division, Suva/CNA in the rubrum,
   UVG/UVV/ATSG citations and accident or military insurance mentions. Rulings below 20 points
   are labelled not relevant without an LLM call, with a DE/FR explanation listing the hints
   found. A ranking-only adjustment rewards substance (length, five-judge panel, an invalidity
   insurance appeal by the IV office, the BSV or a pension fund, an upheld appeal). It penalises
   the simplified procedure and inadmissibility.
2. A deterministic gate drops decisions that do not rule on the merits: not entertained or
   struck off, single-judge, or without a substantive consideration.
3. Apertus 70B reads the criteria, the base rates of the labelled period, the topics of Suva's
   few-shot examples, the matching DE=FR glossary terms, the prior's hints and up to 30,000
   characters of the ruling. It returns JSON with a level from 0 to 9 and a two-sentence
   explanation in each language, each written in its own legal language.
4. The level is read from the token logprobs as an expected value (7.4, not 7). The first
   version asked for a 0-100 score, and Apertus gave 85 to almost every accident insurance
   ruling. Final score = 70 % level + 30 % prior; 50 or more is labelled relevant. Explanations
   are checked for language, the other language's statute abbreviations are replaced from the
   glossary, and a wrong text gets one rewrite request.

**Classification** (prompt `v4`, `docs/eval_classification.md`). Statutes cited, precedents
(BGE/ATF/DTF), the outcome and flags (five-judge panel, public deliberation, cited as intended
for publication) are extracted by rule from every ruling. Every ruling of the two social-law
divisions (dockets 8x/9x, 1,150 rulings) goes to Apertus, which picks a branch (UVG, IVG, MVG,
ATSG/other social insurance, outside social insurance) and a primary plus up to two secondary
legal categories from a closed list of 17. The reply is constrained by a JSON schema with enums,
and a primary category that the branch does not allow is sent back with the error. All other
rulings are outside social insurance by their division.

**Summaries** (prompt `v6`, `docs/eval_summaries.md`, style in `docs/style_guide.md` section 11)
take 10 to 16 Apertus calls per ruling:

1. Source: the ruling without costs, legal aid and the notification list (up to 70,000
   characters).
2. Holdings: Apertus lists the Court's conclusion for each numbered consideration. This step
   was added after the model merged two considerations and inverted a holding.
3. Two originals: the summary in the ruling's language is written from the ruling. The other
   language is also written from the ruling, with the first summary as an outline, because
   Suva's own second-language texts are translations with artefacts. The style follows the
   expected evaluator VIL (facts, cantonal court, principles recalled, their application,
   outcome; a consideration reference closes each statement) at 150-200 words in German and
   160-220 in French. Two of her summaries serve as few-shot anchors.
4. Rule checks: length, consideration references and statutes that exist in the ruling, figures
   and dates that occur in it, no names, initials or birth years, Suva named only as a party,
   no sentence that decides the appeal against the operative part, and the target language's
   abbreviations and glossary terms. Apertus also checks each claim against the ruling. Failed
   checks go back to Apertus for revision, and an overlong text is shortened by Apertus or, as
   a last resort, cut by whole sentences that Apertus ranks as least needed.
5. Consistency: Apertus compares the German and French texts, names the version the ruling
   supports, and the other one is revised.
6. Finishing: deterministic normalisation (section 3).

Each run also writes a headline per language of at most about 12 words.

**Knowledge base, UI and agent.** Results live in SQLite with an FTS5 index. The UI (DE/FR)
lists every ruling of a period with a sortable score, the explanation, badges and filters for
the taxonomy. It shows the original text, both summaries and headlines, and has a button to
summarise any further ruling on demand. The agent uses six tools: `read_article`,
`list_rulings`, `search_rulings`, `read_ruling`, `propose_summary` and `update_memory`. It
answers in the user's language with clickable citations of articles and dockets, at most 10
tool calls per question. A summary the agent proposes replaces the stored one only when the
lawyer accepts it, and is then marked `edited`, like a lawyer's own edit.

### Target architecture (mandatory)

The project is deployable in all three settings. It is built for **a) on-premise** and
**b) air-gapped** operation, and the same container runs unchanged on **c) a sovereign Swiss
cloud** with a Swiss-hosted Apertus endpoint.

- **One container plus one model endpoint.** `docker compose up --build` starts the API and UI
  on port 8000. The first start builds `data/suva.db` from the committed corpus and results
  (about 30 seconds). The only network peer at runtime is `LLM_BASE_URL`, an OpenAI-compatible
  endpoint serving Apertus. On-premise this is the organisation's own server, e.g. vLLM on its
  own GPUs. The 70B model in BF16 needs about 140 GB of GPU memory, e.g. two 80 GB GPUs. We did
  not evaluate quantised or 8B variants.
- **No third-party calls at runtime.** No CDN, web fonts or analytics: the UI is static files
  served by FastAPI. The law texts are committed snapshots, so Fedlex is not needed. The links
  "open on bger.ch" are plain hyperlinks. Without internet they do not resolve, but the full
  text is in the database.
- **Endpoint features used:** chat completions, `logprobs`/`top_logprobs` (triage),
  `response_format: json_schema` (classification), and tool calls (agent). The agent also
  recognises tool calls the server leaves in the text.

| | Build time / data refresh (network) | Runtime |
|---|---|---|
| Code | Docker base images (Docker Hub, ghcr.io), PyPI packages pinned in `uv.lock` | none |
| Model | Apertus weights from Hugging Face, once | local endpoint only |
| Rulings | `python -m suva.fetch` from entscheidsuche.ch; air-gapped: run it on a connected machine and transfer the corpus file | none |
| Laws | `python -m suva.laws` from Fedlex SPARQL | none |

**Transfer to Azure (bonus).** The image runs on Azure Container Apps or App Service with
`./data` on an Azure Files volume. The three `LLM_*` variables point to an Apertus deployment,
e.g. vLLM on a GPU node in Switzerland North. No code changes are needed. Azure is a US-owned
provider, so for jurisdiction (option c) a Swiss provider hosting Apertus is the closer fit.

## 3. Use of Apertus

- **Model:** `swiss-ai/Apertus-v1.5-70B`, the regular instruct model (gateway id
  `apertus-v1-5-70b`, the default when `LLM_NAME` is empty). The app warns if `LLM_NAME` names a
  thinking variant.
- **How it is used:** inference (triage, classification, summaries, headlines) and agents / tool
  use (the legal assistant). No fine-tuning, no adapters, no quantisation on our side.
- **Where it runs:** for the hackathon, the CSCS / Keera gateway (`https://gateway.keera.ch`);
  in production, any OpenAI-compatible server the organisation runs, set by `LLM_NAME`,
  `LLM_BASE_URL` and `LLM_API_KEY`.

| Step | Prompt | Calls | Parameters |
|---|---|---|---|
| Triage | `triage.py` (`v5`) | 1 per ruling that passes the gate | temperature 0, `logprobs`, top 10, 900 tokens |
| Classification | `classify.py` (`v4`) | 1 per 8x/9x ruling, up to 3 on an invalid reply | temperature 0, JSON schema with enums |
| Summaries | `prompts/summary_*.md` (`v6`) | 10-16 per ruling | temperature 0; 0.4 only to redraw a rejected shortening |
| Headlines | `prompts/headline.md` (`v3`) | 3-6 per ruling | temperature 0 |
| Agent | `agent/prompt.md` | up to 10 tool steps per question | temperature 0.2, native tool calls |

All calls go through `src/suva/llm.py`, a thin OpenAI client with retries and an on-disk
response cache keyed by model, messages and parameters.

**Model choice.** The gateway offered the 70B and 8B models, each also as a thinking variant.
On the long legal prompts the thinking variant produced no reasoning at all; it reasoned only
when the assistant turn was prefilled. Its summaries were neither better nor worse than the
regular model's: better on 3 rulings, worse on 4, and differing from 70B about as much as two
70B runs differ from each other. It also brought errors a specialist notices first, such as
calling the IV office "l'assureur-accidents". So all steps use the regular 70B.

**What we tried and dropped.** Several reading studies of the labelled period, with blind
readers and the labels joined afterwards, informed v5. Their proposals were tested with the
cross-quarter rule:

- *Map-reduce triage* (one call per consideration, then a combining call): within wording noise
  for 6.4 times the calls. The study also showed the premise was wrong: rulings that reach the
  model have a median of about 3,900 tokens, and only 3.6 % exceed the excerpt. The segmenter
  and the gate it proposed were adopted; the gate saves 27 % of the calls without moving a
  metric.
- *Cited statutes as a score component:* they restate the branch and the outcome that the prior
  already holds, and a citation boost would reinforce the existing false positives. The better
  extractor was kept for the badges (statute recall 77 % to 100 % on a 20-ruling check).
- *An explicit invalidity insurance rule in the prompt (v4b, v4c):* it raised all IV rulings,
  listed or not, and pushed listed accident insurance rulings down in one quarter. Apertus
  agreed with blind readers on novelty in only 24-30 % of rulings.
- *Level 8 for legal questions, 7 for medical evidence:* it fits how Suva chose when its
  capacity was short (Q1) but not when it had room (Q4).
- *Summaries:* a third few-shot example chosen by similarity (the model copied its facts); an
  LLM judge (with Apertus as judge it rated a correct summary as reversing the outcome); asking
  which sentences to delete (the model deleted half the text); a rewrite prompt naming the
  number of words to remove (worse top summaries).

**Hackathon rule compliance: only Apertus generates text.** Every explanation, category,
summary, headline and agent answer the product shows comes from Apertus. No summary in
`data/results/` was written or corrected by hand or by another LLM. The UI can store a
lawyer's edit, but it is marked `edited`, and none is in the submitted results. The
post-processing after Apertus is rule-based:

- replace the other language's statute abbreviations from the glossary;
- normalise citation format, Swiss amounts, "Suva" for "CNA" and restored French superscripts;
- take the spelling of a word copied with a typo from the ruling;
- replace a closing sentence with the wrong result or party by a standard formula built from
  the rubrum and the operative part;
- add "Fünfer-Entscheid." / "Décision à cinq." for five-judge rulings;
- as a last resort, delete whole sentences that Apertus ranked as least needed.

The German few-shot anchors (`src/suva/prompts/style_examples_de.json`) are German renderings
of VIL's French originals. They are prompt input, never output. Other models appear only in
evaluation: Gemini in the baseline below, and Claude sub-agents as blind readers in the
summary reading and the reading studies.

**Apertus against a frontier cloud model.** `docs/eval_baseline_gemini.md` reruns the same
code and prompts with Gemini 3.8 Flash (thinking off). Gemini's numbers come from an untuned
transfer: every prompt was tuned on Apertus.
<!-- TODO(final): update the summary rows after tonight's summary iteration. -->

| | Apertus 70B (shipped) | Gemini 3.8 Flash |
|---|---|---|
| Triage P@30 / R@60, Q4 · Q1 (generated level for both) | 0.70 / 0.93 · 0.63 / 0.77 | 0.67 / 0.89 · 0.67 / 0.84 |
| Category, primary correct (55 examples) | 0.75 | 0.80 |
| Summaries, blind reading (20 texts) | outcome right 20/20; 36 factual errors; 2 error-free | outcome right 20/20; 2 factual errors; 18 error-free; preferred 20/20 |
| Time per summary (median) | 268 s on the shared gateway | 69 s |
| Sovereignty | open weights, on-premise or air-gapped | US cloud API only |

Ranking and categories are on par. Summaries are where the cloud model is clearly ahead, on
accuracy as well as style. We stay on Apertus because rulings, drafts and internal notes must
not leave Suva's network.

## 4. Data

| Data | Source | Licence / status | Personal data |
|---|---|---|---|
| 6,030 Federal Supreme Court rulings, 2025-10-01 to 2026-06-30 (`data/corpus/`) | entscheidsuche.ch open-data mirror of bger.ch | Court decisions are official acts, not protected by copyright (Art. 5 URG) | Anonymised by the Court ("A.________"); we do not de-anonymise |
| UVG, ATSG, UVV in DE and FR (`data/laws/`) | Fedlex SPARQL endpoint and HTML | Official legal texts (Art. 5 URG) | none |
| 55 example summaries in DE/FR and the list of 59 rulings Suva summarised in Q4 2025 / Q1 2026 (`judgements/`, parsed into `data/eval/`) | Suva, provided for the challenge | Challenge material | Authors identified by initials (FRT, LC4, VIL) |
| Glossary DE=FR (`data/eval/glossary.json`) and style guide | Derived by us from Suva's examples | Project licence | none |

The 55 examples are split into a few-shot pool and a hold-out of 10 (`data/eval/split.json`)
that no prompt ever sees. The full text of all 55 example rulings is in
`data/eval/example_rulings.jsonl.gz`; 23 of them predate the corpus. No data comes from human
subjects. Summaries never name parties, doctors or other insurers, and they omit birth years.
Secrets (`.env`), the database and the response cache are not committed.

## 5. Limitations

- **Factual errors in summaries.** The rule checks secure the outcome, statutes, consideration
  numbers, figures and dates that occur in the ruling. They cannot tell whether a correct-looking
  sentence states the Court's rule correctly. A blind reading of a fresh run found 36 errors in
  20 texts (13 of them wrong consideration references). In two rulings a rule was inverted:
  Art. 6 Abs. 2 UVG in 8C_78/2025, and integrity compensation in 8C_508/2025. Apertus' own
  claim-by-claim check rarely finds such errors. Summaries need a lawyer's review before use.
  <!-- TODO(final): update the error counts after tonight's summary iteration. -->
- **Invalidity insurance recall.** Suva lists about 8 % of IV rulings, and neither metadata,
  statutes nor Apertus separate them from the unlisted ones. Seven of the 8 listed rulings
  outside the top 60 are IV rulings. Apertus rates IV almost all-or-nothing.
- **Labels reflect capacity.** Suva summarised about the same number of accident insurance
  rulings per quarter while the substantive ones nearly doubled. In February 2026 it listed 2 of
  10. A blind reader rated 7 of the 17 unlisted accident insurance rulings in v4's top 30 as
  worth a summary. Precision therefore understates the ranking, and differences of one or two
  rulings per quarter are noise (about ±0.05).
- **Tuned on the evaluation period.** Base rates and examples in the triage prompt come from
  the labelled half-year, so its numbers are optimistic for a new quarter. April-June 2026 has
  no labels.
- **Evaluation is not lawyer-validated.** The blind summary readings and the reading studies
  were done by LLM sub-agents that quote the ruling for every finding, not by Suva's lawyers.
- **Coverage.** Only Federal Supreme Court rulings. Cantonal decisions (one is on Suva's list)
  and rulings before October 2025 are outside the corpus. The "intended for publication" flag
  only works once another ruling cites the docket.
- **Latency on a shared gateway.** A summary takes 1-5 minutes (median 268 s in the baseline
  run). Under load some 20,000-token calls exceeded the 120 s client timeout, so the batch run
  needed `LLM_TIMEOUT=600`. The UI therefore pre-computes the top summaries and runs the rest
  on demand with a progress state.
- **Not tested:** the 8B model or quantised weights for the full pipeline, a vLLM deployment of
  our own (all runs used the hackathon gateway), and load beyond one team.

## 6. Reproducibility

**Running it.** Setup, Docker and every command are in the README, section "Running it".
In short: `cp .env.example .env`, set `LLM_NAME`, `LLM_BASE_URL` and `LLM_API_KEY`, then run
`docker compose up --build` and open http://127.0.0.1:8000. Without Docker, use `make install
load run`. The committed results make the UI work without calling Apertus.

- **Hardware.** The app runs on a laptop (Python 3.12, uv). The model ran on the hackathon
  gateway, whose GPUs we did not control.
- **Runtime** on the shared gateway with 8-12 parallel calls: triage of a quarter 5-40 minutes
  (about 130-190 Apertus calls). Classification of all nine months took 14 minutes. A summary
  takes 1-5 minutes.
- **Seeds and determinism.** Temperature 0 everywhere, except 0.4 when a rejected shortening or
  headline correction is drawn again, and 0.2 in the interactive agent. The gateway is not
  bit-for-bit deterministic: a fresh triage run reproduced Q4 exactly and differed by one ruling
  in Q1. Every response is cached under `data/cache/llm/`, so a rerun with the same model and
  prompt version is exact. The committed `data/results/*.jsonl` are the reference outputs.
- **Commit.** Results and numbers as of `5376115` (main, 2026-11-27).
  <!-- TODO(final): replace with the exact submission commit. -->

```sh
make install load                                   # results as submitted, no LLM needed
uv run suva triage --from 2026-04-01 --to 2026-06-30
uv run suva classify --from 2026-04-01 --to 2026-06-30
uv run suva summarize-relevant --from 2026-04-01 --to 2026-06-30 --limit 30
uv run python -m suva.eval.score_triage data/results/triage_2025q4_2026q1.jsonl --threshold 50
uv run python -m suva.eval.score_classification
uv run python -m suva.eval.score_summaries generated.jsonl   # hold-out, see docs/eval_summaries.md
```

**Results at a glance** (details and per-ruling tables in `docs/eval_*.md`):
<!-- TODO(final): update the summary rows after tonight's summary iteration. -->

| What | Measure | Result |
|---|---|---|
| Triage v5, Q4 2025 | P@10 / P@30 / R@30 / R@60 | 0.90 / 0.70 / 0.75 / 0.96 |
| Triage v5, Q1 2026 | P@10 / P@30 / R@30 / R@60 | 0.60 / 0.60 / 0.58 / 0.77 |
| Triage v5, both quarters | recall / precision at score ≥ 50 | 0.85 / 0.46 (109 rulings) |
| Triage, April-June 2026 | 2,096 rulings: pre-filter / gate / Apertus / relevant | 1,908 / 57 / 131 / 68; all top 30 accident insurance |
| Classification v4, 55 examples | primary category / branch | 0.75 / 0.98 (44 of 45) |
| Summaries v6, 10 hold-out × DE/FR | words DE / FR (target 150-200 / 160-220) | 190 / 212 |
| | ROUGE-L / chrF / glossary recall, DE · FR | 0.20 / 44.8 / 0.62 · 0.24 / 43.0 / 0.71 |
| | share of VIL's five structural markers, DE / FR (VIL herself: 0.80 / 0.93) | 0.68 / 0.80 |
| | outcome stated correctly / style issues | 20 of 20 / 0 |

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
