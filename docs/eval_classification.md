# Classification evaluation

How well `src/suva/classify.py` (prompt version `v3`) assigns the insurance branch and the legal
category, measured against the topic and branch labels of Suva's 55 example summaries
(`data/eval/split.json`). The classification is separate from the relevance score: it sorts and
filters rulings, it does not rank them.

## Taxonomy

A closed list, so labels stay consistent and filterable. Slugs are stable; the UI shows the German
or French label.

| branch | DE | FR |
|---|---|---|
| `uv` | Unfallversicherung (UVG) | Assurance-accidents (LAA) |
| `iv` | Invalidenversicherung (IVG) | Assurance-invalidité (LAI) |
| `mv` | Militärversicherung (MVG) | Assurance militaire (LAM) |
| `atsg` | Allgemeines Sozialversicherungsrecht (ATSG) | Droit général des assurances sociales (LPGA) |
| `other` | Ausserhalb der Sozialversicherung | Hors assurances sociales |

`atsg` also takes the other social insurances (AHV, BVG, KVG, ALV, EL), since their rulings matter
to Suva only through the general part. `mv` is separate because Suva runs military insurance.

Branch-category matrix: which categories a branch allows. A ruling gets one primary and up to two
secondary categories; the LLM is retried when its primary category does not fit its branch.

| category (DE / FR) | `uv` | `iv` | `mv` | `atsg` | `other` |
|---|---|---|---|---|---|
| `invaliditaetsgrad`: Invaliditätsgrad & Einkommensvergleich / Taux d'invalidité, comparaison des revenus | x | x | x | x | x |
| `verfahren`: Verfahren (rechtliches Gehör, Fristen, Kosten) / Procédure | x | x | x | x | x |
| `natuerliche-kausalitaet`: Natürliche Kausalität / Causalité naturelle | x |  | x |  |  |
| `adaequate-kausalitaet`: Adäquate Kausalität (inkl. psychische Folgen, Schleudertrauma) / Causalité adéquate | x |  | x |  |  |
| `rentenrevision`: Rentenrevision / Révision de la rente | x | x | x | x |  |
| `unfallbegriff`: Unfallbegriff & Listenverletzung (Art. 4, Art. 6 Abs. 2 UVG) / Notion d'accident, lésions assimilées | x |  | x |  |  |
| `hilflosigkeit-pflege`: Hilflosenentschädigung & Pflege / Allocation pour impotent, soins | x | x | x | x |  |
| `taggeld-leistungskuerzung`: Taggeld & Leistungskürzung (Wagnis, Grobfahrlässigkeit) / Indemnités journalières, réductions | x | x | x | x | x |
| `beweis-gutachten`: Beweis & medizinische Gutachten / Preuve, expertises médicales | x | x | x | x | x |
| `unterstellung-praemien`: Unterstellung & Prämien (Art. 66 UVG, Art. 73 UVV) / Assujettissement, primes | x |  |  | x |  |
| `integritaetsentschaedigung`: Integritätsentschädigung / Indemnité pour atteinte à l'intégrité | x |  | x |  |  |
| `berufskrankheit`: Berufskrankheit / Maladie professionnelle | x |  | x |  |  |
| `rueckforderung-erlass`: Rückforderung & Erlass / Restitution, remise | x | x | x | x |  |
| `regress-haftung`: Regress & Haftung / Recours, responsabilité | x | x | x | x | x |
| `heilbehandlung`: Heilbehandlung & Kostenübernahme / Traitement médical | x | x | x | x |  |
| `koordination`: Koordination mit anderen Sozialversicherungen / Coordination avec d'autres assurances | x | x | x | x |  |
| `andere`: Andere / Autres | x | x | x | x | x |

Causality, the notion of accident, integrity compensation and occupational disease exist only in
accident and military insurance. Procedure, evidence and recourse/liability fit every branch.
Outside social insurance (private daily-allowance insurance under the VVG, liability law) the
degree of incapacity and daily allowances also come up, e.g. 4A_106/2025.

## Method

1. **Deterministic facts, every ruling.** Statutes cited (`Art. 6 Abs. 2 UVG`, `art. 6 al. 2 LAA`
   and `art. 6 cpv. 2 LAINF` all count as UVG 6), the outcome from the first item of the
   operative part (upheld, partly upheld, remanded, dismissed, not entertained, struck off; a
   remand that only concerns costs does not count), and flags: five-judge panel (counted from the
   "Besetzung" block), public deliberation (Art. 58 BGG), and intended for publication. The
   mirror the corpus comes from carries no publication marker, so that flag is set when another
   ruling in the database cites the docket as "zur Publikation vorgesehen" / "destiné à la
   publication"; it will miss recent leading cases that nobody has cited yet.
2. **Apertus for rulings that pass the triage pre-filter** (`triage.prior(...).score >=
   PRIOR_CUTOFF`, the same function triage uses). The prompt holds the taxonomy, the matrix, the
   subject line with the categories it names, the most cited statutes, the outcome and the same
   ruling excerpt as triage (20,000 characters here). The reply is constrained by a JSON schema
   with enums for branch and categories (`response_format=json_schema`, supported by the
   gateway), so only listed labels can come back. A primary category outside the branch's column
   of the matrix is sent back with the error and retried, up to three attempts; secondary
   categories that do not fit are dropped. After three invalid replies the subject-line result is
   used.
3. **Subject line for all other rulings** (method `subject`): the issue in parentheses
   ("Unfallversicherung (Kausalzusammenhang)") is matched against German, French and Italian
   keywords per category, specific words before generic ones ("Kausalzusammenhang" alone does not
   say whether natural or adequate causality is at issue; "Invalidenrente" alone does not say what
   about the pension is disputed). Without a match (method `rule`) the branch comes from the
   statutes cited and the category is "Verfahren" for rulings not entertained or struck off,
   else "Andere".

## Results on the 55 examples

The example labels map onto the taxonomy one to one, except that `unfallbegriff` and
`listenverletzung` both map to `unfallbegriff`, `einkommensvergleich` to `invaliditaetsgrad`,
`unterstellung` to `unterstellung-praemien` and `haftung` to `regress-haftung`. Ten examples are
labelled `general` (branch not identifiable from the summary) and only count for the category;
the private-insurance example (VVG) counts as `other`. 23 of the 55 rulings were decided before
October 2025 and are not in the corpus; `data/eval/example_rulings.jsonl.gz` holds the full text
of all 55, fetched from the same mirror.

| version | primary category | gold category among primary + secondary | branch (45 labelled) |
|---|---|---|---|
| subject line only (the fallback) | 0.53 | 0.55 | 0.98 |
| v1: taxonomy and subject line in the prompt | 0.56 | 0.56 | 0.98 |
| v2: + categories named by the subject passed as a hint, stricter "Beweis" | 0.71 | 0.71 | 0.98 |
| **v3: + precedence rules (shipped)** | **0.76** | **0.76** | **0.98** |

v3 added three rules of legal precedence: whether an injury is a Listenverletzung or mainly due to
wear (Art. 6 Abs. 2 UVG) and whether a suicide is insured (Art. 48 UVV) belong to the notion of
accident, not causality; a pension revision (Art. 17 ATSG) or new application is
`rentenrevision` even though the degree of invalidity is reassessed. The prompt was tuned on the
same 55 examples, so these figures are optimistic; on the 10 rulings of the summary hold-out,
which the prompt changes were not aimed at, v3 gets 8 of 10 right (subject line: 6).

Where it still goes wrong (13 of 55):

- **The summary's focus differs from the ruling's main issue (6).** Suva's summary of 8C_607/2024,
  8C_720/2024, 8C_44/2025 and 8C_145/2025 is about a procedural point, while the ruling mainly
  decides a pension or causality; 8C_241/2025 and 9C_581/2024 are summarised for what they say
  about evidence. The classifier names the ruling's main question, which is arguably right for a
  filter, but scores as a miss.
- **Two categories that both fit (5).** 8C_72/2025 (integrity compensation and adequate
  causality), 8C_399/2025 (restitution of daily allowances), 8C_179/2025 (end of treatment and
  causality), 8C_458/2025 (premium dispute classified as procedure), 4A_106/2025 (VVG daily
  allowance, labelled as income comparison).
- **Wrong branch (1).** 8C_313/2024 is labelled accident insurance; Apertus and the subject line
  ("Invalidenversicherung") say invalidity insurance.
- **Listenverletzung read as causality (1).** 8C_78/2025, despite the v3 rule.

Branch accuracy is 44 of 45 for both methods: the subject line names the branch in almost every
ruling, so the LLM adds little there.

`python -m suva.eval.score_classification` reruns this evaluation (cached responses make reruns
free) and prints the per-ruling table below.

## Corpus, October 2025 to June 2026

`data/results/classification_2025q4_2026q1.jsonl` (3,934 rulings) and
`data/results/classification_2026q2.jsonl` (2,096 rulings), loaded by `make load`. One run over
both periods took under 7 minutes with 12 parallel calls; all 494 rulings that pass the triage
pre-filter got a valid Apertus answer (none fell back to the subject line).

| | Q4 2025 - Q1 2026 | Q2 2026 |
|---|---|---|
| Apertus (`llm`) | 306 | 188 |
| subject line (`subject`) | 774 | 443 |
| fallback rule (`rule`) | 2,854 | 1,465 |
| branch `uv` / `iv` / `mv` / `atsg` / `other` | 91 / 204 / 1 / 215 / 3,423 | 56 / 125 / 3 / 114 / 1,798 |
| five-judge panel | 236 | 144 |
| public deliberation | 6 | 6 |
| cited as intended for publication | 42 | 7 |

Most common primary categories among the Apertus classifications, Q2 2026: Verfahren 82,
Invaliditätsgrad & Einkommensvergleich 47, Rentenrevision 19, Natürliche Kausalität 11,
Hilflosenentschädigung & Pflege 8. Outcomes in Q2 2026: 910 not entertained, 891 dismissed, 145
remanded, 60 upheld, 23 partly upheld, 5 struck off, 62 not recognised (mostly joined cases or
dispositives without the usual opening line).

## Per-ruling results (v3)

| ruling | gold | Apertus | subject line | subject |
|---|---|---|---|---|
| 4A_106/2025 | other / Invaliditätsgrad & Einkommensvergleich | other / Taggeld & Leistungskürzung **x** | other / Taggeld & Leistungskürzung **x** | Taggeldversicherung |
| 8C_313/2024 | uv / Rentenrevision | iv / Invaliditätsgrad & Einkommensvergleich **x** | iv / Andere **x** | Invalidenversicherung |
| 8C_366/2024 | uv / Unfallbegriff & Listenverletzung | uv / Unfallbegriff & Listenverletzung ok | uv / Andere **x** | Unfallversicherung |
| 8C_498/2024 | uv / Adäquate Kausalität | uv / Adäquate Kausalität (+ Unfallbegriff & Listenverletzung) ok | uv / Heilbehandlung & Kostenübernahme (+ Natürliche Kausalität, Invaliditätsgrad & Einkommensvergleich) **x** | Unfallversicherung (Fallabschluss; Kausalzusammenhang; Invalidenrente) |
| 8C_517/2024 | uv / Unfallbegriff & Listenverletzung | uv / Unfallbegriff & Listenverletzung ok | uv / Andere **x** | Assurance-accidents (suicide; capacité de discernement) |
| 8C_535/2024 | - / Invaliditätsgrad & Einkommensvergleich | iv / Invaliditätsgrad & Einkommensvergleich ok | iv / Andere **x** | Invalidenversicherung |
| 8C_607/2024 | uv / Verfahren | uv / Invaliditätsgrad & Einkommensvergleich **x** | uv / Integritätsentschädigung (+ Invaliditätsgrad & Einkommensvergleich) **x** | Assurance-accidents (rente d'invalidité; indemnité pour atteinte à l'intégrité) |
| 8C_626/2024 | uv / Hilflosenentschädigung & Pflege | uv / Hilflosenentschädigung & Pflege ok | uv / Hilflosenentschädigung & Pflege ok | Unfallversicherung (Pflegeleistung) |
| 8C_656/2024 | uv / Invaliditätsgrad & Einkommensvergleich | uv / Invaliditätsgrad & Einkommensvergleich ok | uv / Andere **x** | Unfallversicherung |
| 8C_676/2024 | - / Invaliditätsgrad & Einkommensvergleich | uv / Invaliditätsgrad & Einkommensvergleich ok | uv / Andere **x** | Unfallversicherung |
| 8C_687/2024 | uv / Rentenrevision | uv / Rentenrevision ok | uv / Andere **x** | Unfallversicherung |
| 8C_719/2024 | uv / Invaliditätsgrad & Einkommensvergleich | uv / Invaliditätsgrad & Einkommensvergleich ok | uv / Invaliditätsgrad & Einkommensvergleich ok | Unfallversicherung (Invaliditätsbemessung) |
| 8C_720/2024 | - / Verfahren | uv / Natürliche Kausalität **x** | uv / Natürliche Kausalität **x** | Assurance-accidents (lien de causalité) |
| 8C_7/2025 | uv / Invaliditätsgrad & Einkommensvergleich | uv / Invaliditätsgrad & Einkommensvergleich ok | uv / Invaliditätsgrad & Einkommensvergleich ok | Assurance-accidents (revenu sans invalidité) |
| 8C_21/2025 | uv / Berufskrankheit | uv / Berufskrankheit ok | uv / Berufskrankheit ok | Assurance-accidents (maladie professionnelle) |
| 8C_44/2025 | iv / Verfahren | iv / Invaliditätsgrad & Einkommensvergleich **x** | iv / Invaliditätsgrad & Einkommensvergleich **x** | Invalidenversicherung, Invalidenrente |
| 8C_62/2025 | uv / Natürliche Kausalität | uv / Natürliche Kausalität ok | uv / Natürliche Kausalität ok | Assurance-accidents (statu quo sine vel ante) |
| 8C_72/2025 | uv / Adäquate Kausalität | uv / Integritätsentschädigung **x** | uv / Integritätsentschädigung (+ Invaliditätsgrad & Einkommensvergleich) **x** | Assurance-accidents (rente d'invalidité; indemnité pour atteinte à l'intégrité) |
| 8C_78/2025 | uv / Unfallbegriff & Listenverletzung | uv / Natürliche Kausalität **x** | uv / Natürliche Kausalität **x** | Unfallversicherung (Unfallkausalität) |
| 8C_129/2025 | uv / Unterstellung & Prämien | uv / Unterstellung & Prämien ok | uv / Unterstellung & Prämien ok | Assurance-accidents (CNA; obligation d'assurance personnel de nettoyage) |
| 8C_135/2025 | uv / Invaliditätsgrad & Einkommensvergleich | uv / Invaliditätsgrad & Einkommensvergleich ok | uv / Invaliditätsgrad & Einkommensvergleich ok | Assicurazione contro gli infortuni (rendita d'invalidità) |
| 8C_145/2025 | - / Verfahren | iv / Invaliditätsgrad & Einkommensvergleich **x** | iv / Invaliditätsgrad & Einkommensvergleich **x** | Assurance-invalidité (rente d'invalidité) |
| 8C_154/2025 | - / Invaliditätsgrad & Einkommensvergleich | uv / Invaliditätsgrad & Einkommensvergleich ok | uv / Integritätsentschädigung (+ Invaliditätsgrad & Einkommensvergleich) **x** | Assurance-accidents (rente d'invalidité; indemnité pour atteinte à l'intégrité) |
| 8C_172/2025 | uv / Natürliche Kausalität | uv / Natürliche Kausalität ok | uv / Natürliche Kausalität ok | Assurance-accidents (lien de causalité) |
| 8C_176/2025 | uv / Taggeld & Leistungskürzung | uv / Taggeld & Leistungskürzung ok | uv / Taggeld & Leistungskürzung ok | Assurance-accidents (réduction de la prestation; indemnité journalière) |
| 8C_177/2025 | uv / Unfallbegriff & Listenverletzung | uv / Unfallbegriff & Listenverletzung ok | uv / Unfallbegriff & Listenverletzung ok | Assurance-accidents (lésion corporelle assimilée à un accident) |
| 8C_178/2025 | uv / Taggeld & Leistungskürzung | uv / Taggeld & Leistungskürzung ok | uv / Taggeld & Leistungskürzung ok | Assurance-accidents (gain assuré) |
| 8C_179/2025 | uv / Natürliche Kausalität | uv / Invaliditätsgrad & Einkommensvergleich **x** | uv / Natürliche Kausalität ok | Assurance-accidents (stabilisation de l'état de santé; lien de causalité) |
| 8C_180/2025 | uv / Unfallbegriff & Listenverletzung | uv / Unfallbegriff & Listenverletzung ok | uv / Natürliche Kausalität **x** | Unfallversicherung (Kausalzusammenhang) |
| 8C_184/2025 | iv / Regress & Haftung | iv / Regress & Haftung ok | iv / Regress & Haftung ok | Assurance-invalidité (demande en réparation) |
| 8C_185/2025 | - / Hilflosenentschädigung & Pflege | iv / Hilflosenentschädigung & Pflege ok | iv / Hilflosenentschädigung & Pflege ok | Invalidenversicherung (Hilflosenentschädigung) |
| 8C_223/2025 | uv / Rentenrevision | uv / Rentenrevision ok | uv / Rentenrevision (+ Invaliditätsgrad & Einkommensvergleich) ok | Assurance-accidents (révision; revenu sans invalidité) |
| 8C_224/2025 | uv / Unfallbegriff & Listenverletzung | uv / Unfallbegriff & Listenverletzung ok | uv / Andere **x** | Unfallversicherung |
| 8C_241/2025 | iv / Beweis & medizinische Gutachten | iv / Invaliditätsgrad & Einkommensvergleich **x** | iv / Invaliditätsgrad & Einkommensvergleich **x** | Invalidenversicherung (Invalidenrente; Arbeitsunfähigkeit) |
| 8C_275/2025 | uv / Natürliche Kausalität | uv / Natürliche Kausalität ok | uv / Natürliche Kausalität ok | Unfallversicherung (Kausalzusammenhang) |
| 8C_311/2025 | uv / Adäquate Kausalität | uv / Adäquate Kausalität ok | uv / Natürliche Kausalität **x** | Assurance-accidents (lien de causalité) |
| 8C_314/2025 | iv / Hilflosenentschädigung & Pflege | iv / Hilflosenentschädigung & Pflege ok | iv / Hilflosenentschädigung & Pflege ok | Assurance-invalidité (allocation pour impotent) |
| 8C_318/2025 | uv / Verfahren | uv / Verfahren ok | uv / Verfahren ok | Assurance-accidents (procédure administrative; condition de recevabilité) |
| 8C_330/2025 | - / Invaliditätsgrad & Einkommensvergleich | uv / Invaliditätsgrad & Einkommensvergleich ok | uv / Invaliditätsgrad & Einkommensvergleich ok | Assurance-accidents (revenu d'invalide) |
| 8C_334/2025 | uv / Natürliche Kausalität | uv / Natürliche Kausalität ok | uv / Natürliche Kausalität ok | Assurance-accidents (lien de causalité) |
| 8C_348/2025 | uv / Adäquate Kausalität | uv / Adäquate Kausalität ok | uv / Adäquate Kausalität (+ Natürliche Kausalität) ok | Assurance-accidents (lien de causalité; traumatisme cranio-cérébral) |
| 8C_351/2025 | uv / Verfahren | uv / Verfahren ok | uv / Verfahren ok | Assurance-accidents (procédure administrative; condition de recevabilité) |
| 8C_356/2025 | uv / Adäquate Kausalität | uv / Adäquate Kausalität ok | uv / Natürliche Kausalität **x** | Assurance-accidents (lien de causalité) |
| 8C_368/2025 | uv / Verfahren | uv / Verfahren ok | uv / Verfahren ok | Assurance-accidents (procédure de première instance; condition de recevabilité) |
| 8C_399/2025 | uv / Taggeld & Leistungskürzung | uv / Rückforderung & Erlass **x** | uv / Rückforderung & Erlass (+ Invaliditätsgrad & Einkommensvergleich) **x** | Assurance-accidents (rente d'invalidité; restitution) |
| 8C_450/2025 | iv / Beweis & medizinische Gutachten | iv / Beweis & medizinische Gutachten ok | iv / Invaliditätsgrad & Einkommensvergleich **x** | Invalidenversicherung (Invalidenrente; berufliche Massnahmen) |
| 8C_455/2025 | - / Verfahren | iv / Verfahren ok | iv / Verfahren ok | Invalidenversicherung (Prozessvoraussetzung) |
| 8C_458/2025 | uv / Unterstellung & Prämien | uv / Verfahren **x** | uv / Andere **x** | Unfallversicherung |
| 8C_508/2025 | uv / Integritätsentschädigung | uv / Integritätsentschädigung ok | uv / Integritätsentschädigung ok | Assurance-accidents (indemnité pour atteinte à l'intégrité) |
| 8C_525/2025 | uv / Rentenrevision | uv / Rentenrevision ok | uv / Rentenrevision (+ Invaliditätsgrad & Einkommensvergleich) ok | Assurance-accidents (révision; rente d'invalidité) |
| 8C_531/2025 | - / Hilflosenentschädigung & Pflege | iv / Hilflosenentschädigung & Pflege ok | iv / Hilflosenentschädigung & Pflege ok | Invalidenversicherung (Hilflosenentschädigung) |
| 8C_613/2025 | uv / Rückforderung & Erlass | uv / Rückforderung & Erlass ok | uv / Rückforderung & Erlass ok | Assurance-accidents (remise de l'obligation de restituer; bonne foi) |
| 9C_581/2024 | - / Beweis & medizinische Gutachten | iv / Invaliditätsgrad & Einkommensvergleich **x** | iv / Invaliditätsgrad & Einkommensvergleich **x** | Assurance-invalidité (novelle demande; évaluation de l'invalidité) |
| 9C_65/2025 | iv / Verfahren | iv / Verfahren ok | iv / Verfahren ok | Assicurazione per l'invalidità (diniego di giustizia e ritardata giustizia; spese giudiziarie in procedura cantonale) |
| 9C_382/2025 | iv / Invaliditätsgrad & Einkommensvergleich | iv / Invaliditätsgrad & Einkommensvergleich ok | iv / Andere **x** | Invalidenversicherung |
