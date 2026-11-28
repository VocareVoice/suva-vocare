# Feedback review - example report (synthetic corrections)

> **Example.** The expert feedback below is **synthetic**: five score corrections and one edited
> summary, entered through the app's API (`PUT /api/rulings/{docket}/score`,
> `PUT /api/rulings/{docket}/summaries/de`) on a scratch copy of the database to demonstrate the
> `feedback-review` skill (`.claude/skills/feedback-review/SKILL.md`, workflow in
> `docs/feedback_loop.md`). The rulings, the model's scores and reasonings, the generated
> summary and all counts from the labelled period are real; the experts' scores, comments and
> edit are not Suva's. The corrections were chosen to agree with Suva's real Q4 2025 / Q1 2026
> list, and every comment was checked against its ruling. **Nothing in this report has been
> applied.** It was made when the relevance threshold was 50; it is now 28.

## 1. Summary

The experts raised three invalidity insurance (IV) rulings that the triage had left below 50 and
lowered two accident insurance (UV) rulings that it had rated 85. In all three IV cases the
model's reasoning dismisses the ruling because it is IV rather than UV, although the prompt's
"Erfahrungswerte" paragraph already names the topics the experts point to; a general rule for
IV rulings is not supported by the labelled period (it repeats the rejected v4b) and is not
proposed. The best-supported change is narrow: name the IV helplessness allowance as a
transferable topic (S1), where Suva listed 3 of 9 rulings in the labelled period against 1 in
10 for IV overall. The edited summary corrects a real error (the missing delegation norm is in
the UVG, not the UVV, and the French text has the same error), which points to the factual-check
prompt (S2), and its wording conflicts with a rule check of the summary pipeline (S3). Whether
routine UV rulings on medical evidence belong in the knowledge base is a question for the legal
team, not for a prompt change.

## 2. Data

| | |
|---|---|
| Database | scratch copy, built with `make load` (all committed results) |
| Export | `DB_PATH=<scratch>/demo.db uv run suva feedback-export --out <scratch>/feedback.json` |
| Prompt versions | triage `v5`, summary `v7`, headline `v3`; all corrections are against triage `v5` |
| Score corrections | 5 (3 raised, 2 lowered), all 5 cross the threshold of 50, 4 with a comment |
| Feedback rows | 5 (the history of the 5 corrections; no separate verdicts) |
| Edited summaries | 1 (8C_254/2025, German, `manual`); generated text found in `data/results/summaries_2026q2.jsonl` (`v7`) |
| Adjustment summaries | none stored (no Apertus endpoint was configured for the demo) |

Limits: five corrections are far too few for patterns; every finding below is an observation
or a hypothesis to test, not a measured effect. 8C_313/2024 has no comment, so its reason is
inferred.

## 3. Score corrections

| Docket | Branch / category | Model -> expert | Stage | Cause | Expert's reason |
|---|---|---|---|---|---|
| 8C_185/2025 | IV / Hilflosenentschädigung & Pflege | 36 -> 75 | Apertus | Prompt criterion not applied | "Meldepflichtverletzung, rückwirkende Aufhebung und Rückforderung nach Art. 25 ATSG: gilt gleich in der UV. Beschwerde der IV-Stelle gutgeheissen, übertragbar." |
| 8C_450/2025 | IV / Beweis & Gutachten | 34 -> 70 | Apertus | Prompt criterion not applied | "Formelle Anforderungen an ein Gutachten nach Art. 44 ATSG (Signatur der ergänzenden Stellungnahme des Sachverständigen): gilt für die UV genauso." |
| 8C_313/2024 | IV / Invaliditätsgrad | 35 -> 65 | Apertus | Hypothesis: prompt criterion not applied | none given |
| 8C_151/2025 | UV / Integritätsentschädigung | 85 -> 30 | Apertus | Policy question | "Reine Würdigung des Einzelfalls: 5 % Integritätsentschädigung bestätigt, keine voraussehbare Verschlimmerung." |
| 8C_679/2024 | UV / Verfahren | 85 -> 35 | Apertus | Policy question | "Bestätigt nur die ständige Rechtsprechung zum Beweiswert versicherungsinterner Berichte und zu Noven. Einzelfall, kein Grundsatz." |

What the rulings say (read in full):

- **8C_185/2025**: appeal of the St. Gallen IV office, upheld. The Court holds that the
  helplessness allowance ended on 1 May 2021 (E. 5.3), that the guardian breached the duty to
  report the improvement (E. 6.2), so the allowance could be cancelled retroactively, and that
  the repayment claim under Art. 25 ATSG was not time-barred (E. 7.2). The model: "IV-Urteil
  ohne übertragbare Grundsätze für Unfallversicherung ... da Suva nur UVG/UVV und
  Militärversicherung führt."
- **8C_450/2025**: the insured person's appeal, partly upheld and remanded. The cardiology
  expert who examined the insured person (the expert within Art. 44 ATSG, E. 4.1) did not sign
  the two supplementary statements on a test result; only the institute's medical director did.
  This formal defect leaves the expert opinion without probative value for now (E. 4.2-4.4).
  The model: "klärt eine formelle Frage zum Beweiswert eines Gutachtens im IV-Verfahren".
- **8C_313/2024**: the insured person's appeal, dismissed; revision of an IV pension
  (Art. 17 ATSG) and the usability of the remaining capacity to work. The model: "zur
  IV-rechtlichen Rentenrevision und Verwertbarkeit der Restarbeitsfähigkeit".
- **8C_151/2025** and **8C_679/2024**: the insured person's appeals against Suva, dismissed
  (8C_679/2024 to the extent admissible). Both apply settled case law to the facts; neither
  states a new rule. The model's reasonings describe the case ("Das Bundesgericht verneinte eine
  Verletzung des Untersuchungsgrundsatzes und wies die Beschwerde ab"; "bestätigt die
  Beweiskraft der versicherungsmedizinischen Beurteilungen") and still score both 85.

### Patterns and counter-evidence

**P1 - IV rulings dismissed as "not UV" (3 corrections, 2 with a stated general reason).** The
triage prompt already says that Suva takes about one in ten IV rulings, "nämlich die mit
Aussagen, die auch in der Unfallversicherung gelten (Invaliditätsbemessung, Verwertbarkeit der
Restarbeitsfähigkeit, Hilflosenentschädigung, Beweiswert von Gutachten, Revision, Verfahren nach
ATSG)". All three rulings fall under that list, and all three reasonings reject them for
being IV. The prompt is not missing the criterion; the model does not apply it.

Counter-evidence from the labelled period (Q4 2025 and Q1 2026; IV rulings past the gate, model
score, Suva's list):

| Group | Rulings | Listed by Suva | Listed, below 50 | Not listed, 50 or more |
|---|---|---|---|---|
| All IV | 151 | 16 (11 %) | 9 | 30 |
| IV citing Art. 17, 25 or 44 ATSG | 64 | 5 (8 %) | 5 | 14 |
| IV, category Beweis & Gutachten | 9 | 2 | 1 | 5 |
| IV, category Invaliditätsgrad | 75 | 8 | 5 | 16 |
| IV, category Hilflosenentschädigung & Pflege | 9 | 3 (33 %) | 2 | 0 |

- The experts' stated reason ("ATSG provision, applies to UV too") does not separate listed from
  unlisted rulings: the IV rulings citing those ATSG articles are listed less often than IV
  rulings overall. A rule built on it would raise about 60 rulings to find 5.
- Raising IV rulings on evidence or on the degree of invalidity in general is what v4b and v4c
  did (`docs/eval_triage.md`, "Tuning, checked across quarters"); both were rejected because
  they pushed listed UV rulings down. The model already scores 6 of the 9 IV evidence rulings at
  50 or more, and 5 of those 6 are not listed.
- The helplessness allowance is the one IV topic with a clear lift: 3 of 9 listed (33 %), 2 of
  them below 50 (8C_185/2025 at 36, 8C_531/2025 at 39), and no unlisted ruling at 50 or more.
  It is small (9 rulings), so a change here can move at most a handful of rulings.

**P2 - UV rulings on settled case law rated 85 (2 corrections).** The prompt already puts
"nur Würdigung des Einzelfalls" at level 3-4, but the model rates most UV rulings on the merits
high: 70 UV rulings of the labelled period scored 50 or more, and Suva listed 43 of them. In the labelled period, of the 37 UV rulings at 50 or more in which the
insured person's appeal was dismissed, Suva listed 21. A rule that lowers this kind of ruling
would cost more listed rulings than it removes. The rejected step 4b ("level 8 for a legal
question, 7 for medical evidence only") encoded the same idea and fitted one quarter but not
the other. This is a question of what Suva wants in the knowledge base (Q1 below).

## 4. Edited summary

**8C_254/2025, German** (five-judge panel; Suva's appeal upheld; generated `v7`, 152 -> 165
words). The edit rewrites two sentences of the Court's reasoning:

- Generated: "Das Bundesgericht erinnerte daran, dass die Revision der Invalidenversicherung
  und die 10 %-Abzugsregelung ausschliesslich im Bereich der Invalidenversicherung erfolgt
  seien (E. 7.4.1)."
  Edited: "Das Bundesgericht hielt fest, dass der pauschale Abzug von 10 % nach Art. 26bis
  Abs. 3 IVV gestützt auf Art. 28a IVG eingeführt wurde und nur für die Invalidenversicherung
  gilt (E. 7.4.1)."
- Generated: "Eine analoge Anwendung im Unfallversicherungsrecht sei nicht zulässig, da der
  Gesetzgeber bewusst keine entsprechende Delegationsnorm in der UVV geschaffen habe
  (E. 7.4.2)."
  Edited: "Dass im UVG eine entsprechende Delegationsnorm fehlt, ist ein bewusster Entscheid
  des Gesetzgebers; eine analoge Anwendung in der Unfallversicherung ist daher ausgeschlossen
  (E. 7.4.1 f.)."

Checked against the ruling (Italian): E. 7.4.1 speaks of "l'assenza di una regolamentazione
equivalente in materia di assicurazione contro gli infortuni, perlomeno nel principio attraverso
una norma di delegazione nella LAINF", a deliberate choice of the legislator. The delegation
norm is missing in the **UVG** (LAINF), not in the UVV; the generated sentence puts it at the
wrong level, and the French summary has the same error ("En l'absence de norme de délégation
dans l'OLAA"). The edit is right. Classification:

- **factual correction** (a provision at the wrong level of the hierarchy, statute vs
  ordinance): confirmed, in both languages. None of the four error types in
  `src/suva/prompts/summary_facts.md` names it, so the final factual check had no reason to flag
  it -> S2;
- **wording**: "erinnerte daran" (a principle the Court recalls) becomes "hielt fest", because
  this is the Court's own new holding in a five-judge ruling, not settled case law. The house
  style allows "hält fest" (`docs/style_guide.md`, line 73), but the rule check in
  `summarize.form_issues` asks for "erinner" or "rappel" in every summary and would push a
  regenerated text back to "erinnert daran" -> S3;
- **added precision** (Art. 28a IVG as the basis of the deduction): a preference of this
  editor; recorded, not proposed.

## 5. Suggested changes

### S1 - Triage: name the helplessness allowance as transferable (medium-low confidence)

- **Target**: `src/suva/triage.py`, `SYSTEM_PROMPT`, level scale:
  "5-6 = Grenzfall, z.B. Urteil einer anderen Sozialversicherung mit klar übertragbaren
  Grundsätzen"
- **Change**:

  ```diff
  -5-6 = Grenzfall, z.B. Urteil einer anderen Sozialversicherung mit klar übertragbaren \
  -Grundsätzen
  +5-6 = Grenzfall, z.B. Urteil einer anderen Sozialversicherung mit klar übertragbaren \
  +Grundsätzen, etwa ein IV-Urteil zur Hilflosenentschädigung (Art. 9 ATSG, auch Art. 26 UVG)
  ```

- **Evidence**: 8C_185/2025 (expert: "übertragbar"); in the labelled period 3 of 9 IV
  helplessness rulings listed, 2 of them below 50, no unlisted one at 50 or more.
- **Expected effect**: 8C_185/2025 and 8C_531/2025 rise toward 50; the six unlisted
  helplessness rulings (9C_214/2025 at 46 among them) may rise too. It names one topic, not IV
  in general, so it should not move UV rulings; v4b shows that a wider IV sentence does.
- **Validation**: triage cross-quarter rule (section 6). Accept only if neither quarter gets
  worse on P@10, P@30, R@30 or R@60 and 8C_185/2025 ends at 50 or more.
- **Confidence**: medium-low: one correction, nine rulings of evidence, and wording changes move
  single levels by several steps.

### S2 - Summaries: add "provision at the wrong level" to the factual check (medium confidence)

- **Target**: `src/suva/prompts/summary_facts.md`, error type 2: "A rule with the wrong meaning:
  the direction reversed ...; a threshold or a count misstated; ..."
- **Change**:

  ```diff
  -2. A rule with the wrong meaning: the direction reversed (liable or released, a presumption or its rebuttal, a condition or an exception); a threshold or a count misstated; preponderant probability turned into certainty; "could not assume in good faith that X" turned into "X was not possible".
  +2. A rule with the wrong meaning: the direction reversed (liable or released, a presumption or its rebuttal, a condition or an exception); a threshold or a count misstated; preponderant probability turned into certainty; "could not assume in good faith that X" turned into "X was not possible"; a provision placed in the wrong act or at the wrong level (the statute instead of the ordinance, UVG and UVV, LAA and OLAA).
  ```

- **Evidence**: 8C_254/2025, the same error in the German and the French text, confirmed by
  E. 7.4.1; one edit.
- **Expected effect**: the final factual check flags and fixes this error type in new
  summaries; no effect on texts without it. Risk: more false alarms on correct UVV citations.
- **Validation**: regenerate 8C_254/2025 and the hold-out on a copy with summary `v8`; the
  regenerated 8C_254/2025 must name the UVG in both languages; `score_summaries --judge` on the
  hold-out must not get worse than `v7`; a blind reading of the changed sentences.
- **Confidence**: medium: the error is real and in both languages, but it is one ruling.

### S3 - Summaries: let the recall check accept the Court's own holdings (medium confidence)

- **Target**: `src/suva/summarize.py`, `form_issues`:
  `if not re.search(r"\berinner|\brappel", draft):`
- **Change**: accept the verbs the house style lists for what the Court does (style guide
  line 73: "erinnert daran / hält fest / bestätigt"; "rappelle / constate / confirme"):

  ```diff
  -    if not re.search(r"\berinner|\brappel", draft):
  +    if not re.search(r"\berinner|\bh(?:ä|ie)lt\b[^.]{0,40}\bfest\b|\brappel|\bconstat", draft):
  ```

- **Evidence**: the expert replaced "erinnerte daran" by "hielt fest" for a new holding of a
  five-judge panel (8C_254/2025); the style guide already allows "hält fest".
- **Expected effect**: fewer revision rounds that force "erinnert daran" onto a new holding;
  summaries that recall a principle are unchanged. Risk: a summary with "hält fest" for the
  facts alone passes the check without stating a principle.
- **Validation**: rerun the hold-out with summary `v8`; count how often the check fired before
  and after, and blind-read the summaries whose principle sentence changed.
- **Confidence**: medium: a rule-based change that follows the style guide, but one edit.

## 6. No change recommended

- **8C_450/2025** and **8C_313/2024** (P1): IV rulings on evidence and on the degree of
  invalidity. The labelled period gives no rule that separates the listed ones (table above),
  and the general IV rule was tried and rejected (v4b, v4c). Keep them as corrections in the
  knowledge base.
- **ATSG citations as a signal** (the experts' stated reason): no lift in the labelled period
  (8 % listed against 11 %).
- **8C_151/2025** and **8C_679/2024** (P2): until the legal team answers Q1.
- The added reference to Art. 28a IVG in 8C_254/2025: one editor's preference.

### Questions for the legal team

1. **Routine UV rulings.** Should a UV ruling on the merits that only applies settled case law
   to the facts (insured person's appeal dismissed) be in the knowledge base? Suva listed 21 of
   37 such rulings at 50 or more in Q4 2025 and Q1 2026; the two corrections say no. The answer
   decides whether the triage should rate them lower at all.
2. **IV rulings.** Is the helplessness allowance (S1) the right exception, and are there other
   IV topics the experts always want (the corrections name evidence and the revision of a
   pension, where the labelled period shows no preference)?

## 7. Next steps

1. The legal team answers Q1 and Q2; the quality owner picks the suggestions to try (S1-S3).
2. A developer applies each chosen suggestion on its own branch, with a new `PROMPT_VERSION`,
   and runs its validation: triage on both labelled quarters with
   `uv run python -m suva.eval.score_triage` under the cross-quarter rule
   (`docs/eval_triage.md`); summaries with `uv run python -m suva.eval.score_summaries --judge`
   on the hold-out (`docs/eval_summaries.md`) and a blind reading.
3. Only changes that pass are merged, the evaluation docs get the new row, and the affected
   rulings are re-run with Apertus. Expert scores and edited summaries are kept: the pipeline
   never overwrites them.

Nothing in this report has been applied to the prompts, the rules or the database.
