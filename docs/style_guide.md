# Suva summary style guide

This guide is derived from Suva's 55 human summaries in `judgements/*.html` (parsed into `data/eval/examples.jsonl`) and from the relevance list `judgements/BG_Urteile_2025_Q4_2026_Q1.xlsx` (parsed into `data/eval/relevant_q4_2025_q1_2026.json`). It defines one house style for the German (DE) and French (FR) summaries that Apertus generates, and it describes which rulings Suva considers relevant. Section 1 is the condensed version for prompts; the rest gives the evidence and rationale.

## 1. Style card (prompt-ready)

1. **Two originals.** Write one German and one French summary of the same ruling. Both carry the same content in the same order, but each is written natively, with the terms, statute abbreviations and citation format of its own language (sections 4 and 8). Never translate word for word.
2. **Length.** German 120 to 250 words, about 180 on average. French about 20 % longer (median ratio FR/DE in the examples: 1.19). A ruling that turns on one narrow point may take one to three sentences. Never exceed 350 words.
3. **Structure.** Three to four paragraphs of continuous prose separated by blank lines. No title, headings, bullet points, bold text or quotation of party names.
   1. *Facts* (one to three sentences, past tense): the insured person, the accident or health damage, what the insurer decided, what the cantonal court decided, who appealed to the Federal Court. Leave this paragraph out when the ruling answers an abstract legal question for which the facts do not matter.
   2. *Principles* (present tense): the rule the Federal Court laid down or recalled, with the statutory provision and the consideration, worded so that it can be quoted without the case: "Das Bundesgericht erinnert daran, dass ... (E. 3.3)." / "Le Tribunal fédéral rappelle que ... (consid. 3.3)."
   3. *Application*: "Im vorliegenden Fall ..." / "En l'espèce, ...", only the reasons that decide the case, with the consideration.
   4. *Outcome*: one sentence with the standard formula of section 4.5, for example "Die Beschwerde des Versicherten wird abgewiesen." / "Le recours de l'assuré est rejeté."
   5. Optional last line, only when the ruling states it: "Fünfer-Entscheid." / "Décision à cinq." or "Fünfer-Entscheid, zur Publikation vorgesehen." / "Décision à cinq, prévue pour publication."
4. **Voice.** Neutral, impersonal, third person, no evaluation of the ruling. The court is "das Bundesgericht" / "le Tribunal fédéral" (variation: "die Bundesrichter" / "les juges fédéraux"). Facts in the past tense (DE Präteritum, FR passé composé), principles, application and outcome in the present tense.
5. **Parties.** "die Suva" / "la Suva" by name; any other accident insurer "der Unfallversicherer" / "l'assureur-accidents"; invalidity insurance "die IV-Stelle" / "l'office AI". The insured person is "der Versicherte" or "die Versicherte" / "l'assuré" or "l'assurée" as in the ruling, "die versicherte Person" / "la personne assurée" in abstract rules. The lower court is "das kantonale Gericht" or "die Vorinstanz" / "le tribunal cantonal" or "l'instance inférieure". No names of parties, lawyers, judges, experts or doctors.
6. **Citations.** DE: "Art. 6 Abs. 2 Bst. g UVG", "Art. 39 UVG, 50 UVV", considerations "(E. 4.3)". FR: "art. 6 al. 2 let. g LAA", "art. 39 LAA, 50 OLAA", "(consid. 4.3)". Only the statute abbreviations of the text's language (UVG, UVV, ATSG, IVG, BGG / LAA, OLAA, LPGA, LAI, LTF). Do not cite BGE/ATF numbers or other rulings; state the rule instead.
7. **Numbers and dates.** Amounts in Swiss format in both languages: "CHF 7'770.-", "CHF 16'751.65". Percentages with a space: "20 %". Dates only when they matter legally (deadlines, start or end of benefits, revision request): "am 1. Juni 2022" / "le 1er juin 2022".
8. **Leave out.** Costs and party compensation, admissibility boilerplate, arguments the court did not need to answer, medical history beyond the diagnoses that matter, the cantonal court's reasoning (keep only its result), quotations of earlier case law.

## 2. The corpus

| | |
|---|---|
| Examples | 55 summaries, each with a German and a French text, rulings dated 9 July 2025 to 27 March 2026 |
| Divisions | 8C: 51, 9C: 3, 4A: 1 |
| Language of the ruling | German 22, French 31, Italian 2 (from the heading: "BGer-Urteil", "Arrêt du TF", "Sentenza del TF") |
| Authors | FRT (Rechtsanwalt): 38, German and French rulings. LC4 (Avocat): 14, French and Italian rulings. VIL (Rechtsanwältin, Bereichsleiterin): 3, French rulings |
| In the relevance list | 32 examples; the other 23 are rulings from Q3 2025, outside the listed period |

The heading of each example names the ruling in its own language ("BGer-Urteil 8C_78/2025 vom 16. Dezember 2025", "Arrêt du TF 8C_356/2025 du 17 décembre 2025", "Sentenza del TF 9C_65/2025 del 29 gennaio 2026, destinata alla pubblicazione negli DTF"). The summary in the ruling's language is the author's original; the other text is a translation of it, often with artefacts (section 7). The scorer therefore marks references in the ruling's language as `orig`.

### Length

| | Words median (IQR) | Range | Sentences median (IQR) | Words per sentence | Paragraphs median (max) |
|---|---|---|---|---|---|
| German | 179 (101-242) | 8-673 | 8 (5-11) | 22 | 3 (8) |
| French | 226 (129-287) | 11-691 | 8 (5-11) | 28 | 3 (8) |

| Group | n | German words median | French words median |
|---|---|---|---|
| Author FRT | 38 | 159 | 197 |
| Author LC4 | 14 | 216 | 240 |
| Author VIL | 3 | 283 | 287 |
| German-language rulings | 22 | 142 | 179 |
| French-language rulings | 31 | 215 | 246 |

French texts are longer than their German counterparts in 52 of 55 pairs (median ratio 1.19, IQR 1.11-1.30), with fewer but longer sentences.

## 3. Structure

Four formats occur; the split file labels every example (`data/eval/split.json`, field `format`).

| Format | n | Shape | Typical author | Examples |
|---|---|---|---|---|
| holding | 22 | Leitsatz style: the legal principle(s) stated as general rules, sometimes a short "In casu" application, no facts paragraph | FRT | 8C_313/2024, 8C_366/2024, 8C_687/2024, 8C_458/2025 |
| facts-holding | 16 | One short facts paragraph (injury, Suva decision, cantonal result), then the holdings, sometimes the outcome | FRT | 8C_656/2024, 8C_78/2025, 8C_275/2025, 8C_334/2025 |
| narrative | 11 | Facts, procedure, "Le Tribunal fédéral a rappelé ...", "Dans le cas particulier ...", "En définitive, le Tribunal fédéral a rejeté le recours", past tense, considerations cited | LC4, VIL (mostly 2025) | 8C_7/2025, 8C_172/2025, 8C_176/2025, 8C_318/2025 |
| compact | 6 | Four blocks: facts, principles with considerations, "En l'espèce ...", one-sentence outcome, present tense | LC4, VIL (2026) | 8C_223/2025, 8C_314/2025, 8C_508/2025, 8C_525/2025, 8C_613/2025 |

What comes first: about half of the summaries open with the facts, the other half with the legal principle. 22 of 55 state the outcome explicitly: 12 of the 17 narrative and compact summaries, 3 of the 22 holding summaries. All 17 summaries by LC4 and VIL cite considerations ("consid. 5.2" / "E. 5.2"); FRT cites them in one of 38.

The recommended structure (style card, item 3) is the compact format: it is the most recent one (six of the seven 2026 summaries by LC4 and VIL use it), it contains the facts-holding format of FRT as a special case, and it makes the outcome and the source considerations explicit.

## 4. Language conventions

### 4.1 Tense and voice

| | German | French |
|---|---|---|
| Facts and earlier decisions | Präteritum: "Der Versicherte erlitt ...", "Die Suva stellte die Leistungen ein", "was das kantonale Gericht bestätigte" | passé composé, plus-que-parfait for what happened before: "L'assuré a subi ...", "La Suva a mis fin aux prestations", "ce qui a été confirmé par le tribunal cantonal" |
| Legal principles | Präsens, often passive or impersonal: "ist ... zu berücksichtigen", "Es ist nicht Sache des Arztes, ..." | présent: "doit être pris en compte", "Il n'appartient pas au médecin de ..." |
| What the court does | Präsens: "Das Bundesgericht erinnert daran / hält fest / bestätigt / lässt offen" | présent: "Le Tribunal fédéral rappelle / constate / confirme / laisse ouverte la question" |
| Outcome | Präsens passiv: "Die Beschwerde wird abgewiesen." | présent passif: "Le recours est rejeté." |

The 2025 narrative summaries tell the court's reasoning in the past ("a rappelé", "ont considéré"; "erinnerte", "stellten fest"). This is acceptable but should not be mixed with the present-tense style in one summary.

### 4.2 Citations

| | German | French |
|---|---|---|
| Article | Art. 6 Abs. 2 Bst. g UVG | art. 6 al. 2 let. g LAA ("Art." only at the start of a sentence) |
| Several acts | Art. 39 UVG, 50 UVV | art. 39 LAA, 50 OLAA |
| Several letters | Art. 61 lit. a und fbis ATSG | les art. 61 let. a et fbis LPGA |
| Conventions | Art. 6 Ziff. 1 EMRK | art. 6 par. 1 CEDH |
| Considerations | (E. 4.3), (E. 3.1 bis 3.3), (E. 4.3.2 und 4.3.3) | (consid. 4.3), (consid. 3.1 à 3.3), (consid. 4.3.2 et 4.3.3) |

The German examples use both "Bst." (FRT's German originals) and "lit." (translations from French); "Bst." is the official spelling of the Swiss classified compilation and is recommended, "lit." is acceptable. For considerations the examples use "E." (9 examples), "Erw." (8) and "Erwägung" (4); "E." is the Federal Court's own abbreviation and is used by every 2026 example that cites considerations. French always uses "consid.".

### 4.3 Recurring phrasings

| German | French |
|---|---|
| Der Versicherte erlitt eine Distorsion des linken oberen Sprunggelenks. | L'assuré a subi une distorsion de l'articulation tibio-tarsienne gauche. |
| Die Suva stellte die Versicherungsleistungen per 29. Oktober 2022 ein. | La Suva a mis fin aux prestations d'assurance avec effet au 29 octobre 2022. |
| Die Suva verneinte einen Anspruch auf eine Invalidenrente und sprach eine Integritätsentschädigung von 20 % zu. | La Suva a nié le droit à une rente d'invalidité et octroyé une indemnité pour atteinte à l'intégrité de 20 %. |
| ..., was das kantonale Gericht bestätigte. | ..., ce qui a été confirmé par le tribunal cantonal. |
| Auf Beschwerde des Versicherten hin ... | Sur recours de l'assuré, ... / Saisi d'un recours de l'assuré, ... |
| Die Suva erhob Beschwerde beim Bundesgericht. | La Suva a recouru au Tribunal fédéral. |
| Das Bundesgericht erinnert daran, dass ... | Le Tribunal fédéral rappelle que ... |
| Gemäss Rechtsprechung ... | Selon la jurisprudence, ... |
| Im vorliegenden Fall / Im konkreten Fall / In casu ... | En l'espèce / Dans le cas particulier ... |
| Es ist auf die Beurteilung des Suvaarztes abzustellen. | Il convient de se fonder sur l'appréciation du médecin de la Suva. |
| Die Vorinstanz hat kein Bundesrecht verletzt, als sie ... | L'instance inférieure n'a pas violé le droit fédéral en ... |
| Diese Frage lässt das Bundesgericht offen. | Le Tribunal fédéral ne tranche pas cette question. |
| Mit anderen Worten ... | En clair, ... / Autrement dit, ... |
| mit überwiegender Wahrscheinlichkeit | au degré de la vraisemblance prépondérante |

### 4.4 Openings

The first sentence carries the case in a nutshell. Facts-first openings take the insured person or the insurer as subject ("Der Versicherte erlitt ...", "Ein Versicherter, der an ... leidet, beantragte ...", "Die Suva sprach ... zu"; "L'assuré a subi ...", "Un assuré souffrant de ... a sollicité ...", "La Suva a accordé ..."). Principle-first openings state the rule ("Die Liste der unfallähnlichen Körperschädigungen in Art. 6 Abs. 2 UVG ist abschliessend." / "La liste des lésions corporelles assimilées à un accident, énumérées à l'art. 6 al. 2 LAA, est exhaustive."). Do not open with the docket, the date, the court or "In diesem Urteil" / "Dans cet arrêt": the heading already carries them.

### 4.5 Outcome formulas

| Result | German | French |
|---|---|---|
| Appeal of the insured dismissed | Die Beschwerde des Versicherten wird abgewiesen. | Le recours de l'assuré est rejeté. |
| Appeal of Suva upheld | Die Beschwerde der Suva wird gutgeheissen und der Einspracheentscheid bestätigt. | Le recours de la Suva est admis et la décision sur opposition confirmée. |
| Partly upheld, remitted | Die Beschwerde wird teilweise gutgeheissen und die Sache zur ergänzenden Abklärung und neuen Entscheidung an die Suva zurückgewiesen. | Le recours est partiellement admis et la cause renvoyée à la Suva pour instruction complémentaire et nouvelle décision. |
| Remitted to the cantonal court | Die Sache wird zur neuen Entscheidung an die Vorinstanz zurückgewiesen. | La cause est renvoyée à l'instance inférieure pour nouvelle décision. |
| Manifestly unfounded | Die Beschwerde wird als offensichtlich unbegründet abgewiesen. | Le recours est rejeté comme manifestement non fondé. |
| Specific result | Die Beschwerde der Suva wird gutgeheissen; der Erlass wird verweigert. | Le recours de la Suva est admis; la remise est refusée. |

### 4.6 Notes after the outcome

FRT adds a last line when the ruling has special weight: "Fünfer-Entscheid." / "Décision à cinq." (8C_626/2024, 8C_687/2024) and "Fünfer-Entscheid, zur Publikation vorgesehen." / "Décision à cinq, prévue pour publication." (8C_458/2025). Add these only when the ruling states the five-judge panel or the intended publication. Personal remarks ("Anmerkung:" / "Remarque:", "cavete collegae:") appear in four FRT summaries, for example that a question is open for accident insurance (9C_382/2025). A generated summary should add an "Anmerkung" only when the ruling itself leaves a question open that matters for accident insurance practice or applies old law.

## 5. What the summaries leave out

None of the 55 examples mentions party names (the rulings are anonymised; insurers other than Suva are named once, SWICA in 8C_626/2024), lawyers, judges, the composition of the court (except "Fünfer-Entscheid"), court costs or party compensation (except where they are the legal issue, 9C_65/2025), BGE/ATF citations or other precedents by number, or the cantonal docket. Admissibility is mentioned only when it is the issue (8C_318/2025, 8C_351/2025). Medical findings are reduced to the diagnoses that matter for the legal question. The cantonal court appears only with its result ("was das kantonale Gericht bestätigte"). Exact dates are rare except in procedural cases about deadlines.

## 6. Where the authors differ, and the single recommended style

| Aspect | FRT | LC4 / VIL | Recommendation | Rationale |
|---|---|---|---|---|
| Length (DE median) | 159 words | 216 / 283 words | 120-250, about 180 | Close to the overall median; FRT writes the German originals that most likely make up the hidden hold-out (section 9.5) |
| Structure | holding or short facts + holding | narrative (2025), compact (2026) | compact four blocks | Contains both; explicit outcome and sources |
| Facts | one or two sentences or none | a full paragraph, sometimes with dates and accident details (8C_176/2025) | one to three sentences | Facts only serve to understand the holding |
| Considerations | almost never | always | cite for the key holdings | Lets a lawyer check the statement in the ruling |
| Tense of the court's reasoning | present | past (2025), present (2026) | present | Consistent with the rules being stated as current law |
| Outcome | usually omitted in holding summaries | always | always, one sentence | The reader must see who won; costs about ten words |
| DE letter citation | Bst. | lit. | Bst. | Official spelling, used in the German originals |
| Remarks | "Anmerkung", "cavete collegae", "In casu" | none | Fünfer/publication flag; "Anmerkung" only when grounded in the ruling; no Latin flourishes except "in casu" | Generated text must not invent practice comments |

## 7. German and French: two originals, not a translation

In the examples the second language is the author's translation of the first, and it shows. The generated pair should avoid these artefacts, which all occur in the corpus:

- French statute abbreviation in a German text: "Art. 73 lit. b OLAA" (8C_129/2025, should be UVV); "ESS" instead of "LSE" (8C_178/2025).
- Non-standard German terms: "Einspruch" / "Einspruchsfrist" (8C_318/2025, should be Einsprache), "Einkommen ohne Invalidität" and "Einkommen mit Invalidität" (8C_7/2025, should be Valideneinkommen and Invalideneinkommen), "Invaliditätsrente" (8C_356/2025, 8C_399/2025, should be Invalidenrente), "Tagegeld" (8C_178/2025, should be Taggeld), "vom Cour de justice des Kantons Genf" (8C_223/2025).
- Wrong outcome verb: "wies die Beschwerde der Suva zurück" (8C_172/2025) where the French says "a rejeté": a dismissed appeal is "abgewiesen"; "zurückweisen" means remittal.
- Meaning inverted in translation: 8C_498/2024 renders "Es tut dem Beweiswert eines Gutachtens keinen Abbruch, wenn dessen Text nicht wortwörtlich der Tonaufnahme entspricht" as "la valeur probante d'une expertise ne correspond pas littéralement aux enregistrements sonores".
- French form errors: "assureur accident" without hyphen (8C_399/2025, should be assureur-accidents).

Recommended generation order: write the summary in the ruling's language first, directly from the ruling, reusing the court's own wording where it is precise. Then write the other language from the ruling and the first summary, with the instruction to write natively and the glossary in the prompt. Finally check both texts automatically for foreign statute abbreviations, avoid-list terms and citation format (`suva.eval.metrics.foreign_statutes`, `glossary_usage`, `citation_issues`).

Each summary also has a heading in the language of the ruling, which the UI can generate from the metadata: "BGer-Urteil 8C_78/2025 vom 16. Dezember 2025", "Arrêt du TF 8C_356/2025 du 17 décembre 2025", "Sentenza del TF 9C_65/2025 del 29 gennaio 2026", followed by ", zur Publikation vorgesehen" / ", destiné à la publication" / ", destinata alla pubblicazione" when the ruling is a leading case.

## 8. Terminology glossary

Built from the aligned examples; the machine-readable version with matching variants is `data/eval/glossary.json`. `n` counts the examples whose German text uses the German term and whose French text uses the French term (refresh with `python -m suva.eval.glossary`). Forms in brackets are accepted variants; "avoid" lists forms seen in the examples that should not be used.

**Parties and institutions**

| Deutsch | Français | n | avoid |
|---|---|---|---|
| der Versicherte (Versicherte, versicherte Person) | l'assuré (assuré, personne assurée) | 42 |  |
| Bundesgericht (Bundesrichter) | Tribunal fédéral (juges fédéraux) | 21 |  |
| kantonales Gericht (kantonale Gericht, Kantonsgericht) | tribunal cantonal (juridiction cantonale, Cour cantonale) | 17 |  |
| Suvaarzt (suvaärztlich, Suva-Arzt, Suva-Ärzt) | médecin de la Suva (médecin Suva, médecins Suva, médecins de la Suva) | 8 |  |
| Invalidenversicherung (IV) | assurance-invalidité (AI) | 7 |  |
| Vorinstanz | instance inférieure (autorité précédente, premiers juges) | 7 |  |
| Unfallversicherer | assureur-accidents (assureur-accident) | 6 | FR: assureur accident |
| Beschwerdeführer | recourant | 6 |  |
| IV-Stelle | office AI | 3 |  |
| Versicherungsmedizin | médecine d'assurance | 3 |  |
| Beschwerdegegner | intimé | 3 |  |
| Unfallversicherung | assurance-accidents | 2 |  |
| behandelnder Arzt (behandelnde Arzt, behandelnden Arzt) | médecin traitant | 2 |  |
| Ersatzkasse | caisse supplétive | 1 |  |
| MEDAS | COMAI | 1 |  |
| RAD | SMR | 1 |  |

**Procedure and outcome**

| Deutsch | Français | n | avoid |
|---|---|---|---|
| Beschwerde | recours | 25 |  |
| Einsprache | opposition | 11 | DE: Einspruch |
| Einspracheentscheid (Einsprache-Entscheid) | décision sur opposition | 8 |  |
| abgewiesen | rejeté (rejette) | 8 |  |
| gutgeheissen | admis | 6 |  |
| zurückgewiesen (Rückweisung, zurückverwiesen, zurückzuweisen) | renvoyé (renvoi) | 6 |  |
| Verfügung | décision | 4 |  |
| rechtskräftig | entrée en force (entré en force, passée en force, passé en force) | 3 |  |
| Fünfer-Entscheid | décision à cinq | 3 |  |
| Beschwerde in öffentlich-rechtlichen Angelegenheiten | recours en matière de droit public | 2 |  |
| prozessuale Revision | révision procédurale | 2 |  |
| Anmerkung | Remarque | 2 |  |
| Vorbescheidverfahren | procédure de préavis | 1 |  |
| rechtliches Gehör (rechtliche Gehör) | droit d'être entendu | 1 |  |
| Begründungspflicht | obligation de motiver (obligation de motivation) | 1 |  |
| Zwischenverfügung (Zwischenentscheid) | décision incidente | 1 |  |
| nicht wieder gutzumachender Nachteil (nicht wieder gutzumachenden Nachteil) | préjudice irréparable | 1 |  |
| Rechtsverweigerung | déni de justice | 1 |  |
| Akteneinsicht | consultation du dossier (accès au dossier) | 1 |  |
| zur Publikation vorgesehen | prévue pour publication | 1 |  |

**Evidence and review**

| Deutsch | Français | n | avoid |
|---|---|---|---|
| Gutachten | expertise | 11 |  |
| überwiegende Wahrscheinlichkeit (überwiegend wahrscheinlich, überwiegender Wahrscheinlichkeit, überwiegenden Wahrscheinlichkeit) | vraisemblance prépondérante | 5 |  |
| Beweiswert (beweiswertig) | valeur probante | 3 |  |
| Gerichtsgutachten (gerichtliche Gutachten, gerichtliches Gutachten) | expertise judiciaire | 3 |  |
| Rechtsfrage | question de droit (questions de droit, relève du droit) | 3 |  |
| Bundesrecht | droit fédéral | 3 |  |
| Schadenminderungspflicht (Schadenminderung) | obligation de réduire le dommage (réduction du dommage) | 3 |  |
| Privatgutachten (Privatgutachter) | expertise privée (expert privé) | 2 |  |
| Willkür (willkürlich) | arbitraire | 2 |  |
| freie Beweiswürdigung (freien Beweiswürdigung) | libre appréciation des preuves | 1 |  |
| Tatfrage | question de fait (questions de fait) | 1 |  |
| Treu und Glauben | bonne foi | 1 |  |

**Benefits**

| Deutsch | Français | n | avoid |
|---|---|---|---|
| Invalidenrente | rente d'invalidité | 8 | DE: Invaliditätsrente |
| Integritätsentschädigung | indemnité pour atteinte à l'intégrité | 5 |  |
| Versicherungsleistungen | prestations d'assurance | 4 |  |
| Taggeld | indemnité journalière (indemnités journalières) | 3 | DE: Tagegeld |
| Leistungspflicht | obligation d'allouer des prestations | 2 |  |
| Integritätsschaden | atteinte à l'intégrité | 2 |  |
| Hilflosenentschädigung | allocation pour impotent | 2 |  |
| Hilflosigkeit | impotence | 2 |  |
| alltägliche Lebensverrichtung (Lebensverrichtung) | acte ordinaire de la vie (actes ordinaires de la vie, acte de la vie, actes de la vie) | 2 |  |
| Hilfsmittel | moyens auxiliaires (moyen auxiliaire) | 2 |  |
| versicherter Verdienst (versicherte Verdienst, versicherten Verdienst, versicherte Jahresverdienst, versicherter Jahresverdienst) | gain assuré (gain annuel assuré) | 2 |  |
| Rückerstattung | restitution | 2 |  |
| grobe Fahrlässigkeit | négligence grave | 2 |  |
| Heilbehandlung | traitement | 1 |  |
| dauernde persönliche Überwachung | surveillance personnelle permanente | 1 |  |
| Hilfe und Pflege zu Hause (Hauspflege) | aide et soins à domicile (soins à domicile) | 1 |  |
| Geldleistungen (Barleistungen) | prestations en espèces | 1 |  |
| Erlass | remise | 1 |  |
| guter Glaube (guten Glauben) | bonne foi | 1 |  |
| Wagnis | entreprise téméraire (entreprises téméraires) | 1 |  |
| Nichtberufsunfall (Nichtberufsunfälle) | accident non professionnel (accidents non professionnels) | 1 |  |

**Accident and causation**

| Deutsch | Français | n | avoid |
|---|---|---|---|
| adäquater Kausalzusammenhang (adäquate Kausalzusammenhang, adäquaten Kausalzusammenhang, adäquate Kausalität, adäquaten Kausalität) | lien de causalité adéquate (causalité adéquate) | 4 |  |
| mittelschwerer Unfall (mittelschwer, mittleren Bereich) | gravité moyenne (catégorie moyenne) | 4 |  |
| psychische Störungen (psychische Beschwerden, psychischen Beschwerden, psychischen Störung) | troubles psychiques | 4 |  |
| Schädel-Hirn-Trauma | traumatisme crânio-cérébral (traumatisme cranio-cérébral) | 3 |  |
| unfallähnliche Körperschädigung (unfallähnlichen Körperschädigung) | lésion corporelle assimilée à un accident (lésions corporelles assimilées à un accident) | 2 |  |
| Listenverletzung | lésion figurant sur la liste (lésions figurant sur la liste, lésion de la liste, lésion répertoriée à la liste) | 2 |  |
| Abnützung (Abnutzung) | usure | 2 |  |
| natürlicher Kausalzusammenhang (natürliche Kausalzusammenhang, natürlichem Kausalzusammenhang) | lien de causalité naturelle | 2 |  |
| Status quo sine vel ante | statu quo sine vel ante | 2 |  |
| Schleudertrauma | coup du lapin (traumatismes de la colonne cervicale) | 2 |  |
| Unfallbegriff | notion d'accident | 1 |  |
| ungewöhnliche äussere Einwirkung | facteur extérieur de caractère extraordinaire | 1 |  |
| Vorzustand | état préexistant | 1 |  |
| richtunggebende Verschlimmerung (richtunggebenden Verschlimmerung) | aggravation déterminante | 1 |  |
| Berufskrankheit | maladie professionnelle | 1 |  |
| Rückfall | rechute | 1 |  |
| Spätfolgen | séquelles tardives | 1 |  |

**Work capacity**

| Deutsch | Français | n | avoid |
|---|---|---|---|
| zumutbar (Zumutbarkeit) | exigible (exigibilité) | 9 |  |
| Arbeitsfähigkeit | capacité de travail | 8 |  |
| Arbeitsunfähigkeit (arbeitsunfähig) | incapacité de travail | 6 |  |
| angepasste Tätigkeit (angepassten Tätigkeit, leidensangepasste Tätigkeit) | activité adaptée | 5 |  |
| medizinisch-theoretisch | médico-théorique | 3 |  |
| Belastungsprofil (Zumutbarkeitsprofil) | profil des contraintes (profil d'exigibilité) | 2 |  |
| Stabilisierung des Gesundheitszustandes (Stabilisierung seines Gesundheitszustands) | stabilisation de l'état de santé | 2 |  |
| Erwerbsunfähigkeit | incapacité de gain | 1 |  |

**Income comparison and revision**

| Deutsch | Français | n | avoid |
|---|---|---|---|
| Invalideneinkommen | revenu d'invalide (revenu avec invalidité) | 5 | DE: Einkommen mit Invalidität |
| LSE | ESS | 4 |  |
| Kompetenzniveau | niveau de compétence (niveau de compétences) | 4 |  |
| Rentenrevision (Revision der Rente) | révision de la rente (révision de rente) | 4 |  |
| Valideneinkommen | revenu sans invalidité (revenu de valide) | 3 | DE: Einkommen ohne Invalidität |
| GAV | CCT | 3 |  |
| Invaliditätsgrad | degré d'invalidité (taux d'invalidité) | 2 |  |
| Verwertbarkeit | exploitabilité (exploiter la capacité) | 2 |  |
| Revisionsgrund | motif de révision | 2 |  |
| Einkommensvergleich | comparaison des revenus | 1 |  |
| Tabellenlohn | salaire statistique | 1 |  |
| ausgeglichener Arbeitsmarkt (ausgeglichenen Arbeitsmarkt, ausgeglichene Arbeitsmarkt) | marché du travail équilibré | 1 |  |
| Abzug | déduction (abattement) | 1 |  |
| Soziallohn | salaire social | 1 |  |
| Leistungsminderung | baisse de rendement | 1 |  |
| Nominallohnentwicklung | évolution du salaire nominal (évolution des salaires nominaux) | 1 |  |

**Coverage and premiums**

| Deutsch | Français | n | avoid |
|---|---|---|---|
| Unterstellung | assujettissement | 1 |  |
| Prämien | primes | 1 |  |
| obligatorische Versicherung (obligatorische Versicherungsschutz) | assurance obligatoire (assuré obligatoirement) | 1 |  |

**Statutes** (abbreviation, then the name in each language; n = examples citing the act in both texts)

| DE | FR | Name (DE) | Nom (FR) | n |
|---|---|---|---|---|
| UVG | LAA | Bundesgesetz über die Unfallversicherung | Loi fédérale sur l'assurance-accidents | 9 |
| UVV | OLAA | Verordnung über die Unfallversicherung | Ordonnance sur l'assurance-accidents | 5 |
| ATSG | LPGA | Bundesgesetz über den Allgemeinen Teil des Sozialversicherungsrechts | Loi fédérale sur la partie générale du droit des assurances sociales | 12 |
| ATSV | OPGA | Verordnung über den Allgemeinen Teil des Sozialversicherungsrechts | Ordonnance sur la partie générale du droit des assurances sociales | 1 |
| IVG | LAI | Bundesgesetz über die Invalidenversicherung | Loi fédérale sur l'assurance-invalidité | 0 |
| IVV | RAI | Verordnung über die Invalidenversicherung | Règlement sur l'assurance-invalidité | 1 |
| BGG | LTF | Bundesgerichtsgesetz | Loi sur le Tribunal fédéral | 2 |
| VVG | LCA | Versicherungsvertragsgesetz | Loi sur le contrat d'assurance | 1 |
| KVG | LAMal | Bundesgesetz über die Krankenversicherung | Loi fédérale sur l'assurance-maladie | 0 |
| KLV | OPAS | Krankenpflege-Leistungsverordnung | Ordonnance sur les prestations de l'assurance des soins | 1 |
| AHVG | LAVS | Bundesgesetz über die Alters- und Hinterlassenenversicherung | Loi fédérale sur l'assurance-vieillesse et survivants | 0 |
| BVG | LPP | Bundesgesetz über die berufliche Vorsorge | Loi fédérale sur la prévoyance professionnelle | 0 |
| MVG | LAM | Bundesgesetz über die Militärversicherung | Loi fédérale sur l'assurance militaire | 0 |
| AVIG | LACI | Arbeitslosenversicherungsgesetz | Loi sur l'assurance-chômage | 0 |
| VG | LRCF | Verantwortlichkeitsgesetz | Loi sur la responsabilité | 1 |
| EMRK | CEDH | Europäische Menschenrechtskonvention | Convention européenne des droits de l'homme | 1 |
| BV | Cst. | Bundesverfassung | Constitution fédérale | 0 |

## 9. What makes a ruling relevant to Suva

### 9.1 The labelled period

The xlsx lists 60 decisions for 2025 Q4 (28) and 2026 Q1 (32). The quarter is that of the ruling date, not of the summary: summaries were created 17 to 138 days (median 34) after the ruling, and docket years range from 2023 to 2026. 53 are 8C rulings, 6 are 9C rulings (9C_65/2025, 9C_145/2025, 9C_311/2025, 9C_382/2025, 9C_690/2024, 9C_699/2024), and one is a cantonal decision (Kantonsgericht Basel-Landschaft, 5 February 2026). That is about ten relevant rulings per month. By language of the ruling: 41 German including the cantonal decision, 18 French, 1 Italian. The language inferred from the wording of Suva's page titles (field `ruling_lang`) matches the fetched corpus for 58 of the 59 Federal Court rulings; 9C_690/2024 has a German page title but is a French ruling. Every other ruling of the period is, per the challenge, not relevant.

### 9.2 Base rates in the fetched corpus

The fetched corpus (`data/corpus/rulings.jsonl.gz`) holds 3,934 Federal Court rulings decided in the period, including all 59 listed Federal Court rulings. Every relevant ruling is an 8C or 9C ruling whose subject (corpus field `title`, for example "Unfallversicherung (Invalidenrente)") is accident or invalidity insurance:

| Subject, rulings decided 1 October 2025 to 31 March 2026 | Rulings | Relevant | Share |
|---|---|---|---|
| Accident insurance (Unfallversicherung, Assurance-accidents) | 91 | 43 | 47 % |
| Invalidity insurance (Invalidenversicherung, Assurance-invalidité, Assicurazione per l'invalidità) | 198 | 16 | 8 % |
| Other subjects of 8C and 9C (unemployment insurance, social assistance, supplementary benefits, health insurance, AHV, occupational pensions, taxes) | 404 | 0 | 0 % |
| All other divisions | 3,241 | 0 | 0 % |

Within the 91 accident insurance rulings, short rulings (under 12,000 characters) are rarely relevant (7 of 37, against 36 of the 54 longer ones), and neither are inadmissibility decisions (2 of 20); rulings in which the appeal is at least partly upheld are relevant more often (15 of 24). Whether Suva or another accident insurer is the party makes no difference: Suva is named at the start of 60 of them, 28 relevant (47 %), against 15 of the other 31 (48 %).

### 9.3 Evidence from the examples

| Topic (primary legal issue) | n | Examples |
|---|---|---|
| Income comparison: Valideneinkommen, Invalideneinkommen, LSE tables, Kompetenzniveau, deductions, Verwertbarkeit, Soziallohn | 10 | 8C_656/2024, 8C_676/2024, 8C_7/2025, 8C_330/2025, 9C_382/2025 |
| Procedure: Einsprache, deadlines, right to be heard, public hearing, standing, denial of justice | 9 | 8C_318/2025, 8C_351/2025, 8C_455/2025, 9C_65/2025 |
| Adequate causation (psychological and whiplash case law) | 5 | 8C_498/2024, 8C_72/2025, 8C_311/2025, 8C_348/2025 |
| Natural causation, status quo sine, weight of insurance doctors' reports | 5 | 8C_62/2025, 8C_172/2025, 8C_275/2025, 8C_334/2025 |
| Pension revision (Art. 17 and 53 ATSG) | 4 | 8C_313/2024, 8C_687/2024, 8C_223/2025, 8C_525/2025 |
| Injuries on the list of Art. 6 Abs. 2 UVG | 4 | 8C_366/2024, 8C_78/2025, 8C_177/2025, 8C_224/2025 |
| Helplessness and care at home | 4 | 8C_626/2024, 8C_185/2025, 8C_314/2025, 8C_531/2025 |
| Daily allowance, insured earnings, benefit reductions (Wagnis, detention) | 3 | 8C_176/2025, 8C_178/2025, 8C_399/2025 |
| Expert opinions and observation | 3 | 8C_241/2025, 8C_450/2025, 9C_581/2024 |
| Notion of accident, suicide | 2 | 8C_180/2025, 8C_517/2024 |
| Insurer assignment (Suva competence, Ersatzkasse) | 2 | 8C_129/2025, 8C_458/2025 |
| Occupational disease, insurer liability, integrity compensation, repayment and waiver | 1 each | 8C_21/2025, 8C_184/2025, 8C_508/2025, 8C_613/2025 |

Branch of insurance as identifiable from the summary: accident insurance 37, invalidity insurance 7, private insurance (VVG daily sickness allowance, 4A_106/2025) 1, not identifiable 10. Suva is named in 20 of the 55 German texts, the generic "Unfallversicherer" appears in 8, invalidity insurance in 7. Statutes cited in both languages: ATSG/LPGA in 12 examples, UVG/LAA in 9, UVV/OLAA in 5, BGG/LTF in 2, single citations of ATSV, IVV, VVG, KLV, VG and EMRK.

Relevance does not depend on the outcome: Suva lost or had to investigate further in several examples (8C_7/2025, 8C_62/2025, 8C_172/2025, 8C_177/2025). It does not require a new principle either: 8C_275/2025 was dismissed as manifestly unfounded and is still listed.

### 9.4 Signals for the triage

- **Subject accident insurance** (8C; "Unfallversicherung", "Assurance-accidents", "Assicurazione contro gli infortuni"; UVG/UVV, LAA/OLAA, LAINF/OAINF cited): about every second ruling is relevant, and these are 43 of the 59 relevant rulings. Rank within this group by substance: a full judgment with a stated or clarified legal principle ranks above a short ruling, a decision in the simplified procedure (Art. 108/109 BGG) or an inadmissibility decision; an appeal that is upheld or remitted ranks higher than a dismissal. Suva as a party is not a separate signal inside this group, but the explanation should name the insurer. Suva keywords: "Suva", "SUVA", "Schweizerische Unfallversicherungsanstalt", "Caisse nationale suisse d'assurance en cas d'accidents", "CNA", "Istituto nazionale svizzero di assicurazione contro gli infortuni", "INSAI".
- **Subject invalidity insurance** (8C and 9C): about one in twelve is relevant. Look for rules that also govern accident insurance: the general part of social insurance law (ATSG/LPGA): expert opinions (Art. 44 ATSG, MEDAS), the weight of medical reports, observation (Art. 43a ATSG), objection procedure (Art. 52 ATSG), revision (Art. 17 and 53 ATSG), repayment and waiver (Art. 25 ATSG), duty to advise and liability (Art. 27 and 78 ATSG), delay (Art. 56 ATSG), standing; and concepts shared with accident insurance: income comparison and LSE tables, Kompetenzniveau, deductions, Soziallohn, Verwertbarkeit, helplessness.
- **Everything else**: not relevant in the period (0 of 3,645). The examples contain one private insurance ruling (4A_106/2025) and the list one cantonal decision; such exceptions cannot be found by rule and should not drive the triage design.
- **Weight boosters**: a five-judge panel ("in Fünferbesetzung"), intended publication ("zur Publikation vorgesehen", BGE/ATF/DTF), an explicit clarification or change of case law, Federal Court procedure that trips up practitioners (deadline standstill, 8C_455/2025).

A good triage explanation names the branch, the insurer's role and the legal point, for example: "Unfallversicherung (UVG), Suva ist Beschwerdegegnerin; Grundsatz zur Listenverletzung nach Art. 6 Abs. 2 UVG bei vorbestehender Abnützung; Fünfer-Entscheid."

### 9.5 Implications for the evaluation

17 of the 18 French-language rulings of the list have an example summary. Of the 28 listed decisions without an example, 27 are German-language (26 Federal Court rulings and the Basel-Landschaft decision) and one is French (9C_690/2024). Suva's hidden hold-out is therefore most likely made of German-original summaries in FRT's style. For German-language rulings, optimise the German summary first: compact, principle-oriented, present tense, a one- or two-sentence facts paragraph, Bst. citations, terms from section 8.

## 10. Evaluation set and tools

| File | Content |
|---|---|
| `data/eval/examples.jsonl` | One record per example: docket, ruling date and language, leading-case flag, DE and FR text (paragraphs separated by blank lines), link, author |
| `data/eval/relevant_q4_2025_q1_2026.json` | The 60 listed decisions with quarter, normalised docket, ruling date and language (from the SharePoint page name), creation date and whether an example exists, plus a coverage report |
| `data/eval/split.json` | Hold-out of 10 examples (5 German-, 4 French-, 1 Italian-language rulings, 9 topics, all three authors, all in the listed period), the few-shot pool, recommended few-shot examples per ruling language, and topic/format/branch labels for all 55 |
| `data/eval/glossary.json` | The glossary of section 8, statutes and citation patterns |

Commands:

```sh
uv run python -m suva.eval.examples          # re-parse the HTML examples and the xlsx
uv run python -m suva.eval.glossary          # refresh glossary support counts
uv run python -m suva.eval.score_summaries generated.jsonl [--all] [--judge] [--out report.md]
uv run python -m suva.eval.score_triage triage.jsonl [--threshold 0.5] [--out report.md]
```

`score_summaries` reads rows `{"docket", "lang", "text"}` and reports length ratio, ROUGE-L, chrF, glossary recall (share of the reference's glossary terms the candidate uses) and style issues (avoid-list terms, foreign statute abbreviations, citation format). `--judge` adds a 1-5 rubric (legal accuracy, coverage, style, terminology) from the LLM configured by `LLM_NAME`, `LLM_BASE_URL` and `LLM_API_KEY`, using `src/suva/prompts/judge_summary.md`. `score_triage` reads rows `{"docket", "score"}` (JSONL or CSV) and reports coverage, precision@10/30, recall@30/60, optional threshold metrics, and the relevant rulings outside the top 60.

## 11. Evaluator style: Villa Rebeca (VIL), as generated

The summaries are expected to be judged by Villa Rebeca (VIL, Rechtsanwältin, Bereichsleiterin). Where the authors differ (section 6), the generator follows her, with one deliberate deviation: it is shorter. The operative prompt is `src/suva/prompts/summary_style.md` with the language conventions in `summary_de.md` and `summary_fr.md`.

Her three summaries (8C_7/2025, 8C_172/2025, 8C_613/2025) are French originals of French rulings, 258 to 477 words (French), 4 to 5 paragraphs, with a consideration reference closing almost every paragraph.

| Aspect | VIL | Generated |
|---|---|---|
| Length | 280 words median (French) | 150-200 words German, 160-220 French (captain: "rather shorter"); facts and repetition are cut first, never holdings |
| Paragraph 1 | Facts: insured person and occupation, accident and injury, the insurer's decision with the decisive figures ("CHF 67'071.- (ESS)", "-15%") and dates ("avec effet au 8 juillet 2020") | Same, 1-3 sentences, only figures and dates the dispute turns on; no birth year |
| Paragraph 2 | Cantonal court: "Saisie d'un recours de l'assuré, la Cour de justice genevoise a ...", its result and decisive ground, "(consid. 3.1)" | Same, 1-2 sentences |
| Paragraph 3 (optional) | The appellant's argument: "La Suva a recouru au Tribunal fédéral faisant valoir que ... (consid. 3.2)" | Only when it frames the dispute |
| Federal Court | "Les juges fédéraux ont tout d'abord rappelé la jurisprudence selon laquelle ... (consid. 4.2)" (2025) / "Le Tribunal fédéral rappelle que ... (art. 25 al. 1 LPGA)" (2026), then "En l'espèce, le Tribunal fédéral a considéré que ... (consid. 5.2.1)"; quotes a decisive phrase of the Court in « » | Principles in the present ("rappelle que", "erinnert daran, dass"), application in the past ("a considéré", "erwog"), consideration closing each statement, sub-numbers and ranges ("consid. 3.1 à 3.3", "E. 3.1 bis 3.3") |
| Connectors | "tout d'abord", "Partant de là", "Or", "par ailleurs", "En clair", "Finalement", "Dans ces circonstances" | Same, and German equivalents ("zunächst", "Ausgehend davon", "Indessen", "Zudem", "Mit anderen Worten", "Schliesslich", "Unter diesen Umständen") |
| Outcome | "En définitive, le Tribunal fédéral a rejeté le recours de la Suva." (2025) / "Le recours de la Suva est admis; la remise est refusée." (2026) | "En définitive, le Tribunal fédéral a admis / rejeté le recours de ..." / "Letztlich hiess das Bundesgericht die Beschwerde ... gut / wies ... ab"; built from the operative part and the parties block when the model gets it wrong |
| Lower court | Named ("la Cour de justice genevoise", "le Tribunal cantonal") | Named in French; "das kantonale Gericht" or its German name in German |

Few-shot examples: 8C_7/2025 and 8C_172/2025 come first in every prompt. 8C_613/2025 is in the evaluation hold-out and is never shown. Her German texts are translations with the artefacts of section 7 ("Einkommen ohne Invalidität", "wies die Beschwerde der Suva zurück" for a dismissal, "Erw.3.1"), so German prompts use corrected renderings of her French originals (`src/suva/prompts/style_examples_de.json`). No further example is shown: a third one picked by similarity to the ruling made the model copy its facts (the French summary of 8C_450/2025 took the 3.5 m fall onto a concrete slab from 8C_72/2025); the glossary entries that occur in the ruling carry the terminology instead.
