"""Relevance triage of a ruling for Suva.

Stage 1 is a deterministic prior from the docket and the text (division, statutes, Suva as a
party, accident-insurance vocabulary). Rulings below `PRIOR_CUTOFF` are labelled not relevant
without an LLM call. Stage 2 asks Apertus for a score and a German explanation, with the topics
of Suva's own example summaries and the lawyers' feedback as context.
"""

import json
import re
import sqlite3
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from suva import db
from suva.llm import LLMClient, Message

PROMPT_VERSION = "v1"
PREFILTER_MODEL = "prefilter"
RELEVANCE_THRESHOLD = 50
PRIOR_CUTOFF = 20
EXCERPT_CHARS = 30_000


@dataclass
class TriageResult:
    score: int  # 0-100
    label: Literal["relevant", "not_relevant"]
    reasoning: str
    model: str | None = None


@dataclass
class Prior:
    score: int
    factors: list[str]


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

_FACTS = re.compile(r"^\s*(?:Sachverhalt|Faits|Fatti)\s*:", re.MULTILINE)
_REASONS = re.compile(
    r"^\s*(?:Erwägungen?|Considérant en droit|Considérants?|Diritto|Considerando in diritto)\s*:",
    re.MULTILINE,
)
_OPERATIVE = re.compile(r"^\s*(?:Demnach erkennt|Par ces motifs|Per questi motivi)", re.MULTILINE)
_SUBJECT = re.compile(
    r"^\s*(?:Gegenstand|Objet|Oggetto)\s*\n(.+?)(?:\n\s*(?:Beschwerde|Recours|Ricorso|Revisionsgesuch|"
    r"Demande|Domanda)|\Z)",
    re.MULTILINE | re.DOTALL | re.IGNORECASE,
)


def _clean(text: str) -> str:
    return re.sub(r"[ \t\xa0]*\n[\s\xa0]*", "\n", text).strip()


@dataclass
class Sections:
    rubrum: str
    facts: str
    reasons: str
    operative: str


def split_sections(text: str) -> Sections:
    """Split a ruling into rubrum (parties, subject), facts, reasons and operative part."""
    text = _clean(text)
    operative = _OPERATIVE.search(text)
    end = operative.start() if operative else len(text)
    reasons = _REASONS.search(text, 0, end)
    facts = _FACTS.search(text, 0, reasons.start() if reasons else end)
    rubrum_end = min(m.start() for m in (facts, reasons) if m) if (facts or reasons) else 0
    return Sections(
        rubrum=text[:rubrum_end],
        facts=text[facts.start() : reasons.start() if reasons else end] if facts else "",
        reasons=text[reasons.start() : end] if reasons else text[rubrum_end:end],
        operative=text[end:],
    )


def subject(text: str) -> str:
    """The "Gegenstand" line of the rubrum, e.g. "Unfallversicherung (Kausalzusammenhang)"."""
    match = _SUBJECT.search(_clean(text)[:6000])
    return " ".join(match.group(1).split()).rstrip(",") if match else ""


def prior(ruling: dict[str, Any]) -> Prior:
    """Cheap relevance prior from docket and text; it decides which rulings reach the LLM."""
    text = ruling.get("text") or ""
    sections = split_sections(text)
    subj = ruling.get("title") or subject(text)
    score, factors = 0, []

    def add(points: int, factor: str) -> None:
        nonlocal score
        score += points
        factors.append(factor)

    if ACCIDENT_INSURANCE.search(subj) or MVG.search(subj):
        add(45, f"Gegenstand: {subj}")
    elif INVALIDITY_INSURANCE.search(subj):
        add(25, f"Gegenstand: {subj}")
    division = (ruling.get("docket") or "")[:2]
    if points := DIVISION_PRIOR.get(division):
        add(points, f"Abteilung {division}")
    if SUVA.search(sections.rubrum):
        add(25, "Suva ist Partei")
    elif SUVA.search(text):
        add(10, "Suva erwähnt")
    if uvg := len(UVG.findall(text)):
        add(min(15, 3 + uvg), f"UVG/UVV zitiert ({uvg}x)")
    if MVG.search(text) and not MVG.search(subj):
        add(10, "Militärversicherung erwähnt")
    if ACCIDENT_INSURANCE.search(text) and not ACCIDENT_INSURANCE.search(subj):
        add(5, "Unfallversicherung erwähnt")
    if ATSG.search(text):
        add(5, "ATSG zitiert")
    return Prior(score=min(score, 100), factors=factors)


def excerpt(text: str, limit: int = EXCERPT_CHARS) -> str:
    """The parts of a ruling that matter for triage, within `limit` characters."""
    text = _clean(text)
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
Grundsatzcharakter.
- Urteile, die nur den konkreten Sachverhalt würdigen, ohne für die Praxis der Suva etwas \
Neues oder Bestätigenswertes zu sagen.

Bewerte die Relevanz mit einem Score von 0 bis 100:
85-100 klar relevant, gehört in die Übersicht; 60-84 eher relevant; 30-59 Grenzfall; \
0-29 nicht relevant.

Antworte nur mit einem JSON-Objekt:
{"score": <0-100>, "label": "relevant" | "not_relevant", \
"reasoning": "<2-4 Sätze auf Deutsch: worum es geht und warum das Urteil für die Suva relevant \
ist oder nicht>", "key_factors": ["<Stichwort>", ...]}"""


def load_examples(path: Path) -> list[dict[str, str]]:
    """Suva's example summaries (docket and German text) from a JSONL file, if present."""
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _first_sentences(text: str, limit: int = 300) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text.rfind(". ", 0, limit)
    return text[: cut + 1] if cut > 80 else text[:limit] + " ..."


def build_messages(
    ruling: dict[str, Any],
    prior_: Prior,
    examples: list[dict[str, str]],
    feedback: list[dict[str, Any]],
) -> list[Message]:
    parts = []
    # The ruling's own example summary is left out so the labelled period can be evaluated.
    shown = [e for e in examples if e["docket"] != ruling["docket"]]
    if shown:
        lines = "\n".join(f"- {e['docket']}: {_first_sentences(e['de'])}" for e in shown)
        parts.append(f"Beispiele früherer Urteile, die die Suva zusammengefasst hat:\n{lines}")
    if feedback:
        lines = "\n".join(
            f"- {f['docket']} ({subject(f['text'] or '') or f['title'] or 'ohne Gegenstand'}): "
            f"{'relevant' if f['verdict'] == 'relevant' else 'nicht relevant'}"
            + (f", Score {f['corrected_score']}" if f["corrected_score"] is not None else "")
            + (f". Kommentar: {f['comment']}" if f["comment"] else "")
            for f in feedback
        )
        parts.append(
            "Korrekturen der Juristinnen und Juristen der Suva an früheren Bewertungen "
            f"(diese gehen deiner eigenen Einschätzung vor):\n{lines}"
        )
    parts.append(
        f"Zu bewertendes Urteil: {ruling['docket']} vom {ruling.get('decision_date') or '?'}\n"
        f"Hinweise aus der Vorprüfung: {', '.join(prior_.factors) or 'keine'}\n\n"
        f"{excerpt(ruling.get('text') or '')}"
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "\n\n".join(parts)},
    ]


def parse_result(data: Any, model: str | None) -> TriageResult:
    """Validate the model's JSON reply; the label always follows the score."""
    if not isinstance(data, dict):
        raise ValueError(f"expected a JSON object, got {data!r}")
    score = max(0, min(100, round(float(data["score"]))))
    reasoning = data.get("reasoning") or ""
    if isinstance(reasoning, list):
        reasoning = " ".join(map(str, reasoning))
    return TriageResult(
        score=score,
        label="relevant" if score >= RELEVANCE_THRESHOLD else "not_relevant",
        reasoning=" ".join(str(reasoning).split()),
        model=model,
    )


def prefiltered(prior_: Prior) -> TriageResult:
    hints = ", ".join(prior_.factors) if prior_.factors else "keine"
    return TriageResult(
        score=prior_.score // 4,
        label="not_relevant",
        reasoning=(
            "In der Vorprüfung ausgeschieden: Das Urteil enthält keine ausreichenden Bezüge zur "
            "Unfall- oder Militärversicherung (keine Suva-Beteiligung, kaum UVG/UVV-Zitate). "
            f"Gefundene Hinweise: {hints}."
        ),
        model=PREFILTER_MODEL,
    )


def triage_ruling(
    ruling: dict[str, Any],
    llm: LLMClient,
    examples: list[dict[str, str]],
    feedback: list[dict[str, Any]],
) -> TriageResult:
    prior_ = prior(ruling)
    if prior_.score < PRIOR_CUTOFF:
        return prefiltered(prior_)
    messages = build_messages(ruling, prior_, examples, feedback)
    return parse_result(llm.chat_json(messages, max_tokens=600), llm.model)


def triage(conn: sqlite3.Connection, docket: str, llm: LLMClient) -> TriageResult:
    """Score how relevant ruling `docket` is for Suva and explain why. Does not persist."""
    ruling = db.get_ruling(conn, docket)
    if ruling is None:
        raise KeyError(docket)
    examples = load_examples(llm.settings.examples_path)
    return triage_ruling(ruling, llm, examples, db.latest_feedback(conn))


def triage_batch(
    conn: sqlite3.Connection, dockets: list[str], llm: LLMClient, workers: int = 8
) -> Iterator[tuple[str, TriageResult | Exception]]:
    """Triage many rulings with parallel LLM calls, yielding results as they complete.

    A failed ruling yields its exception instead of stopping the batch; rerunning picks it up.
    """
    examples = load_examples(llm.settings.examples_path)
    feedback = db.latest_feedback(conn)
    rulings = [db.get_ruling(conn, docket) for docket in dockets]
    with ThreadPoolExecutor(workers) as pool:
        futures = {
            pool.submit(triage_ruling, ruling, llm, examples, feedback): ruling["docket"]
            for ruling in rulings
            if ruling is not None
        }
        for future in as_completed(futures):
            try:
                yield futures[future], future.result()
            except Exception as exc:
                yield futures[future], exc
