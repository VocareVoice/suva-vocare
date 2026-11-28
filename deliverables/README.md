# Relevance list for Q2 2026

Suva scores the delivered list of Q2 2026 rulings by recall and F2, so the cut-off is chosen
for F2. The app uses the same threshold (`triage.RELEVANCE_THRESHOLD`): the list holds exactly
the rulings it labels relevant.

| File | What it holds |
|---|---|
| `relevant_q2_2026.txt` | **The list to submit**: the 100 rulings decided 1 April - 30 June 2026 with a triage score of 28 or more, highest score first, on one comma-separated line (`8C_254/2025, 8C_256/2025, ...`) |
| `relevant_q2_2026.csv` | The same rulings with `docket, decision_date, publication_date, score, headline_de` |
| `summaries_june_2026/` | The summaries to submit: one file per ruling and language (`8C_254_2025_de.md`, `8C_254_2025_fr.md`) for the 27 listed rulings decided in June 2026, 54 files, and `index.md` listing them by score |
| `Vocare_Praecedens_vf.pptx` / `.pdf` | The final pitch deck, editable and as PDF |
| `Praecedens_demo.mp4` | Demo video of the app, 1:53, without voice or captions, for live narration; not in the submission zip |
| `Praecedens_demo_voiceover.mp4` | The same demo video narrated by a Gemini text-to-speech voice, with captions (the product itself uses only Apertus); not in the submission zip |
| `Vocare_Report.pdf` | The report, an exact copy of the root `Vocare_Report.pdf` (the template requires that one); `make report-pdf` copies it here |
| `Vocare_Submission.zip` | Built by `make submission`: `Vocare_Report.pdf` and `Vocare_Praecedens_vf.pdf` from this folder (runs `make report-pdf` first, fails if either PDF is missing) |

## Summaries and submission zip

The judged summaries are those of rulings decided in June 2026. Each file has a header (docket,
decision date, bger.ch link, relevance score, headline in that language, model and prompt
version) and then the Apertus summary exactly as stored; nothing is generated or edited by the
export.

```sh
make load
make summary-files   # uv run suva export-summary-files --from 2026-06-01 --to 2026-06-30 --out deliverables/summaries_june_2026
make report-pdf      # cp Vocare_Report.pdf deliverables/ (rerun after re-exporting the root report)
make submission      # make report-pdf, then deliverables/Vocare_Submission.zip with deliverables/Vocare_Report.pdf and Vocare_Praecedens_vf.pdf
```

`headline_de` is filled for the rulings that have a headline (those with a score of 50 or
more, from before the threshold was lowered to 28). `publication_date` is empty for rulings the
mirror added after 3 July (see below).

## How the list is made

The scores are those of the v5 triage (`docs/eval_triage.md`): Apertus 70B rates every ruling
that passes the keyword prior and the merits gate, and the score blends that rating with the
prior. Nothing in the triage was changed. The list keeps every ruling at or above a cut-off,
ordered by score, ties in docket order.

```sh
make load
uv run suva export-relevant deliverables/relevant_q2_2026 --from 2026-04-01 --to 2026-06-30
uv run python -m suva.eval.cutoff data/results/triage_2025q4_2026q1.jsonl   # table below
```

## Cut-off: score 28 or more

Per quarter of the labelled period (quarters by decision date; Q4 2025: 28 listed rulings among
1,930, Q1 2026: 31 among 2,004), n = list length, R = recall, P = precision:

| score >= | Q4 2025 n | R | P | F2 | Q1 2026 n | R | P | F2 |
|---|---|---|---|---|---|---|---|---|
| 20 | 86 | 1.00 | 0.33 | 0.707 | 106 | 1.00 | 0.29 | 0.674 |
| 25 | 78 | 1.00 | 0.36 | 0.737 | 102 | 1.00 | 0.30 | 0.686 |
| **28** (label) | **73** | **1.00** | **0.38** | **0.757** | **95** | **1.00** | **0.33** | **0.708** |
| 30 | 69 | 1.00 | 0.41 | 0.773 | 90 | 0.94 | 0.32 | 0.678 |
| 35 | 56 | 0.96 | 0.48 | 0.804 | 78 | 0.87 | 0.35 | 0.668 |
| 40 | 44 | 0.86 | 0.55 | 0.769 | 67 | 0.84 | 0.39 | 0.681 |
| 50 | 42 | 0.86 | 0.57 | 0.779 | 67 | 0.84 | 0.39 | 0.681 |
| 72 | 27 | 0.75 | 0.78 | 0.755 | 42 | 0.71 | 0.52 | 0.663 |

Tuned on one quarter, checked on the other:

| Rule | Tuned on | Value | F2 there | Checked on | n | R | P | F2 |
|---|---|---|---|---|---|---|---|---|
| score >= | Q4 2025 | 35 | 0.804 | Q1 2026 | 78 | 0.87 | 0.35 | 0.668 |
| score >= | Q1 2026 | **28** | 0.708 | Q4 2025 | 73 | 1.00 | 0.38 | **0.757** |
| top K | Q4 2025 | 53 | 0.818 | Q1 2026 | 53 | 0.77 | 0.45 | 0.678 |
| top K | Q1 2026 | 95 | 0.708 | Q4 2025 | 95 | 1.00 | 0.29 | 0.676 |

- **28** is the best cut-off on Q1 and keeps recall 1.00 on the held-out Q4 (F2 0.757). The Q4
  optimum, 35, drops three listed Q1 rulings (scores 28, 28 and 31) and gets F2 0.668 there.
  28 is the better rule in the held-out direction and in the worse quarter.
- A fixed list length transfers worse (0.676-0.678): the quarters have 73 and 95 rulings at 28
  or more, so the right length depends on the quarter, while the score scale does not.
- Against the earlier label threshold of 50, 28 keeps about the same F2 (0.757 / 0.708 against
  0.779 / 0.681) and raises recall from 0.86 / 0.84 to 1.00 / 1.00. The deck says that missing
  a relevant ruling is worse than flagging an extra one.
- The F2 curve is flat between 25 and 40 (0.67-0.80), so the choice costs little if Q2 differs.

**Expected for Q2 2026**, if Suva lists about 30 rulings as in the labelled quarters: F2 about
0.70-0.76, recall close to 1.00, precision about 0.30-0.38. Recall 1.00 is optimistic: the
cut-off sits at the lowest-scored listed Q1 rulings (two at exactly 28), and each listed ruling
scored below 28 costs about 0.03 recall. The Q2 list has 100 rulings at 28 or more (68 of them
at 50 or more), against 73 and 95 in the labelled quarters.

## Decision date or publication date

The deck asks for "rulings published in the second quarter of 2026"; the corpus and the app
select rulings by decision date. The challenge admins confirmed that the decision date counts,
and Suva's own labels agree.

**Publication dates.** bger.ch lists the rulings it publishes each day ("Liste der am ...
neu aufgenommenen Entscheide", marked * if intended for BGE), but serves the lists only behind
an hCaptcha on www.bger.ch, and relevancy.bger.ch disallows all crawling in its robots.txt.
The entscheidsuche.ch mirror reads each day's list in its crawl of the next evening and logs
every crawl job. `python -m suva.fetch.published --until 2026-07-03` reads that log and sets
`publication_date` (first crawl that added the ruling, minus one day) in
`data/corpus/rulings.jsonl.gz`. Checks:

- bger.ch's list of 15 April 2026 (fetched once): all 49 rulings get 15 April.
- Suva's "Erstellt" date is on or after the publication date for 58 of 59 listed rulings. The
  exception, 9C_699/2024 (created 17 November, our date 19 November), shows that the date can
  be a day or two late when the mirror skipped a day. The quarter boundaries are not affected:
  the mirror crawled on 31 March, 1 and 2 April, 29 and 30 June and 1 July.
- 5,506 of the 6,031 corpus records have a date. The other 525 (523 decided April-June 2026)
  were added after 3 July, so they were published in July or later; their date stays empty,
  because each later day costs a 50 MB crawl snapshot.

**Suva's quarters follow the decision date.**

- All 59 listed Federal Court rulings are in the quarter of their decision date; only 41 are in
  the quarter of their publication. The other 18 were published in the next quarter and listed
  under the quarter of the decision: 9 decided in November and December 2025 and published in
  January 2026 are listed under Q4 2025 (e.g. 8C_366/2024, decided 23 December, published 21
  January), and 9 decided in March 2026 and published in April are listed under Q1 2026 (e.g.
  8C_525/2025, decided 17 March, published 15 April on bger.ch's list).
- Suva's workbook (`judgements/BG_Urteile_2025_Q4_2026_Q1.xlsx`) has one column "Jahr /
  Quartal" and no publication date.
- The same cut-off with quarters by publication date scores against Suva's labels F2 0.579
  (recall 0.68) in Q4 2025 and 0.512 (recall 0.71) in Q1 2026, against 0.757 and 0.708 by
  decision date.

The app keeps selecting periods by decision date; the publication date is stored in the corpus
and shown on a ruling's detail page.
