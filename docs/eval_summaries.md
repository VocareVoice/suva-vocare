# Summary evaluation

How the summary writer `src/suva/summarize.py` (prompt version `v6`, model `apertus-v1-5-70b`)
works, and how its German and French summaries compare with Suva's human summaries on the
hold-out of `data/eval/split.json`: 10 rulings (5 German-, 4 French- and 1 Italian-language;
authors FRT, LC4 and VIL), never shown to the model.

## Method

1. **Source.** The ruling is split into rubrum, facts, reasons and operative part. Costs, legal
   aid, the notification list and the signature are dropped from the operative part, the
   considerations on the costs of the federal proceedings (Art. 64-68 BGG) from the reasons, and
   facts longer than 8,000 characters are cut in the middle. Up to 70,000 characters (about 20,000 tokens) go to the
   model unchanged. Longer reasons are condensed chunk by chunk into notes that keep their
   consideration numbers; no accident insurance ruling in the corpus is that long.
2. **Holdings.** The model first lists the Court's own conclusions, one line per numbered
   consideration. Both drafts get this list next to the ruling. Without it the model merged two
   considerations of 8C_185/2025 and turned "duty to notify violated" (E. 6.2) into "not
   violated" (it took the reasoning of E. 7.2, which is about the time limit for restitution).
3. **Style.** The prompt (`src/suva/prompts/summary_style.md`, `summary_de.md`,
   `summary_fr.md`) is the house style of `docs/style_guide.md`, adapted to Villa Rebeca (VIL),
   who is expected to evaluate the summaries (section 11 of the style guide). It covers facts,
   the cantonal court, the principles the Court recalls, their application and the outcome, with
   a consideration reference closing each statement. It aims shorter than her examples: 150-200
   words in German, 160-220 in French. Per language it adds the citation format, statute
   abbreviations, outcome formulas, and the glossary entries (`data/eval/glossary.json`) that
   occur in the ruling.
4. **Few-shot.** Her summaries 8C_7/2025 and 8C_172/2025. For German prompts these are corrected
   renderings of her French originals (`src/suva/prompts/style_examples_de.json`), because the
   German texts in the examples are translations with artefacts. 8C_613/2025, her third summary,
   is in the hold-out and is never shown. A third example chosen by similarity to the ruling was
   tried and dropped, because the model copied its facts (see below).
5. **Two originals.** The summary in the ruling's language is written first, from the ruling.
   The other language is also written from the ruling, with the first summary as an outline so
   that both cover the same points.
6. **Self-check and revision.** Each draft is checked against rules:
   - length;
   - consideration references that exist in the ruling;
   - statutes the ruling cites;
   - figures and dates that occur in the ruling;
   - no anonymised names or initials, and no birth years;
   - no insurer other than Suva named, and Suva only when it is a party;
   - no sentence in which the Federal Supreme Court decides the appeal otherwise than the
     operative part, or decides the appeal of a party that did not appeal (v2: "Das
     Bundesgericht weist die Beschwerde der Suva ab" in the middle of a summary of Suva's
     upheld appeal, 8C_254/2025, which the closing-sentence fix did not reach; the finishing
     step replaces such a sentence by the operative part when the revision keeps it);
   - the target language's statute abbreviations and terms, the glossary's avoid list and the
     citation format;
   - no German percentage adjective ("10%igen Abzugspraxis", v3);
   - a principle the Court recalls ("erinnert daran" / "rappelle"; v4: the German summary of
     8C_256/2025 listed the findings without the rule of E. 5.2).

   The model also checks the draft claim by claim, quoting the ruling for each claim. Both sets
   of findings go back for a revision. A second revision follows if rule checks still fail, and
   an overlong text is shortened to at most 200 words in German and 220 in French (v3; before,
   230 and 250). A shortening that drops the consideration references or the paragraphs is
   rejected and drawn again with some sampling. Apertus often returned the text unchanged
   (8C_718/2025 stayed at 250 words through every rewrite), so a final text that is still too
   long is cut by whole sentences (v6): the model ranks the numbered sentences from least to
   most needed, and the least needed are deleted until the text fits. The first sentence of a
   paragraph, the cantonal court's decision, the principles the Court recalls, the closing
   outcome paragraph and the last consideration reference are never deleted. Asked instead
   which sentences to delete, the model named half of them (8C_718/2025 fell to 88 words); a
   rewrite prompt naming the number of words to remove (v5) made the top summaries worse and
   was dropped. The checks see only the rules, not the examples: with the examples
   in context, the model quoted an example as if it were the ruling.
7. **Consistency.** The model compares the German and the French summary and names, for each
   contradiction, the version the ruling supports; that version's counterpart is revised.
8. **Finishing.** Every final text gets the rule checks once more. Anonymised names ("Dr. med.
   D.") are replaced by the person's role. Deleting them broke sentences, and the general
   revision often kept them, so a separate model step does the replacement. The closing sentence
   must state the operative part: the appellant comes from the rubrum (Suva, the insured person
   with grammatical gender, the IV office, another insurer), the result from the first point of
   the operative part, and a closing sentence with the wrong result or party is replaced by the
   standard formula. Five-judge rulings, detected from the bench in the rubrum, end with
   "Fünfer-Entscheid." / "Décision à cinq.". Citation format, Swiss amounts, "Suva" for "CNA",
   the Italian abbreviations of Italian rulings (LAINF, OAINF, OAI, INSAI; v2) and anonymised
   places ("in U.________"; v2) are normalised deterministically. v3 adds: the finishing step
   shortens again (the revisions and the consistency fix lengthened the texts); OAI becomes
   RAI / IVV with its article wherever the ruling cites the Italian IV ordinance ("la révision
   de l'OAI" → "du RAI", 8C_254/2025); a word the model copied from the ruling with one letter
   too many or too few, which neither the ruling nor the corpus contains, takes the ruling's
   spelling ("Beimmann" → "Beimann", 8C_343/2025); a canton in brackets after an anonymised
   employer goes ("bei einer Firma (TI)"); the outcome sentence becomes a paragraph of its own;
   and the prompt calls another insurer "the accident insurer" instead of "an accident insurer
   other than Suva", which the model copied into 8C_63/2026. v4: a short sentence before the
   closing paragraph that only states the outcome goes ("Das Bundesgericht heisst die Beschwerde
   der Suva gut.", 8C_254/2025), "der B.________ GmbH" becomes "einer GmbH" instead of "der
   GmbH", and the consistency check compares every figure, duration, percentage and date (the
   German summary of 8C_256/2025 said "fast vier Jahre" for "quatre ans et huit mois"). v6:
   superscripts the ruling text lost are restored in the final French text ("1 er août" → "1er août", "la I e
   Cour" → "la Ire Cour").

A summary takes 10 to 16 model calls and 1 to 5 minutes on the shared gateway, so in the UI it
runs on demand with a progress state, or ahead of time with `suva summarize-relevant`. The model
is pinned to `apertus-v1-5-70b` (`summarize.MODEL`): a comparison with the thinking variant gave
no gain.

**Headlines.** Each run also writes a headline per language (`headline_de` / `headline_fr`): at
most about 12 words saying what the Court decided, without docket or date, e.g. "Keine analoge
Anwendung von Art. 26bis IVV in der Unfallversicherung" / "Pas d'application par analogie de
l'art. 26bis RAI dans l'assurance-accidents". It is written from the subject line, the operative
part and the extracted holdings (step 2), first in the ruling's language and then in the other
with the first as reference, with the glossary terms found in the ruling. A headline is checked
for length (15 words in German, 17 in French), language, the other language's statute
abbreviations, dockets, dates, names, an opening with the Court and (v3) procedural wording
("recours rejeté", "Beschwerde abgewiesen", "l'intimée", unless the appeal was inadmissible);
failures go back to the model twice, after which the headline is left out. Also in v3, a word
that no two rulings of the corpus in that language use, up to its ending and for German compounds
part by part, goes back to the model ("Prémiums" for "primes", 8C_470/2025); a headline whose
only problem is such a word is kept if the corrections find nothing better, because rare
legitimate words (an occupation) would otherwise cost the headline. `suva headline-relevant` runs only the source,
holdings and headline steps (3 to 6 calls), and a later summary reuses them from the cache.

## Results on the hold-out

Scores from `python -m suva.eval.score_summaries` (length ratio, ROUGE-L, chrF, glossary recall,
style issues) and three VIL style measures: the share of her five structural markers present
(facts first, cantonal court, principles recalled, application, closing outcome), paragraphs, and
consideration references. Each row is one run over the 10 hold-out rulings; the prompt changed
between runs, the model and the hold-out did not.

| run | change | lang | words | length ratio | ROUGE-L | chrF | glossary recall | style issues | VIL markers | paragraphs | consid. refs |
|---|---|---|---|---|---|---|---|---|---|---|---|
| v3 | style card of docs/style_guide.md, open critique | de | 184 | 0.98 | 0.19 | 45.4 | 0.58 | 0 | 0.66 | 2.6 | 3.2 |
| v3 |  | fr | 226 | 1.04 | 0.25 | 46.0 | 0.63 | 0 | 0.66 | 2.7 | 3.6 |
| v6 | VIL style and anchors | de | 268 | 1.48 | 0.18 | 48.2 | 0.62 | 0 | 0.84 | 4.0 | 3.6 |
| v6 |  | fr | 307 | 1.43 | 0.25 | 48.6 | 0.74 | 0 | 0.86 | 4.1 | 2.7 |
| v7 | + shorter target, outcome card, shortening pass | de | 194 | 1.11 | 0.18 | 43.1 | 0.57 | 0 | 0.82 | 2.7 | 3.6 |
| v7 |  | fr | 215 | 1.01 | 0.25 | 43.6 | 0.71 | 0 | 0.78 | 2.5 | 2.8 |
| v9 | + rules-only checks, outcome formula, DE/FR consistency check | de | 180 | 1.00 | 0.18 | 42.2 | 0.57 | 0 | 0.76 | 3.0 | 3.1 |
| v9 |  | fr | 218 | 1.02 | 0.24 | 43.4 | 0.68 | 0 | 0.82 | 3.0 | 2.9 |
| v10 | + holdings extraction | de | 184 | 1.02 | 0.20 | 43.6 | 0.57 | 0 | 0.78 | 3.1 | 2.6 |
| v10 |  | fr | 220 | 1.01 | 0.25 | 44.8 | 0.70 | 0 | 0.82 | 3.3 | 2.7 |
| v11 | + VIL anchors only (no similar example), finishing pass | de | 174 | 0.99 | 0.20 | 42.0 | 0.55 | 0 | 0.76 | 3.0 | 2.8 |
| v11 |  | fr | 222 | 1.04 | 0.25 | 43.9 | 0.70 | 0 | 0.80 | 3.5 | 3.0 |
| v12 | + federal costs considerations dropped from the source (final) | de | 190 | 1.05 | 0.20 | 44.8 | 0.62 | 0 | 0.68 | 3.0 | 2.8 |
| v12 |  | fr | 212 | 1.00 | 0.24 | 43.0 | 0.71 | 0 | 0.80 | 3.4 | 2.2 |

The final run against each human summary (`orig` marks the reference in the ruling's language,
written by the author; the other language is the author's translation):

| docket | author | lang | words gen/ref | ROUGE-L | chrF | glossary | VIL markers |
|---|---|---|---|---|---|---|---|
| 8C_313/2024 | FRT | de (orig) | 242/179 | 0.14 | 44.1 | 0.50 | 0.6 |
| 8C_313/2024 | FRT | fr | 247/236 | 0.18 | 40.9 | 0.58 | 0.6 |
| 8C_719/2024 | FRT | de (orig) | 157/100 | 0.20 | 44.8 | 0.70 | 0.8 |
| 8C_719/2024 | FRT | fr | 183/131 | 0.26 | 48.9 | 0.73 | 0.8 |
| 8C_78/2025 | FRT | de (orig) | 165/171 | 0.21 | 49.5 | 0.55 | 0.6 |
| 8C_78/2025 | FRT | fr | 166/236 | 0.23 | 39.7 | 0.55 | 0.8 |
| 8C_185/2025 | FRT | de (orig) | 200/218 | 0.12 | 34.6 | 0.67 | 0.8 |
| 8C_185/2025 | FRT | fr | 244/252 | 0.15 | 31.9 | 0.60 | 0.8 |
| 8C_351/2025 | LC4 | de | 192/516 | 0.21 | 27.9 | 0.53 | 0.8 |
| 8C_351/2025 | LC4 | fr (orig) | 206/558 | 0.23 | 28.6 | 0.58 | 1.0 |
| 8C_356/2025 | FRT | de | 261/321 | 0.24 | 48.6 | 0.90 | 0.6 |
| 8C_356/2025 | FRT | fr (orig) | 220/359 | 0.29 | 42.7 | 0.73 | 0.6 |
| 8C_450/2025 | FRT | de (orig) | 188/134 | 0.19 | 50.7 | 0.50 | 0.8 |
| 8C_450/2025 | FRT | fr | 232/165 | 0.20 | 43.3 | 0.62 | 1.0 |
| 8C_508/2025 | LC4 | de | 170/176 | 0.32 | 57.5 | 0.86 | 0.6 |
| 8C_508/2025 | LC4 | fr (orig) | 216/186 | 0.37 | 56.1 | 1.00 | 1.0 |
| 8C_613/2025 | VIL | de | 157/261 | 0.22 | 41.0 | 0.38 | 0.6 |
| 8C_613/2025 | VIL | fr (orig) | 206/258 | 0.29 | 47.7 | 0.71 | 0.8 |
| 9C_65/2025 | LC4 | de | 171/111 | 0.17 | 49.7 | 0.67 | 0.6 |
| 9C_65/2025 | LC4 | fr | 203/129 | 0.20 | 49.9 | 1.00 | 0.6 |

ROUGE-L and chrF against a single human reference mainly measure wording overlap; the two
largest gaps (8C_351/2025, references of 516 and 558 words) are summaries three times longer than
ours. Across the hold-out the outputs have no style issues (foreign statute abbreviations,
avoid-list terms, citation format) and no statute, consideration, figure or date that the ruling
does not contain.

### Style match with VIL

The same measures on Suva's human summaries, by author, and on the final hold-out outputs:

| | lang | VIL markers | paragraphs | consid. refs | words (median) |
|---|---|---|---|---|---|
| VIL (3 summaries) | de / fr | 0.80 / 0.93 | 4.7 / 4.7 | 3.7 / 3.7 | 283 / 287 |
| LC4 (14) | de / fr | 0.67 / 0.77 | 4.1 / 4.0 | 2.4 / 2.8 | 216 / 239 |
| FRT (38) | de / fr | 0.35 / 0.35 | 2.4 / 2.4 | 0.0 / 0.0 | 159 / 196 |
| generated, final (10) | de / fr | 0.68 / 0.80 | 3.0 / 3.4 | 2.8 / 2.2 | 190 / 212 (mean) |

The generated summaries follow her structure and citation habit (close to VIL and LC4, far from
FRT) at about two thirds of her length, as asked. On her hold-out ruling 8C_613/2025 the French
summary has 4 of her 5 markers and 206 words against her 258.

### Legal accuracy, read against the rulings

The automatic scores do not show legal errors, so every hold-out summary was read against its
ruling. The LLM judge of `score_summaries --judge` was not used for decisions: with Apertus as
judge it rated a correct summary of 8C_719/2024 as reversing the outcome.

| Error found in earlier runs | Fix | Final run |
|---|---|---|
| Outcome copied from an example: "Letztlich wies das Bundesgericht die Beschwerde der Suva ab" for an upheld appeal (8C_613/2025); hybrids like "wies ... gut" | outcome sentence built from the rubrum and the operative part when the model's is wrong | all 20 correct |
| "Verletzung der Meldepflicht verneint" where the Court found it violated (8C_185/2025, E. 6.2), mixed up with the time limit of E. 7.2 | holdings extracted per consideration before writing | correct in both languages |
| Facts of the similar example in the summary (8C_450/2025 FR: the 3.5 m fall of 8C_72/2025) | similar example dropped | none |
| "la Suva" for a case against another insurer (8C_351/2025 FR) | Suva named only when it is a party | none |
| "art. 37 OLAA" for the IV ordinance (8C_185/2025 FR) | statutes checked against the ruling | none |
| "Dr. med. D.", "Der Dachdecker A.", birth years | names replaced by roles, birth years removed | none |
| Federal Court costs and legal aid in the summary | costs dropped from the source | none |

Remaining weaknesses in the final run: some German sentences are clumsy ("Nach verweigerter
Erlassgesuch", 8C_613/2025; "Einspracheentscheidung", 8C_351/2025), one German summary starts
with "Der Versicherte" for a female insured person (9C_65/2025), the French of German rulings
sometimes keeps a German term ("GgV Ziff. 382", 8C_185/2025), and the facts paragraph of a
long procedural history can attribute a figure to the wrong stage (8C_313/2024 in an earlier
run). The claim-by-claim check rarely finds anything: Apertus 70B (also the thinking variant)
missed both an injected wrong figure and the 8C_185/2025 error, which is why the rule checks,
the holdings step and the outcome formula carry the accuracy work.

## Side by side

### 8C_613/2025 - VIL's own summary (hold-out)

**Villa Rebeca, French original**

> Un assuré percevait des indemnités journalières de la Suva après un accident à l’épaule. La Suva lui a ensuite réclamé la restitution de CHF 16'751.65, au motif que l’indemnité versée pour l’activité auprès d’un employeur avait été calculée trop largement. L’assuré a demandé la remise, invoquant sa bonne foi et sa situation financière difficile.
>
> Le Tribunal fédéral rappelle que la remise suppose cumulativement la bonne foi et une situation difficile (art. 25 al. 1 LPGA). La bonne foi est exclue lorsque l’assuré pouvait reconnaître, avec l’attention exigible, que les prestations étaient indues, notamment en cas de négligence grave. L’examen de l’attention exigible relève du droit, que le Tribunal fédéral revoit librement (consid. 3.1 à 3.3).
>
> En l’espèce, le Tribunal fédéral a considéré que le Tribunal cantonal avait occulté le fait que les indemnités journalières cumulées perçues par l’assuré – en raison de ses différentes activités – étaient largement supérieures au revenus perçus avant l’accident. Le total atteignait environ CHF 7'770.- par mois, soit presque le double des revenus antérieurs d’environ CHF 4'000.-. En clair, le Tribunal cantonal avait établi les faits de manière manifestement inexacte et incomplète, ce qui confine à l'arbitraire (consid. 5.2.1).
>
> Si l’assuré ne devait pas nécessairement déceler l’erreur à la seule lecture du courrier initial, il aurait dû réagir une fois les versements reçus, ceux-ci étant manifestement disproportionnés par rapport à ses salaires antérieurs auprès de l’employeur concerné. Son omission de se renseigner constitue une négligence grave, excluant la bonne foi (consid. 5.2.2).
>
> Le recours de la Suva est admis; la remise est refusée.

**Generated, French**

> Assuré, engagé à temps partiel auprès de deux employeurs et au chômage, s’est blessé à l’épaule gauche le 18 septembre 2020. La Suva lui a versé des indemnités journalières, puis a demandé la restitution d’un trop-perçu. L’assuré a requis la remise, que la Suva a refusée. Saisie d’un recours, la Cour des assurances sociales vaudoise a admis la bonne foi de l’assuré et renvoyé la cause à la Suva pour examiner la condition de la situation difficile. La Suva a recouru au Tribunal fédéral.
>
> Le Tribunal fédéral rappelle que la bonne foi est exclue dès qu’il y a dol ou négligence grave (art. 25 al. 1 LPGA). Il constate que les indemnités journalières perçues par l’assuré, cumulées, s’élevaient à près du double des revenus cumulés avant l’accident. Il retient qu’après avoir reçu ces prestations, l’assuré aurait dû, avec un minimum d’attention, remarquer l’écart important avec ses salaires antérieurs et se renseigner ou contacter la Suva ou son employeur. En s’abstenant de le faire, il a commis une négligence grave excluant sa bonne foi (consid. 5.2.2). Partant de là, les juges annulent l’arrêt cantonal et confirment la décision sur opposition refusant la remise (consid. 6).
>
> En définitive, le Tribunal fédéral a admis le recours de la Suva.

**Suva's German version (translation)**

> Ein Versicherter bezog nach einem Schulterunfall Taggelder der Suva. Die Suva forderte von ihm später die Rückerstattung von CHF 16'751.65, da das für die Tätigkeit bei einem Arbeitgeber ausgerichtete Taggeld zu hoch berechnet worden war. Der Versicherte ersuchte um Erlass der Rückerstattungspflicht und berief sich auf seinen guten Glauben sowie auf seine schwierige finanzielle Lage.
>
> Das Bundesgericht erinnert daran, dass der Erlass kumulativ den guten Glauben und eine grosse Härte voraussetzt (Art. 25 Abs. 1 ATSG). Der gute Glaube ist ausgeschlossen, wenn der Versicherte bei gebotener Aufmerksamkeit hätte erkennen können, dass die Leistungen unrechtmässig bezogen wurden, insbesondere bei grober Fahrlässigkeit. Die Prüfung der zumutbaren Aufmerksamkeit ist eine Rechtsfrage, die das Bundesgericht frei überprüft (E. 3.1 bis 3.3).
>
> Im vorliegenden Fall erwog das Bundesgericht, dass das kantonale Gericht den Umstand ausgeblendet hatte, dass die vom Versicherten aufgrund seiner verschiedenen Tätigkeiten kumuliert bezogenen Taggelder deutlich höher waren als die vor dem Unfall erzielten Einkünfte. Insgesamt beliefen sie sich auf rund CHF 7'770.- pro Monat, also fast doppelt so viel wie die früheren Einkünfte von ungefähr CHF 4'000.-. Mit anderen Worten hatte das kantonale Gericht den Sachverhalt offensichtlich unrichtig und unvollständig festgestellt, was an Willkür grenzt (E. 5.2.1).
>
> Zwar musste der Versicherte den Fehler nicht zwingend bereits bei blosser Lektüre des ursprünglichen Schreibens erkennen. Nach Erhalt der Zahlungen hätte er jedoch reagieren müssen, da diese im Vergleich zu seinen früheren Löhnen beim betreffenden Arbeitgeber offensichtlich unverhältnismässig waren. Dass er sich nicht erkundigte, stellt eine grobe Fahrlässigkeit dar, welche den guten Glauben ausschliesst (E. 5.2.2).
>
> Die Beschwerde der Suva wird gutgeheissen; der Erlass wird verweigert.

**Generated, German**

> Der Versicherte, bei zwei Arbeitgebern und der Arbeitslosenversicherung tätig, verletzte sich am 18. September 2020 an der linken Schulter. Die Suva richtete Taggelder aus und forderte später einen Teilbetrag zurück. Nach verweigerter Erlassgesuch wurde die Sache an die Suva zurückgewiesen, um die Härte zu prüfen. Die Suva erhob Beschwerde ans Bundesgericht.
>
> Das Bundesgericht erinnert daran, dass die Gutgläubigkeit entfällt bei Vorsatz oder grober Nachlässigkeit (Art. 25 Abs. 1 ATSG). Es stellt fest, dass die dem Versicherten ausgerichteten Taggelder, kumuliert, fast doppelt so hoch waren wie seine vor dem Unfall erzielten Einkünfte. Es erwägt, dass der Versicherte nach Erhalt der Leistungen mit einem Mindestmass an Aufmerksamkeit hätte erkennen müssen, dass die Summe nicht mit seinen früheren Einkünften vereinbar war, und sich bei der Suva oder seinem Arbeitgeber hätte erkundigen müssen. Indem er dies unterliess, hat er grobfahrlässig gehandelt, was die Gutgläubigkeit ausschliesst (E. 5.2.2).
>
> Letztlich hiess das Bundesgericht die Beschwerde der Suva gut und bestätigte die ablehnende Einspracheverfügung.

### 8C_719/2024 - German ruling, FRT's German original (hold-out)

**Thomas Frei, German original**

> Das kantonale Gericht erhöhte die 2023 beginnende Invalidenrente von 12% auf 13%, wobei es das Invalideneinkommen aufgrund eines auf 2022 aufgerechneten Tabellenlohnes und das Valideneinkommen gestützt auf die Angaben des Arbeitgebers per 2023 festlegte.
>
> Wegen des Erfordernisses der zeitidentischen Grundlage ist das Valideneinkommen bezüglich des nämlichen Zeitraums (hier: 2022) wie das Invalideneinkommen festzulegen. Die Frage, ob die Quartalsschätzungen der Nominallohnentwicklung für das Jahr 2023 anwendbar wären, lässt das Bundesgericht offen.
>
> Anmerkung: das kantonale Gericht rechnete den Tabellenlohn nicht auf 2023 auf, weil die «Indexzahlen 2023 zum Zeitpunkt des Einspracheentscheids noch nicht veröffentlicht» gewesen sind, ohne jedoch die Quartalsschätzungen zu erwähnen.

**Generated, German**

> Der Versicherte, als Fassadenmonteur tätig und bei der Suva unfallversichert, erlitt am 16. April 2018 bei einem Sturz eine distale intraartikuläre Radiustrümmerfraktur rechts. Nach mehreren Operationen und einer kreisärztlichen Untersuchung stellte die Suva die Leistungen per Ende Januar 2023 ein und sprach eine Invalidenrente von 12 % sowie eine Integritätsentschädigung zu. Das Kantonsgericht Luzern erhöhte den Invaliditätsgrad auf 13 %, indem es das Valideneinkommen auf die Angaben der ehemaligen Arbeitgeberin für das Jahr 2023 abstützte, während es das Invalideneinkommen anhand der LSE 2020 für das Jahr 2022 ermittelte.
>
> Das Bundesgericht erinnerte daran, dass das Valideneinkommen so konkret wie möglich zu ermitteln ist (E. 4.2). Es stellte fest, dass die ehemalige Arbeitgeberin für das Jahr 2022 einen mutmasslichen Verdienst von CHF 70'415.- angegeben hatte. Aus der Gegenüberstellung mit dem Invalideneinkommen resultierte ein Invaliditätsgrad von gerundet 11 %. In diesen Umständen hiess das Bundesgericht die Beschwerde der Suva gut und bestätigte den Einspracheentscheid vom 15. November 2023 (E. 5).

**Generated, French**

> Assuré, façadier-peintre assuré auprès de la Suva, s’est blessé le 16 avril 2018 à la main droite lors d’une chute sur un chantier. Après plusieurs interventions chirurgicales et une appréciation du médecin d’arrondissement, la Suva a mis fin aux prestations et alloué une rente d’invalidité de 12 % ainsi qu’une indemnité pour atteinte à l’intégrité. Le Tribunal cantonal de Lucerne a porté le taux d’invalidité à 13 % en se fondant sur le salaire 2023 indiqué par l’ancien employeur pour le revenu sans invalidité, tandis que le revenu d’invalide était calculé sur la base de l’ESS 2020 indexé à 2022.
>
> Le Tribunal fédéral rappelle que le revenu sans invalidité doit être déterminé de la manière la plus concrète possible (consid. 4.2). Il constate que l’ancien employeur avait indiqué un salaire de CHF 70'415.- pour l’année 2022. Comparé au revenu d’invalide, le degré d’invalidité s’élève à 11 %. Dans ces circonstances, le Tribunal fédéral admet le recours de la Suva et confirme la décision sur opposition du 15 novembre 2023 (consid. 5).
>
> En définitive, le Tribunal fédéral a admis le recours de la Suva.

Both generated versions state the decisive point (the incomes must be compared for the same year,
2022), the figures (CHF 70'415.-, 11 %) and the outcome. FRT's summary also notes that the Court
left open whether the quarterly estimates of nominal wages for 2023 apply; ours does not.

## Reproduce

```sh
DB_PATH=data/eval.db uv run suva load data/eval/example_rulings.jsonl.gz
DB_PATH=data/eval.db uv run python - <<'PY'
import json
from suva import db, summarize
from suva.config import get_settings
from suva.eval.examples import load_split
from suva.llm import LLMClient

conn, llm = db.connect(get_settings().db_path), LLMClient(model=summarize.MODEL)
with open("generated.jsonl", "w") as out:
    for docket in load_split()["holdout"]:
        for lang, text in summarize.summarize(conn, docket, llm).summaries.items():
            row = {"docket": docket, "lang": lang, "text": text}
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
PY
uv run python -m suva.eval.score_summaries generated.jsonl
```

With `LLMClient(model=summarize.MODEL)` (`apertus-v1-5-70b`) at temperature 0. The gateway is not bit-for-bit deterministic,
so wording and the scores above vary slightly between runs.
