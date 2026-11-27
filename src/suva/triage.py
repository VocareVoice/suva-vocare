"""Relevance triage of a ruling for Suva.

Stage 1 is a deterministic prior from the docket and the text (subject, division, statutes,
Suva as a party). Rulings below `PRIOR_CUTOFF` are labelled not relevant without an LLM call, and
so are decisions that do not rule on the merits (the gate: inadmissible, struck off, single
judge, no substantive consideration). Stage 2 asks Apertus for a relevance level and an
explanation in German and in French, with the topics of Suva's example summaries as context. The
score blends the level, weighted by its token probabilities, with the prior. Results and metrics:
docs/eval_triage.md.
"""

import json
import math
import re
import sqlite3
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from suva import classify, db
from suva.eval.metrics import contains_term, foreign_statutes, term_forms
from suva.llm import LLMClient, Message, TokenLogprob, parse_json
from suva.segment import clean, segment

PROMPT_VERSION = "v5"
MODEL = "apertus-v1-5-70b"
PREFILTER_MODEL = "prefilter"
GATE_MODEL = "gate"
RELEVANCE_THRESHOLD = 50
PRIOR_CUTOFF = 20
EXCERPT_CHARS = 30_000
# Share of the final score that comes from the keyword prior rather than the LLM.
PRIOR_WEIGHT = 0.3
LANGUAGES = ("de", "fr")
GLOSSARY_TERMS = 25


@dataclass
class TriageResult:
    score: int  # 0-100
    label: Literal["relevant", "not_relevant"]
    reasoning_de: str
    reasoning_fr: str
    model: str | None = None


@dataclass
class Prior:
    score: int  # topical: how closely the ruling concerns accident insurance; filters for the LLM
    substance: int  # adjustment for how much law the ruling states; only used for ranking
    factors: list[str]
    factors_fr: list[str]

    @property
    def ranking(self) -> int:
        return max(0, min(100, self.score + self.substance))


def _pattern(*alternatives: str, flags: int = 0) -> re.Pattern[str]:
    return re.compile("|".join(alternatives), flags)


SUVA = _pattern(
    r"\bSuva\b",
    r"\bSUVA\b",
    r"Schweizerische\s+Unfallversicherungsanstalt",
    r"\bCNA\b",
    r"Caisse\s+nationale\s+suisse\s+d.assurance\s+en\s+cas\s+d.accidents",
    r"\bINSAI\b",
    r"Istituto\s+nazionale\s+svizzero\s+di\s+assicurazione\s+contro\s+gli\s+infortuni",
)
UVG = _pattern(r"\bUVG\b", r"\bUVV\b", r"\bLAA\b", r"\bOLAA\b", r"\bLAINF\b", r"\bOAINF\b")
MVG = _pattern(r"\bMVG\b", r"\bLAM\b", r"Militärversicherung", r"assurance\s+militaire")
ATSG = _pattern(r"\bATSG\b", r"\bLPGA\b")
ACCIDENT_INSURANCE = _pattern(
    r"unfallversicher",
    r"assurance[s]?[- ]accidents",
    r"assureur[s]?[- ]accidents",
    r"assicurazione\s+(?:obbligatoria\s+)?contro\s+gli\s+infortuni",
    r"assicurator[ei]\s+(?:contro\s+gli\s+)?infortuni",
    r"berufskrankheit",
    r"maladie[s]?\s+professionnelle",
    r"malattia\s+professionale",
    r"integritätsentschädigung",
    r"atteinte\s+à\s+l.intégrité",
    r"menomazione\s+dell.integrità",
    flags=re.IGNORECASE,
)
INVALIDITY_INSURANCE = _pattern(
    r"invalidenversicherung",
    r"assurance[- ]invalidité",
    r"assicurazione\s+(?:per|contro)\s+l.invalidità",
    flags=re.IGNORECASE,
)

DIVISION_PRIOR = {"8C": 10, "9C": 5}

_INADMISSIBLE = _pattern(
    r"nicht eingetreten",
    r"abgeschrieben",
    r"n.est pas entré en matière",
    r"irrecevable",
    r"rayée? du rôle",
    r"inammissibile",
    r"non (?:si )?entra nel merito",
    r"stralciat",
)
_SIMPLIFIED = _pattern(
    r"vereinfachten Verfahren",
    r"procédure simplifiée",
    r"procedura semplificata",
    r"erkennt (?:die Präsidentin|der Präsident)",
    r"(?:la Présidente|le Président) prononce",
    r"(?:la|il) President[ea] pronuncia",
)
_PANEL = re.compile(
    r"^(?:Besetzung|Composition|Composizione)\s*\n(.+?)(?:Gerichtsschreiber|Greffi|Cancellier|"
    r"\n\s*(?:Verfahrensbeteiligte|Participants|Parti)\b)",
    re.MULTILINE | re.DOTALL,
)
# Titles and roles around the judges' names in the panel block.
_ROLE = re.compile(
    r"Bundesrichter(?:in(?:nen)?)?|nebenamtliche[rn]?|präsi\w*\s+Mitglied|Präsident(?:in)?|"
    r"Einzelrichter(?:in)?|\bals\b|\bM(?:mes?|M)?\b\.?|\bles?\b|\bla\b|Juges?\s+fédéra\w+|"
    r"Juge\s+présidant\w*|\bJuges?\b|Présidente?|suppléant\w*|juge\s+unique|"
    r"Giudic[ei]\s+federal[ei]|Giudice|President[ea]|supplente|giudice\s+unico",
    re.IGNORECASE,
)
LONG_RULING_CHARS = 12_000
FIVE_JUDGES = 10
# An invalidity insurance appeal by the IV office, the federal office (BSV) or a pension fund.
# Insured persons appear anonymised ("A.________"), so a named appellant is an institution.
INSURER_APPEAL = 15
_APPELLANT = re.compile(
    r"^(?:Verfahrensbeteiligte|Participants à la procédure|Parti)\s*\n(.+?)\n"
    r"(?:gegen|contre|contro)\s*$",
    re.MULTILINE | re.DOTALL,
)
_COUNSEL = re.compile(r"vertreten durch|représentée? par|patrocinat|rappresentat", re.IGNORECASE)

_SUBJECT = re.compile(
    r"^\s*(?:Gegenstand|Objet|Oggetto)\s*\n(.+?)(?:\n\s*(?:Beschwerde|Recours|Ricorso|Revisionsgesuch|"
    r"Demande|Domanda)|\Z)",
    re.MULTILINE | re.DOTALL | re.IGNORECASE,
)


@dataclass
class Sections:
    rubrum: str
    facts: str
    reasons: str
    operative: str


def split_sections(text: str) -> Sections:
    """Split a ruling into rubrum (parties, subject), facts, reasons and operative part."""
    s = segment(text)
    operative = "\n".join(part for part in (s.dispositive, s.signature) if part)
    return Sections(rubrum=s.rubrum, facts=s.facts, reasons=s.reasons, operative=operative)


def subject(text: str) -> str:
    """The "Gegenstand" line of the rubrum, e.g. "Unfallversicherung (Kausalzusammenhang)"."""
    match = _SUBJECT.search(clean(text)[:6000])
    return " ".join(match.group(1).split()).rstrip(",") if match else ""


def panel_size(rubrum: str) -> int | None:
    """Number of judges on the panel: 3, or 5 for questions of principle (Art. 20 BGG)."""
    match = _PANEL.search(rubrum)
    if not match:
        return None
    names = re.split(r",|\n|\bund\b|\bet\b|\be\b|\.", _ROLE.sub(" ", match.group(1)))
    return sum(bool(re.search(r"\w{2}", name)) for name in names)


def insurer_appealed(rubrum: str) -> bool:
    """The appellant of the party block is a named institution, not an anonymised person."""
    match = _APPELLANT.search(rubrum)
    return bool(match) and "____" not in _COUNSEL.split(match.group(1))[0]


def prior(ruling: dict[str, Any]) -> Prior:
    """Cheap relevance prior from docket and text; it decides which rulings reach the LLM."""
    text = ruling.get("text") or ""
    sections = split_sections(text)
    subj = ruling.get("title") or subject(text)
    score, substance, factors, factors_fr = 0, 0, [], []

    def add(points: int, factor: str, factor_fr: str) -> None:
        nonlocal score
        score += points
        factors.append(factor)
        factors_fr.append(factor_fr)

    def weigh(points: int, factor: str, factor_fr: str) -> None:
        nonlocal substance
        substance += points
        factors.append(factor)
        factors_fr.append(factor_fr)

    accident = bool(ACCIDENT_INSURANCE.search(subj) or MVG.search(subj))
    invalidity = not accident and bool(INVALIDITY_INSURANCE.search(subj))
    if accident:
        add(45, f"Gegenstand: {subj}", f"Objet: {subj}")
    elif invalidity:
        add(25, f"Gegenstand: {subj}", f"Objet: {subj}")
    division = (ruling.get("docket") or "")[:2]
    if points := DIVISION_PRIOR.get(division):
        add(points, f"Abteilung {division}", f"cour {division}")
    # Suva or accident insurance in the facts of an invalidity insurance ruling does not make it
    # relevant: none of the 17 such rulings of Q4 2025 and Q1 2026 that name Suva is listed.
    if not invalidity:
        if SUVA.search(sections.rubrum):
            add(15, "Suva ist Partei", "la Suva est partie")
        elif SUVA.search(text):
            add(10, "Suva erwähnt", "Suva mentionnée")
        if uvg := len(UVG.findall(text)):
            add(min(15, 3 + uvg), f"UVG/UVV zitiert ({uvg}x)", f"LAA/OLAA citées ({uvg} fois)")
        if MVG.search(text) and not MVG.search(subj):
            add(10, "Militärversicherung erwähnt", "assurance militaire mentionnée")
        if ACCIDENT_INSURANCE.search(text) and not ACCIDENT_INSURANCE.search(subj):
            add(5, "Unfallversicherung erwähnt", "assurance-accidents mentionnée")
    if ATSG.search(text):
        add(5, "ATSG zitiert", "LPGA citée")

    if _INADMISSIBLE.search(sections.operative[:600]):
        weigh(-20, "Nichteintreten oder Abschreibung", "irrecevabilité ou radiation du rôle")
    elif _SIMPLIFIED.search(text):
        weigh(-15, "vereinfachtes Verfahren", "procédure simplifiée")
    elif classify.outcome(text) in ("upheld", "partly_upheld", "remanded"):
        weigh(5, "Beschwerde (teilweise) gutgeheissen", "recours (partiellement) admis")
    if len(clean(text)) >= LONG_RULING_CHARS:
        weigh(10, "ausführlich begründet", "motivation détaillée")
    if panel_size(sections.rubrum) == 5:
        weigh(FIVE_JUDGES, "Fünferbesetzung", "composition à cinq juges")
    if invalidity and insurer_appealed(sections.rubrum):
        weigh(
            INSURER_APPEAL,
            "Beschwerde der IV-Stelle, des BSV oder einer Vorsorgeeinrichtung",
            "recours de l'office AI, de l'OFAS ou d'une institution de prévoyance",
        )
    return Prior(score=min(score, 100), substance=substance, factors=factors, factors_fr=factors_fr)


def excerpt(text: str, limit: int = EXCERPT_CHARS) -> str:
    """The parts of a ruling that matter for triage, within `limit` characters."""
    text = clean(text)
    if len(text) <= limit:
        return text
    s = split_sections(text)
    rubrum, facts, operative = s.rubrum[:3000], s.facts[:5000], s.operative[:2000]
    room = max(limit - len(rubrum) - len(facts) - len(operative), 4000)
    reasons = s.reasons
    if len(reasons) > room:
        head = int(room * 0.7)
        reasons = f"{reasons[:head]}\n[...]\n{reasons[-(room - head) :]}"
    if len(s.facts) > len(facts):
        facts += "\n[...]"
    return "\n".join(part for part in (rubrum, facts, reasons, operative) if part)


SYSTEM_PROMPT = """\
Du arbeitest im Rechtsdienst der Suva (Schweizerische Unfallversicherungsanstalt). Jedes Quartal \
sichtet ihr alle neuen Urteile des Bundesgerichts und wählt die aus, die für die Suva relevant \
sind; zu diesen schreibt ihr eine Zusammenfassung auf Deutsch und Französisch für die \
Rechtsprechungsübersicht. Pro Quartal sind das etwa 30 von rund 2000 Urteilen.

Relevant sind vor allem:
- Urteile zur obligatorischen Unfallversicherung (UVG/UVV), ob die Suva oder ein anderer \
Unfallversicherer Partei ist, und zur Militärversicherung (MVG), die die Suva führt.
- Urteile, die eine Rechtsfrage klären, eine Praxis bestätigen oder präzisieren oder \
verallgemeinerbare Grundsätze enthalten, z.B. zu Unfallbegriff, natürlichem und adäquatem \
Kausalzusammenhang, Status quo sine, Rückfall, Berufskrankheit, Taggeld, Rente, \
Invaliditätsbemessung (Valideneinkommen, Invalideneinkommen, LSE-Tabellen, Abzüge), \
Integritätsentschädigung, Heilbehandlung, Leistungskürzung, Rückforderung, Beweiswert \
medizinischer Berichte und Gutachten, Unterstellung und Prämien, Verfahren nach ATSG.
- Grundsatzurteile anderer Sozialversicherungen (IV, ATSG, BVG, Krankentaggeld nach VVG) oder \
des Haftpflichtrechts, wenn sie für die Unfallversicherung übertragbar sind (z.B. \
Invalideneinkommen, Schadenminderungspflicht, Regress).

Nicht relevant sind:
- Urteile ohne Bezug zur Unfallversicherung (Strafrecht, Zivilrecht, Steuern, Ausländerrecht, \
IV-Fälle ohne Bedeutung für die UV usw.).
- Nichteintretensentscheide, Abschreibungen und Urteile im vereinfachten Verfahren \
(Art. 108/109 BGG), unentgeltliche Rechtspflege, reine Kosten- und Fristfragen ohne \
Grundsatzcharakter. Gemeint sind Nichteintretensentscheide des Bundesgerichts selbst. Prüft \
das Bundesgericht, ob der Versicherer auf eine Einsprache oder das kantonale Gericht auf eine \
Beschwerde eintreten musste (Begründung der Einsprache, Fristen, rechtliches Gehör), ist das \
eine Verfahrensfrage nach ATSG und wie ein materielles Urteil zu bewerten.
- Urteile, die nur den konkreten Sachverhalt würdigen, ohne für die Praxis der Suva etwas \
Neues oder Bestätigenswertes zu sagen.

Erfahrungswerte: Von den Urteilen zur Unfallversicherung mit materieller Beurteilung nimmt die \
Suva die meisten auf, von den Urteilen zur Invalidenversicherung nur etwa jedes zehnte, nämlich \
die mit Aussagen, die auch in der Unfallversicherung gelten (Invaliditätsbemessung, \
Verwertbarkeit der Restarbeitsfähigkeit, Hilflosenentschädigung, Beweiswert von Gutachten, \
Revision, Verfahren nach ATSG).

Ordne das Urteil einer Relevanzstufe zu:
9 = Leitentscheid oder neue Rechtsfrage der Unfall- oder Militärversicherung
7-8 = materielles Urteil zur Unfallversicherung mit Grundsätzen, die für die Praxis der Suva \
nützlich sind
5-6 = Grenzfall, z.B. Urteil einer anderen Sozialversicherung mit klar übertragbaren Grundsätzen
3-4 = Bezug zur Unfallversicherung, aber nur Würdigung des Einzelfalls, oder IV-Urteil ohne \
Bedeutung für die Unfallversicherung
0-2 = kein Bezug zur Unfallversicherung oder rein prozessuale Erledigung (Nichteintreten, \
Abschreibung, vereinfachtes Verfahren)

Die Begründung schreibst du zweimal, als zwei Originale mit demselben Inhalt: auf Deutsch und \
auf Französisch. Jede Fassung besteht aus zwei Sätzen: Der erste nennt den Versicherungszweig, \
die Rolle des Versicherers und die Rechtsfrage, der zweite sagt, warum das Urteil für die Suva \
relevant ist oder nicht; die Relevanzstufe gehört nicht in die Begründung. Jede Fassung \
verwendet nur die Fachbegriffe, Gesetzesabkürzungen und Zitierweise ihrer eigenen Sprache \
(deutsch: UVG, UVV, ATSG, IVG, BGG, "Art. 6 Abs. 2 UVG"; französisch: LAA, OLAA, LPGA, LAI, \
LTF, "art. 6 al. 2 LAA") und ist keine wörtliche Übersetzung der anderen.

Antworte nur mit einem JSON-Objekt in dieser Reihenfolge:
{"reasoning_de": "<zwei Sätze auf Deutsch>", "reasoning_fr": "<deux phrases en français>", \
"key_factors": ["<Stichwort>", ...], "relevanz": <Stufe 0-9>}"""

# Placed after the ruling: without it, the explanations run to four or five sentences.
REMINDER = (
    "Antworte jetzt mit dem JSON-Objekt. reasoning_de und reasoning_fr haben je höchstens drei "
    "kurze Sätze (zusammen höchstens 60 Wörter pro Sprache)."
)
LANGUAGE_NAMES = {"de": "Deutsch", "fr": "Französisch"}


def load_examples(path: Path) -> list[dict[str, Any]]:
    """Suva's example summaries from the few-shot pool of `split.json` next to `path`.

    The evaluation hold-out is never shown to the model.
    """
    if not path.exists():
        return []
    pool = set(json.loads((path.parent / "split.json").read_text())["fewshot_pool"])
    with open(path, encoding="utf-8") as f:
        examples = [json.loads(line) for line in f if line.strip()]
    return [e for e in examples if e["docket"] in pool]


def load_glossary(path: Path) -> dict[str, Any]:
    """The DE/FR glossary (`glossary.json` next to the examples at `path`)."""
    path = path.parent / "glossary.json"
    if not path.exists():
        return {"statutes": [], "terms": []}
    return json.loads(path.read_text(encoding="utf-8"))


def terminology(glossary: dict[str, Any], text: str) -> list[str]:
    """DE = FR pairs of the glossary's statutes and terms that occur in `text`."""
    statutes = [
        f"{s['de']} = {s['fr']}"
        for s in glossary["statutes"]
        if s["de"] != s["fr"] and contains_term(text, [s["de"], s["fr"]])
    ]
    terms = [
        t
        for t in glossary["terms"]
        if contains_term(text, term_forms(t, "de") + term_forms(t, "fr"))
    ]
    terms.sort(key=lambda t: -t.get("support", 0))
    return statutes + [f"{t['de']} = {t['fr']}" for t in terms[:GLOSSARY_TERMS]]


def _first_sentences(text: str, limit: int = 300) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text.rfind(". ", 0, limit)
    return text[: cut + 1] if cut > 80 else text[:limit] + " ..."


def build_messages(
    ruling: dict[str, Any],
    prior_: Prior,
    examples: list[dict[str, Any]],
    glossary: dict[str, Any],
) -> list[Message]:
    parts = []
    # The ruling's own example summary is left out so the labelled period can be evaluated.
    shown = [e for e in examples if e["docket"] != ruling["docket"]]
    if shown:
        lines = "\n".join(f"- {e['docket']}: {_first_sentences(e['text_de'])}" for e in shown)
        parts.append(f"Beispiele früherer Urteile, die die Suva zusammengefasst hat:\n{lines}")
    text = excerpt(ruling.get("text") or "")
    if terms := terminology(glossary, text):
        lines = "\n".join(f"- {term}" for term in terms)
        parts.append(f"Fachbegriffe Deutsch = Französisch für die Begründung:\n{lines}")
    parts.append(
        f"Zu bewertendes Urteil: {ruling['docket']} vom {ruling.get('decision_date') or '?'}\n"
        f"Hinweise aus der Vorprüfung: {', '.join(prior_.factors) or 'keine'}\n\n"
        f"{text}"
    )
    parts.append(REMINDER)
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "\n\n".join(parts)},
    ]


_LEVEL_KEY = re.compile(r'"relevanz"\s*:\s*"?$')


def expected_level(logprobs: list[TokenLogprob] | None) -> float | None:
    """Probability-weighted relevance level from the logprobs of the digit the model wrote.

    The generated digit alone clusters on a few values; the expectation ranks within them.
    """
    text = ""
    for token in logprobs or []:
        if token.token.strip().isdigit() and _LEVEL_KEY.search(text):
            # Alternatives such as "9" and the full-width "９" are the same level, so they add up.
            probs = [0.0] * 10
            for t, lp in token.top.items():
                if t.strip().isdigit() and len(t.strip()) == 1:
                    probs[int(t.strip())] += math.exp(lp)
            total = sum(probs)
            return sum(level * p for level, p in enumerate(probs)) / total if total else None
        text += token.token
    return None


_FUNCTION_WORDS = {
    "de": re.compile(
        r"\b(?:der|die|das|und|oder|aber|ist|sind|wird|werden|wurde|hat|nicht|kein|keine|keinen|"
        r"ein|eine|einer|einem|einen|eines|dem|den|zur|zum|vom|beim|im|mit|für|auf|aus|bei|von|"
        r"nach|über|durch|gegen|ohne|seit|trotz|wegen|mangels|sowie|auch|dass|sich|es|sie|er)\b"
    ),
    "fr": re.compile(
        r"\b(?:le|la|les|et|ou|est|sont|été|a|ont|une|un|de|du|des|au|aux|pour|dans|par|sur|"
        r"avec|sans|que|qui|ne|pas|ni|ce|cette|ces|son|sa|ses|il|elle|l|d|qu|n)\b"
    ),
    "it": re.compile(
        r"\b(?:il|lo|gli|della|dello|dei|degli|delle|che|non|per|con|sono|è|nel|nella|alla|"
        r"del|una|uno)\b"
    ),
}


def language(text: str) -> str | None:
    """The language ("de", "fr" or "it") most of the text's function words belong to."""
    counts = {lang: len(words.findall(text.lower())) for lang, words in _FUNCTION_WORDS.items()}
    first, second = sorted(counts.values(), reverse=True)[:2]
    return max(counts, key=counts.__getitem__) if first >= 2 and first > second else None


def _text(value: Any) -> str:
    if isinstance(value, list):
        value = " ".join(map(str, value))
    return " ".join(str(value or "").split())


def parse_result(
    data: Any, model: str | None, prior_score: int = 0, level: float | None = None
) -> TriageResult:
    """Validate the model's reply and blend its relevance level with the prior into a score.

    The label always follows the score.
    """
    if not isinstance(data, dict):
        raise ValueError(f"expected a JSON object, got {data!r}")
    if level is None:
        level = float(data["relevanz"])
    level = max(0.0, min(9.0, level))
    score = round(100 * ((1 - PRIOR_WEIGHT) * level / 9 + PRIOR_WEIGHT * prior_score / 100))
    return TriageResult(
        score=score,
        label="relevant" if score >= RELEVANCE_THRESHOLD else "not_relevant",
        reasoning_de=_text(data.get("reasoning_de")),
        reasoning_fr=_text(data.get("reasoning_fr")),
        model=model,
    )


def wrong_language(result: TriageResult) -> list[str]:
    """The languages whose reasoning is missing or written in another language."""
    return [lang for lang in LANGUAGES if language(getattr(result, f"reasoning_{lang}")) != lang]


_LEVEL = (
    r"(?:Relevanz(?:stufe)?|Stufe|Niveau(?: de pertinence)?|Pertinence)\s*:?\s*\d(?:\s*-\s*\d)?"
)
# "Stufe 7." or "Relevanz: 8 (...)." as a sentence of its own, or "(Stufe 5-6)" inside one.
_LEVEL_SENTENCE = re.compile(
    rf"(?:^|(?<=[.;!?]))\s*(?:Daher\s+|Donc\s+)?{_LEVEL}\s*(?:\([^)]*\))?\s*[.;]?", re.IGNORECASE
)
_LEVEL_ASIDE = re.compile(rf"\s*\({_LEVEL}\)", re.IGNORECASE)


def without_level(text: str) -> str:
    """Drop the relevance level the model sometimes writes into its explanation."""
    return " ".join(_LEVEL_ASIDE.sub("", _LEVEL_SENTENCE.sub(" ", text)).split())


# Italian abbreviations that differ from the French ones, by German abbreviation.
ITALIAN_STATUTES = {"LAINF": "UVG", "OAINF": "UVV", "OAI": "IVV", "LADI": "AVIG", "CEDU": "EMRK"}


def native_statutes(text: str, glossary: dict[str, Any], lang: str) -> str:
    """Replace the other languages' statute abbreviations: "Art. 73 lit. b OLAA" in German
    becomes "Art. 73 lit. b UVV", a pair such as "UVG/LAA" becomes "UVG", and "OAI" from an
    Italian ruling becomes "IVV" or "RAI".

    The model keeps such abbreviations even when asked to rewrite, and they map one to one.
    """
    other = "fr" if lang == "de" else "de"
    for foreign in foreign_statutes(text, glossary, lang):
        native = next(s[lang] for s in glossary["statutes"] if s[other] == foreign)
        n, f = re.escape(native), re.escape(foreign)
        text = re.sub(rf"(?<![\w-])(?:{n}\s*/\s*{f}|{f}\s*/\s*{n})(?![\w-])", native, text)
        text = re.sub(rf"(?<![\w-]){f}(?![\w-])", native, text)
    for italian, german in ITALIAN_STATUTES.items():
        if native := next((s[lang] for s in glossary["statutes"] if s["de"] == german), None):
            text = re.sub(rf"(?<![\w-]){italian}(?![\w-])", native, text)
    return text


def prefiltered(prior_: Prior) -> TriageResult:
    return TriageResult(
        score=prior_.score // 4,
        label="not_relevant",
        reasoning_de=(
            "In der Vorprüfung ausgeschieden: Das Urteil betrifft weder die Unfall- noch die "
            "Invaliden- oder Militärversicherung und hat zu wenig Bezug zur Suva oder zum UVG. "
            f"Gefundene Hinweise: {', '.join(prior_.factors) or 'keine'}."
        ),
        reasoning_fr=(
            "Écarté lors de l'examen préliminaire: l'arrêt ne concerne ni l'assurance-accidents, "
            "ni l'assurance-invalidité, ni l'assurance militaire et présente trop peu de lien "
            f"avec la Suva ou la LAA. Indices relevés: {', '.join(prior_.factors_fr) or 'aucun'}."
        ),
        model=PREFILTER_MODEL,
    )


def gate(text: str) -> tuple[str, str] | None:
    """Why a ruling does not decide on the merits (German, French), or None if it does.

    Suva never lists such decisions: none of the 82 candidates of Q4 2025 and Q1 2026 is listed.
    """
    outcome = classify.outcome(text)
    if outcome == "not_entertained":
        return "Nichteintretensentscheid", "décision d'irrecevabilité"
    if outcome == "struck_off":
        return "Abschreibung", "radiation du rôle"
    if classify.panel_size(text) in (1, 2):
        return "Entscheid des Einzelrichters", "décision du juge unique"
    if not segment(text).substantive:
        return "keine materielle Erwägung", "aucun considérant sur le fond"
    return None


def gated(prior_: Prior, reason: tuple[str, str]) -> TriageResult:
    de, fr = reason
    return TriageResult(
        score=prior_.score // 4,
        label="not_relevant",
        reasoning_de=(
            f"Ohne Bewertung durch das Sprachmodell ausgeschieden ({de}): Das Bundesgericht "
            "entscheidet nicht in der Sache, und solche Entscheide nimmt die Suva nicht in ihre "
            "Rechtsprechungsübersicht auf."
        ),
        reasoning_fr=(
            f"Écarté sans évaluation par le modèle de langage ({fr}): le Tribunal fédéral ne "
            "statue pas sur le fond, et la Suva ne reprend pas de telles décisions dans sa revue "
            "de jurisprudence."
        ),
        model=GATE_MODEL,
    )


def triage_ruling(
    ruling: dict[str, Any],
    llm: LLMClient,
    examples: list[dict[str, Any]],
    glossary: dict[str, Any],
) -> TriageResult:
    prior_ = prior(ruling)
    if prior_.score < PRIOR_CUTOFF:
        return prefiltered(prior_)
    if reason := gate(ruling.get("text") or ""):
        return gated(prior_, reason)
    messages = build_messages(ruling, prior_, examples, glossary)
    completion = llm.complete(messages, max_tokens=900, logprobs=True, top_logprobs=10)
    result = parse_result(
        parse_json(completion.content),
        llm.model,
        prior_score=prior_.ranking,
        level=expected_level(completion.logprobs),
    )
    if wrong := wrong_language(result):
        # Ask once more for just the faulty fields; the level of the first answer stands.
        fields = ", ".join(f'"reasoning_{lang}" auf {LANGUAGE_NAMES[lang]}' for lang in wrong)
        retry = messages + [
            {"role": "assistant", "content": completion.content},
            {
                "role": "user",
                "content": f"Schreibe {fields} neu, mit demselben Inhalt. Antworte nur mit "
                "einem JSON-Objekt mit diesen Feldern.",
            },
        ]
        fixed = parse_json(llm.complete(retry, max_tokens=600).content)
        for lang in wrong:
            setattr(result, f"reasoning_{lang}", _text(fixed.get(f"reasoning_{lang}")))
        if wrong := wrong_language(result):
            raise ValueError(f"reasoning not written in {', '.join(wrong)}")
    for lang in LANGUAGES:
        text = without_level(getattr(result, f"reasoning_{lang}"))
        setattr(result, f"reasoning_{lang}", native_statutes(text, glossary, lang))
    return result


def triage(conn: sqlite3.Connection, docket: str, llm: LLMClient) -> TriageResult:
    """Score how relevant ruling `docket` is for Suva and explain why. Does not persist."""
    ruling = db.get_ruling(conn, docket)
    if ruling is None:
        raise KeyError(docket)
    path = llm.settings.examples_path
    return triage_ruling(ruling, llm, load_examples(path), load_glossary(path))


def triage_batch(
    conn: sqlite3.Connection, dockets: list[str], llm: LLMClient, workers: int = 8
) -> Iterator[tuple[str, TriageResult | Exception]]:
    """Triage many rulings with parallel LLM calls, yielding results as they complete.

    A failed ruling yields its exception instead of stopping the batch; rerunning picks it up.
    """
    path = llm.settings.examples_path
    examples, glossary = load_examples(path), load_glossary(path)
    rulings = [db.get_ruling(conn, docket) for docket in dockets]
    with ThreadPoolExecutor(workers) as pool:
        futures = {
            pool.submit(triage_ruling, ruling, llm, examples, glossary): ruling["docket"]
            for ruling in rulings
            if ruling is not None
        }
        for future in as_completed(futures):
            try:
                yield futures[future], future.result()
            except Exception as exc:
                yield futures[future], exc
