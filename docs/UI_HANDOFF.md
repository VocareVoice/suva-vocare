# UI handoff - context for the UI/UX design work

Everything known so far about the UI and the surrounding product, so UI design can start in parallel with the backend.
Submission deadline: **2026-11-28, 14:30**.

## 1. The product in one paragraph

Suva's lawyers today search the Federal Supreme Court (bger.ch) publications by hand, read each ruling and write a short summary in German and French.
Our prototype fetches all rulings of a period, scores each one for relevance to Suva / Swiss accident insurance with a written explanation, writes a German and a French summary (not a translation of each other) in Suva's house style for the relevant ones, and stores everything in a searchable knowledge base.
The UI is where the lawyers review all of this.

## 2. Users

- Suva legal specialists (accident insurance law), working in German or French.
- Expert readers: they care about legal precision, the original text, and why something was flagged. They will distrust anything they cannot verify against the source.
- The judges of the hackathon are Suva's legal specialists too, and they will only look at a few screens (see section 6).

## 3. Required UI capabilities (from Suva's presentation)

1. **See and browse the court rulings** - all rulings of a period, not only the relevant ones.
2. **Relevance score** per ruling, sortable.
3. **Reasoning** - why a ruling is relevant (or why not). This is the triage explanation.
4. **German and French summary** for relevant rulings.
5. **Summarise on demand** - a lawyer finds a ruling the first pass did not mark as relevant and can trigger an automatic summary of it.
6. **Feedback on the relevance score** - the lawyer can say the score is wrong (relevant / not relevant, optionally a corrected score and a comment). We plan to feed this back into later scoring, which is a good pitch point.

Nice to have (bonus "improve the customer experience"):

- Full-text search across rulings and summaries (the backend has full-text search).
- Filters: period, court division (e.g. 8C = accident and disability insurance), language, score range, has-summary.
- Side-by-side: original ruling next to the summary, ideally with the key passages the summary is based on.
- Copy / export a summary in Suva's format.
- Showing which statutes are cited (UVG/LAA, UVV/OLAA, ATSG/LPGA, IVG).
- Status of a summary: AI-generated, reviewed, edited by a lawyer.

## 4. Screens we expect

1. **Ruling list (main screen)** - table with docket (e.g. `8C_129/2025`), decision date, division, language, subject/title, relevance score (sortable, visually prominent), short one-line reason, summary available yes/no. Search box and filters on top. Default sort: score descending.
2. **Ruling detail** - header (docket, date, division, language, subject, link to the original on bger.ch), relevance score and full reasoning, feedback control, German summary, French summary (tabs or side by side), original full text (long, needs good reading typography and scroll), "Summarise" button when no summary exists yet (generation takes a while: needs a loading / progress state).
3. **Feedback interaction** - lightweight: agree / disagree, optional corrected score, optional comment.

## 5. What a summary looks like

The human examples are in `judgements/*.html` (57 rulings). Each has a German ("Text DE") and a French ("Text FR") paragraph, typically one dense paragraph of the key holdings, citing articles (e.g. "Art. 73 lit. b UVV" / "art. 73 let. b OLAA").
Example (8C_129/2025, shortened):

> **DE:** Die Reinigung von Wohnungen und Büros fällt unter Art. 73 lit. b OLAA, und dieser Artikel steht im Einklang mit dem Gesetz. Es gibt keine Unterscheidung zwischen Reinigungsunternehmen, die innerhalb oder ausserhalb von Gebäuden tätig sind ...
>
> **FR:** Le nettoyage des appartements et des bureaux tombe sous l'art. 73 let. b OLAA et cet article est conforme à la loi. On ne distingue pas les entreprises de nettoyage selon qu'elles intervenaient à l'extérieur ou à l'intérieur de bâtiments ...

A style guide derived from all examples will land at `docs/style_guide.md` (in progress). Design for paragraphs of roughly 100-300 words per language.

## 6. How we are judged (drives UI priorities)

- Suva's experts will look at **2-3 summaries of our highest-ranked rulings** (many teams, little time). The detail view of a top-ranked ruling is the most important screen: it must look credible, clean and expert.
- They check whether our **top-ranked rulings are really relevant**, so score + reasoning must be easy to scan in the list.
- Deliverables also include a **2-minute demo video** and a **10-slide pitch deck**, both built around the UI. Design with the demo story in mind: list -> top ruling -> reasoning -> DE/FR summary -> summarise a missed ruling -> give feedback.

## 7. Data available to the UI

Per ruling: docket, decision date, publication date, division, language (de/fr/it), title/subject, url to bger.ch, full text, source.
Triage: score 0-100, label relevant / not relevant, reasoning text, model, prompt version.
Summaries: one per language (de, fr), text, model, prompt version, created at.
Feedback: verdict, corrected score, comment, created at.

Volume: a 3-month period is a few hundred rulings; most are not relevant, roughly 30 per quarter are.
Periods: Q4 2025 - Q1 2026 (practice period, has Suva's real labels) and April - June 2026 (the period the judges score).

## 8. Technical frame

- Backend: Python, FastAPI, SQLite with full-text search. JSON API (being built now; endpoint names below are the plan, check `src/suva/api.py` once merged):
  - list rulings (filters: period, score, text search; sort by score)
  - ruling detail (text + triage + both summaries)
  - POST summarise a ruling on demand
  - POST feedback on a ruling
- Frontend: served by FastAPI as static files from `src/suva/web/`. A first working (plain) UI will be built by an automated worker against the API; the design work is meant to restyle and reshape it. Plain HTML/CSS/JS or a small framework is fine, but see constraints.
- **Constraints:**
  - Must run on-premise / air-gapped / Swiss cloud: **no external CDNs, web fonts or analytics at runtime**. Vendor any library or font into the repo.
  - Judges must run it end to end from the repo (`docker compose up`).
  - Bilingual audience: UI labels in German (French optional / toggle).
  - Keep the template layout (README.md, technical_report.md, challenge_description.md, LICENSE, `src/`) untouched.

## 9. Working together

- The repo: https://github.com/VocareVoice/suva-vocare. Work on a branch and open pull requests; do not push to `main` directly.
- Parallel backend work right now: project skeleton (API, DB), fetching rulings from bger.ch, style guide + evaluation. Next: relevance triage, summary writer, first working UI.
- To avoid collisions: design work can start with mockups / a style sheet (colors, typography, components) now; once the first working UI lands in `src/suva/web/`, take that over and iterate in PRs.
- Feature freeze planned around 11:00 on submission day; after that only polish, report, deck and video.
