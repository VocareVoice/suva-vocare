"""Deterministic segmenter for Federal Supreme Court rulings (DE/FR/IT).

A ruling is cut into rubrum, facts, considerations (numbered, each classified), dispositive and
signature. Shapes:
- full: separate facts ("Sachverhalt:") and reasons ("Erwägungen:") headings
- combined: one heading for facts and law ("Considérant en fait et en droit", "zieht in
  Erwägung"), or "Erwägungen:" right after the rubrum with the facts in E. 1
- order: "Vu : ... considérant : que ..." / "in Erwägung, dass ...", unnumbered paragraphs
- unsegmented: no reasons heading found

Coverage on the corpus: docs/eval_triage.md.
"""

import re
from dataclasses import dataclass, field

_FACTS = re.compile(r"^(?:Sachverhalt|Faits|Fatti)\s*:\s*$", re.M)
_REASONS = re.compile(
    r"^(?:Erwägung(?:en)?|Considérant en droit|Considérants|Diritto|Considerando in diritto)"
    r"\s*:?\s*$",
    re.M,
)
_COMBINED = re.compile(
    r"^(?:Considérant en fait et en droit|Ritenuto in fatto e considerando in diritto"
    r"|(?:Das Bundesgericht|D(?:er|ie|as) [\wä ]{3,40}) zieht in Erwägung"
    r"|Considerando in fatto e in diritto)\s*:\s*$",
    re.M | re.I,
)
_ORDER = re.compile(
    r"^(?:considérant|Considerando|in Erwägung(?:, dass)?|considerato)\s*[,:]?\s*$|"
    r"^(?:in Erwägung,? dass|considérant que|considerato che)\b",
    re.M | re.I,
)
_VU = re.compile(r"^(?:Vu|Nach Einsicht|Visto|Ritenuto)\b.{0,40}:?\s*$", re.M)
_VERB = (
    r"(?:erkennt|verfügt|entscheidet|stellt\b.{0,40}\bfest|prononce|ordonne|décide|pronuncia"
    r"|decreta|ordina|decide)"
)
_DISPOSITIVE = re.compile(
    rf"^(?:(?:Demnach|Par ces motifs,?|Per questi motivi,?)\s+)?[\wÀ-ÿ' ]{{0,40}}?{_VERB}"
    r"(?:\s+[\wÀ-ÿ' ]{0,40})?\s*:\s*$"
    r"|^(?:Demnach erkennt|Par ces motifs|Per questi motivi)\b.*$",
    re.M | re.I,
)
_PLACES = (
    r"Luzern|Lausanne|Lucerne|Lucerna|Losanna|Bellinzona|St\. Gallen|Saint-Gall|San Gallo"
    r"|Mon-Repos"
)
_SIGNATURE = re.compile(rf"^(?:{_PLACES})\s*,\s*(?:le |den |il )?\d", re.M)
_SIGNATURE_FALLBACK = re.compile(r"^(?:Im Namen de|Au nom de|In nome de)", re.M)
_ROMAN = re.compile(r"^(?:[IVX]{1,5}|[A-H])\.\s+\S.{0,150}$")
_TOP = re.compile(r"^(\d{1,2})\.(?:\s*$|\s+(?=\S))")
_SUB = re.compile(r"^(\d{1,2})\.(\d{1,2})(?:\.\d{1,2})*\.?(?:\s|$)")
_FACT_LETTER = re.compile(r"^([A-Z])\.(?:[a-z]\.)?(?:\s|$)", re.M)

# "Art. 106 Abs. 1 BGG", "art. 66 al. 1, 2e phrase, LTF", "Art. 95 f. BGG"
_TAIL = (
    r"(?:\s*(?:Abs|al|cpv|lit|let|Bst|Satz|phrase|seconde|i\.V\.m|f|ff|und|et|e|bis|in fine"
    r"|\d+e?|[a-z])\b\.?,?)*\s*"
)
_REVIEW = re.compile(
    rf"\b[Aa]rt\.\s*(?:29|42|82|83|84|85|86|87|88|89|90|91|92|93|95|96|97|99|100|101|105|106"
    rf"|107|108){_TAIL}(?:BGG|LTF)\b"
    r"|Kognition|pouvoir d'examen|potere d'esame|von Amtes wegen|d'office|d'ufficio"
    r"|offensichtlich unrichtig|manifestement inexact|manifestamente inesatt"
    r"|Eintretensvoraussetzung|Sachurteilsvoraussetzung|(?:ist|nicht) einzutreten|recevab"
    r"|irrecevab|ammissib|inammissib|Beschwerdefrist|délai de recours|termine di ricorso"
    r"|\bNoven\b|\bnova\b|faits nouveaux|fatti nuovi|Rügeprinzip|Rügepflicht"
    r"|Verfahren\w* (?:zu )?vereinig|jonction des causes|joindre les causes|congiun",
    re.I,
)
_COSTS = re.compile(
    rf"\b[Aa]rt\.\s*6[4-8]{_TAIL}(?:BGG|LTF)\b"
    r"|Gerichtskosten|Parteientschädigung|unentgeltliche Rechtspflege|unentgeltliche Verbeiständung"
    r"|frais judiciaires|frais de (?:la )?procédure|dépens|assistance judiciaire"
    r"|spese giudiziarie|ripetibili|gratuito patrocinio|assistenza giudiziaria",
    re.I,
)
# Closing remarks after the costs: suspensive effect or other requests now moot.
_CLOSING = re.compile(
    r"aufschiebende\w* Wirkung|gegenstandslos|effet suspensif|sans objet|effetto sospensivo"
    r"|privo d.oggetto|priva di oggetto",
    re.I,
)
_LOWER_DECISION = re.compile(
    r"\b(?:mit|durch) (?:Urteil|Entscheid|Verfügung|Einspracheentscheid) vom"
    r"|\b(?:par|du) (?:arrêt|jugement|décision)\b[^.]{0,40}\bdu \d"
    r"|\bcon (?:sentenza|decisione|giudizio) del",
    re.I,
)
_SUBSTANTIVE_LAW = re.compile(
    r"\b(?:ATSG|LPGA|UVG|UVV|LAA|OLAA|LAINF|OAINF|IVG|IVV|LAI|RAI|MVG|LAM|AHVG|LAVS|BVG|LPP"
    r"|ELG|LPC|AVIG|LACI|KVG|LAMal|ZGB|CC|OR|CO|StGB|CP|VVG|LCA|EOG|LAPG|FamZG|LAFam)\b"
)
_ISSUE = re.compile(
    r"\bStreitig(?:\s+und\s+zu\s+prüfen)?\s+ist|\bstreitig\s+ist|Zu\s+prüfen\s+ist"
    r"|\bEst\s+litigieu|\best\s+litigieu|Le\s+litige\s+porte|litige\s+porte|objet\s+du\s+litige"
    r"|\bLitigios[ao]\b|\boggetto\s+del\s+contendere|\bÈ\s+litigios|\bè\s+litigios",
    re.I,
)


def clean(text: str) -> str:
    return re.sub(r"[ \t\xa0]*\n[\s\xa0]*", "\n", text).strip()


@dataclass
class Consideration:
    number: str  # "1", "2", ...; "" for an unnumbered order
    text: str
    kind: str = "substantive"  # admissibility | substantive | costs | facts
    subs: int = 0  # number of sub-considerations (2.1, 2.2, ...)
    heading: str = ""  # a Roman or lettered heading in front of it ("III. Frais")
    issue: bool = False  # states what is disputed ("Streitig ist ...")


@dataclass
class Segments:
    shape: str  # full | combined | order | unsegmented
    rubrum: str = ""
    facts: str = ""
    reasons: str = ""  # from the reasons heading to the dispositive, as in the ruling
    considerations: list[Consideration] = field(default_factory=list)
    dispositive: str = ""
    signature: str = ""
    problems: list[str] = field(default_factory=list)

    @property
    def substantive(self) -> list[Consideration]:
        return [c for c in self.considerations if c.kind == "substantive"]


def _last(pattern: re.Pattern[str], text: str, start: int = 0) -> re.Match[str] | None:
    matches = list(pattern.finditer(text, start))
    return matches[-1] if matches else None


def segment(text: str) -> Segments:
    """Cut a ruling into its parts; `problems` is empty when every boundary was found."""
    text = clean(text)
    problems = []

    reasons = _REASONS.search(text)
    combined = _COMBINED.search(text)
    order = None
    if reasons and combined:
        reasons = min(reasons, combined, key=lambda m: m.start())
        combined = reasons if reasons.re is _COMBINED else None
    elif combined:
        reasons = combined
    if not reasons:
        order = _ORDER.search(text)
        reasons = order

    dispositive = _last(_DISPOSITIVE, text, reasons.end() if reasons else 0)
    if dispositive is None:
        problems.append("no_dispositive")
    end = dispositive.start() if dispositive else len(text)
    signature = _SIGNATURE.search(text, end) or _SIGNATURE_FALLBACK.search(text, end)
    if dispositive and not signature:
        problems.append("no_signature")
    sig_start = signature.start() if signature else len(text)

    if not reasons:
        return Segments(
            shape="unsegmented",
            rubrum=text[:end],
            dispositive=text[end:sig_start],
            signature=text[sig_start:],
            problems=["no_reasons", *problems],
        )

    shape = "order" if order else "combined" if combined else "full"
    facts = _FACTS.search(text, 0, reasons.start())
    rubrum_end = facts.start() if facts else reasons.start()
    if shape == "order":
        vu = _VU.search(text, 0, reasons.start())
        if vu:
            rubrum_end = vu.start()
    elif shape == "full" and not facts:
        # Simplified rulings: "Erwägungen:" right after the rubrum, the facts in E. 1.
        shape = "combined"
    if facts and not _FACT_LETTER.search(text, facts.end(), reasons.start()):
        problems.append("facts_unlettered")
    facts_text = text[rubrum_end : reasons.start()] if (facts or shape == "order") else ""

    body = text[reasons.end() : end]
    considerations = _considerations(body, numbered=shape != "order", problems=problems)
    _classify(considerations, shape)
    return Segments(
        shape=shape,
        rubrum=text[:rubrum_end],
        facts=facts_text.strip(),
        reasons=text[reasons.start() : end].strip(),
        considerations=considerations,
        dispositive=text[end:sig_start].strip(),
        signature=text[sig_start:].strip(),
        problems=problems,
    )


def _considerations(body: str, numbered: bool, problems: list[str]) -> list[Consideration]:
    lines = body.strip("\n").split("\n")
    if not numbered:
        return [Consideration(number="", text="\n".join(lines).strip())]
    result: list[Consideration] = []
    preamble: list[str] = []
    current: list[str] | None = None
    heading = ""
    expected = 1
    implicit = 0
    # Modern rulings put a top-level number on a line of its own ("2.\n2.1. ..."); then a
    # numbered line with text after it is a list item or a quote, not a consideration.
    bare = any(re.fullmatch(r"\d{1,2}\.\s*", line) for line in lines)
    for line in lines:
        sub = _SUB.match(line)
        top = _TOP.match(line) if not sub else None
        if top and bare and line[top.end() :].strip() and expected > 1 and len(line) < 300:
            top = None
        if top and int(top.group(1)) == expected:
            if current is not None:
                result[-1].text = "\n".join(current).strip()
            result.append(Consideration(number=top.group(1), text="", heading=heading))
            heading = ""
            current = [line]
            expected += 1
            continue
        if sub and result and sub.group(1) == result[-1].number:
            result[-1].subs += 1
        elif sub and sub.group(1) == str(expected):
            # "3.1." without a "3." line before it
            if current is not None:
                result[-1].text = "\n".join(current).strip()
            result.append(Consideration(number=str(expected), text="", heading=heading, subs=1))
            heading = ""
            current = []
            expected += 1
            implicit += 1
        # A heading between considerations ("III. Frais et dépens") belongs to the next one.
        if (
            _ROMAN.match(line)
            and not sub
            and not top
            and len(line) < 120
            and current is not None
            and _looks_like_heading(line)
        ):
            heading = line
            continue
        (current if current is not None else preamble).append(line)
    if current is not None:
        result[-1].text = "\n".join(current).strip()
    if implicit:
        problems.append("implicit_top_number")
    if not result:
        problems.append("no_numbered_considerations")
        return [Consideration(number="", text=body.strip())]
    if preamble and len("\n".join(preamble)) > 200:
        problems.append("text_before_first_consideration")
        result[0].text = "\n".join(preamble).strip() + "\n" + result[0].text
    elif preamble:
        result[0].heading = "\n".join(preamble).strip()
    return result


def _looks_like_heading(line: str) -> bool:
    return not line.rstrip().endswith((".", ",", ";", ":")) or bool(
        re.match(r"^[IVX]{1,5}\.\s", line)
    )


def _classify(considerations: list[Consideration], shape: str = "full") -> None:
    """Admissibility/standard of review, substantive reasoning, or costs, per consideration.

    When unsure, a consideration is substantive: skipping one loses what it says.
    """
    n = len(considerations)
    for i, c in enumerate(considerations):
        c.issue = bool(_ISSUE.search(c.text))
        review = len(_REVIEW.findall(c.text))
        costs = len(_COSTS.findall(c.text))
        law = len(_SUBSTANTIVE_LAW.findall(c.text))
        leading = all(prev.kind in ("admissibility", "facts") for prev in considerations[:i])
        closing = bool(costs or _CLOSING.search(c.text))
        last = n > 1 and i == n - 1 and len(c.text) < 2500
        near_end = (
            n > 2
            and i >= max(1, n - 3)
            and not law
            and len(c.text) < 1200
            and all(not _ISSUE.search(later.text) for later in considerations[i + 1 :])
        )
        if closing and (last or near_end):
            c.kind = "costs"
        elif shape == "combined" and i == 0 and not review and _LOWER_DECISION.search(c.text):
            c.kind = "facts"
        elif leading and i < 3 and review and review >= law and not c.issue and len(c.text) < 3000:
            c.kind = "admissibility"
        else:
            c.kind = "substantive"
