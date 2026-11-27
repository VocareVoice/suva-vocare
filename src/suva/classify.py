"""Legal classification of a ruling: insurance branch first, then the legal category.

The taxonomy is a closed list (`BRANCHES`, `CATEGORIES`, `MATRIX`), so labels stay consistent and
filterable. Statutes, precedents, outcome and flags are extracted from the text without an LLM.
Rulings of the social-law divisions are classified by Apertus (JSON schema with enum-constrained
labels, retried when a category does not fit the branch); every other ruling is outside social
insurance by its division. Kept separate from the relevance score.
Results: docs/eval_classification.md.
"""

import re
import sqlite3
from collections import Counter
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from typing import Any, Literal, NamedTuple

from suva import db, triage
from suva.llm import LLMClient, Message, parse_json

PROMPT_VERSION = "v4"
# Stored with the prompt version, so re-extracted statutes and precedents load over older rows
# without re-running Apertus.
EXTRACTION_VERSION = "s2"
VERSION = f"{PROMPT_VERSION}+{EXTRACTION_VERSION}"
EXCERPT_CHARS = 20_000
MAX_ATTEMPTS = 3
MAX_SECONDARY = 2


class Label(NamedTuple):
    de: str
    fr: str


BRANCHES: dict[str, Label] = {
    "uv": Label("Unfallversicherung (UVG)", "Assurance-accidents (LAA)"),
    "iv": Label("Invalidenversicherung (IVG)", "Assurance-invalidité (LAI)"),
    "mv": Label("Militärversicherung (MVG)", "Assurance militaire (LAM)"),
    "atsg": Label(
        "Allgemeines Sozialversicherungsrecht (ATSG)",
        "Droit général des assurances sociales (LPGA)",
    ),
    "other": Label("Ausserhalb der Sozialversicherung", "Hors assurances sociales"),
}

CATEGORIES: dict[str, Label] = {
    "invaliditaetsgrad": Label(
        "Invaliditätsgrad & Einkommensvergleich", "Taux d'invalidité, comparaison des revenus"
    ),
    "verfahren": Label("Verfahren (rechtliches Gehör, Fristen, Kosten)", "Procédure"),
    "natuerliche-kausalitaet": Label("Natürliche Kausalität", "Causalité naturelle"),
    "adaequate-kausalitaet": Label(
        "Adäquate Kausalität (inkl. psychische Folgen, Schleudertrauma)", "Causalité adéquate"
    ),
    "rentenrevision": Label("Rentenrevision", "Révision de la rente"),
    "unfallbegriff": Label(
        "Unfallbegriff & Listenverletzung (Art. 4, Art. 6 Abs. 2 UVG)",
        "Notion d'accident, lésions assimilées",
    ),
    "hilflosigkeit-pflege": Label(
        "Hilflosenentschädigung & Pflege", "Allocation pour impotent, soins"
    ),
    "taggeld-leistungskuerzung": Label(
        "Taggeld & Leistungskürzung (Wagnis, Grobfahrlässigkeit)",
        "Indemnités journalières, réductions",
    ),
    "beweis-gutachten": Label("Beweis & medizinische Gutachten", "Preuve, expertises médicales"),
    "unterstellung-praemien": Label(
        "Unterstellung & Prämien (Art. 66 UVG, Art. 73 UVV)", "Assujettissement, primes"
    ),
    "integritaetsentschaedigung": Label(
        "Integritätsentschädigung", "Indemnité pour atteinte à l'intégrité"
    ),
    "berufskrankheit": Label("Berufskrankheit", "Maladie professionnelle"),
    "rueckforderung-erlass": Label("Rückforderung & Erlass", "Restitution, remise"),
    "regress-haftung": Label("Regress & Haftung", "Recours, responsabilité"),
    "heilbehandlung": Label("Heilbehandlung & Kostenübernahme", "Traitement médical"),
    "koordination": Label(
        "Koordination mit anderen Sozialversicherungen", "Coordination avec d'autres assurances"
    ),
    "andere": Label("Andere", "Autres"),
}

_EVERYWHERE = {"verfahren", "beweis-gutachten", "regress-haftung", "andere"}
_SOCIAL = _EVERYWHERE | {"invaliditaetsgrad", "taggeld-leistungskuerzung", "koordination"}
_SOCIAL |= {"rueckforderung-erlass", "rentenrevision", "hilflosigkeit-pflege", "heilbehandlung"}
_ACCIDENT = {"natuerliche-kausalitaet", "adaequate-kausalitaet", "unfallbegriff"}
_ACCIDENT |= {"integritaetsentschaedigung", "berufskrankheit"}

# Which categories a branch allows. Procedure, evidence, recourse/liability and "other" fit every
# branch; causality, the notion of accident, integrity compensation and occupational disease only
# exist in accident and military insurance; premiums and coverage in accident insurance and the
# other social insurances (AHV contributions, BVG affiliation). Outside social insurance (private
# insurance under the VVG, liability law) daily allowances and income comparisons occur too.
MATRIX: dict[str, frozenset[str]] = {
    "uv": frozenset(_SOCIAL | _ACCIDENT | {"unterstellung-praemien"}),
    "mv": frozenset(_SOCIAL | _ACCIDENT),
    "iv": frozenset(_SOCIAL),
    "atsg": frozenset(_SOCIAL | {"unterstellung-praemien"}),
    "other": frozenset(_EVERYWHERE | {"invaliditaetsgrad", "taggeld-leistungskuerzung"}),
}

Outcome = Literal[
    "upheld", "partly_upheld", "remanded", "dismissed", "not_entertained", "struck_off"
]
OUTCOMES: dict[str, Label] = {
    "upheld": Label("gutgeheissen", "admis"),
    "partly_upheld": Label("teilweise gutgeheissen", "partiellement admis"),
    "remanded": Label("zurückgewiesen", "renvoyé"),
    "dismissed": Label("abgewiesen", "rejeté"),
    "not_entertained": Label("nicht eingetreten", "irrecevable"),
    "struck_off": Label("abgeschrieben", "rayé du rôle"),
}
FLAGS: dict[str, Label] = {
    "five_judges": Label("Fünferbesetzung", "Composition à cinq juges"),
    "public_deliberation": Label("Öffentliche Beratung", "Délibération publique"),
    "publication": Label("Zur Publikation vorgesehen", "Destiné à la publication"),
}


@dataclass
class Classification:
    branch: str
    primary: str
    secondary: list[str]
    statutes: list[dict[str, Any]]
    precedents: list[dict[str, Any]]
    outcome: Outcome | None
    flags: list[str]
    method: Literal["llm", "subject", "rule"]
    model: str | None = None
    rationale: str | None = None


@dataclass
class Facts:
    """What the deterministic extractor reads from a ruling."""

    subject: str
    statutes: list[dict[str, Any]]
    precedents: list[dict[str, Any]]
    outcome: Outcome | None
    flags: list[str] = field(default_factory=list)


def taxonomy(counts: dict[str, Any] | None = None) -> dict[str, Any]:
    """The closed label lists with German and French labels, for the UI's badges and filters.

    `counts` (from `db.classification_counts`) adds how many rulings carry each label.
    """
    counts = counts or {"branches": {}, "categories": {}}

    def labels(items: dict[str, Label]) -> list[dict[str, Any]]:
        return [{"value": slug, "de": label.de, "fr": label.fr} for slug, label in items.items()]

    return {
        "branches": [
            {**item, "count": counts["branches"].get(item["value"], 0)} for item in labels(BRANCHES)
        ],
        "categories": [
            {
                **item,
                "branches": [b for b, allowed in MATRIX.items() if item["value"] in allowed],
                "counts": counts["categories"].get(item["value"], {}),
            }
            for item in labels(CATEGORIES)
        ],
        "outcomes": labels(OUTCOMES),
        "flags": labels(FLAGS),
    }


# ---------------------------------------------------------------- deterministic extraction

# French and Italian abbreviations map to the German one, so a statute has one canonical name.
LAWS = {
    "UVG": "UVG", "LAA": "UVG", "LAINF": "UVG",
    "UVV": "UVV", "OLAA": "UVV", "OAINF": "UVV",
    "ATSG": "ATSG", "LPGA": "ATSG",
    "ATSV": "ATSV", "OPGA": "ATSV",
    "IVG": "IVG", "LAI": "IVG",
    "IVV": "IVV", "RAI": "IVV", "OAI": "IVV",
    "MVG": "MVG", "LAM": "MVG",
    "AHVG": "AHVG", "LAVS": "AHVG",
    "AHVV": "AHVV", "RAVS": "AHVV", "OAVS": "AHVV",
    "BVG": "BVG", "LPP": "BVG",
    "BVV 2": "BVV 2", "OPP 2": "BVV 2",
    "FZG": "FZG", "LFLP": "FZG",
    "KVG": "KVG", "LAMal": "KVG",
    "KVV": "KVV", "OAMal": "KVV",
    "KLV": "KLV", "OPAS": "KLV",
    "AVIG": "AVIG", "LACI": "AVIG", "LADI": "AVIG",
    "AVIV": "AVIV", "OACI": "AVIV", "OADI": "AVIV",
    "ELG": "ELG", "LPC": "ELG",
    "ELV": "ELV", "OPC-AVS/AI": "ELV",
    "EOG": "EOG", "LAPG": "EOG", "LIPG": "EOG",
    "FamZG": "FamZG", "LAFam": "FamZG", "LAFabb": "FamZG",
    "VVG": "VVG", "LCA": "VVG",
    "BGG": "BGG", "LTF": "BGG",
    "VGG": "VGG", "LTAF": "VGG",
    "BV": "BV", "Cst.": "BV", "Cost.": "BV",
    "OR": "OR", "CO": "OR",
    "ZGB": "ZGB", "CC": "ZGB",
    "ZPO": "ZPO", "CPC": "ZPO",
    "StGB": "StGB", "CP": "StGB",
    "StPO": "StPO", "CPP": "StPO",
    "SVG": "SVG", "LCR": "SVG",
    "VwVG": "VwVG", "PA": "VwVG",
    "EMRK": "EMRK", "CEDH": "EMRK", "CEDU": "EMRK",
}  # fmt: skip
LAW_ORDER = ["UVG", "UVV", "ATSG", "ATSV", "IVG", "IVV", "MVG"]
_LAW_NAMES = "|".join(
    re.escape(law).replace(r"\ ", r"\s*") for law in sorted(LAWS, key=len, reverse=True)
)

# A citation is "Art." and a chain of units joined by "und", "et", "i.V.m." etc., then the
# statute: "Art. 95 und 96 BGG", "art. 97 al. 2 et 105 al. 3 LTF", "Art. 72 f. UVG", "art. 15 ss
# LAA", "Art. 6 Abs. 1 des Bundesgesetzes über die Unfallversicherung (UVG)". A unit is an
# article and its parts (paragraphs, sentence, letters): "Art. 37 Abs. 2 lit. b und Abs. 3 lit. b".
# "bis" followed by a number is a range ("Art. 5 bis 7"), not the suffix of "Art. 5bis".
_SUFFIX = r"(?:bis|ter|quater|quinquies|sexies|septies|octies|novies|decies)\b"
_NUM = rf"\d+(?:[a-z]?\s*{_SUFFIX}(?!\s*\d)|[a-z]\b)?"
_AND = r"\s*(?:,|-|–)\s*|\s+(?:und|et|e)\s+"
_WITH = (
    r"\s+(?:i\.\s*V\.\s*m\.|in\s+Verbindung\s+mit|en\s+(?:relation|lien|corrélation)\s+avec|"
    r"in\s+(?:relazione|combinazione)\s+con|cum|par\s+renvoi\s+de)\s+"
)
_ORDINAL = (
    r"(?:\d+\s*(?:re|ère|ème|e|a)|première|deuxième|seconde|troisième|dernière|prima|seconda|"
    r"terza)"
)
_SENTENCE = (
    rf",?\s*(?:Satz\s*\d+|(?:erster|zweiter|dritter|letzter)\s+Satz|{_ORDINAL}\s+(?:phrase|phr\.|frase)"
    r"|(?:phrase|frase)\s+\d+)"
)
_PARA_WORD = r"(?:Abs\.|Absatz|al\.|cpv\.|para\.|par\.)"
_PARAS = (
    rf"{_PARA_WORD}\s*{_NUM}(?:(?:{_AND}|\s+(?:sowie|bzw\.)\s+)(?:{_PARA_WORD}\s*)?{_NUM}"
    rf"(?!\w)(?!\s*{_SUFFIX}|\s*(?:Abs|al|cpv|par)\.|\s*(?:re|ère|ème|e|a)?\s+(?:phrase|phr\.|frase)))*"
)
_LET_WORD = r"(?:lit\.|let\.|lett\.|Bst\.|Ziff\.|ch\.|n\.|cifra)"
_LETTER = rf"[a-z]{{1,3}}\b(?:\s*{_SUFFIX})?"
_LETTERS = (
    rf"{_LET_WORD}\s*(?:{_LETTER}(?:(?:{_AND})(?!{_PARA_WORD})(?:{_LET_WORD}\s*)?{_LETTER})*"
    rf"|\d+[a-z]?\b(?:(?:{_AND})(?:{_LET_WORD}\s*)?\d+[a-z]?\b(?!\s*(?:{_PARA_WORD}|{_LET_WORD})))*)"
)
# Letters can be followed by a number ("lit. b Ziff. 5"); only the letter is kept.
_PART = re.compile(
    rf"(?P<para>{_PARAS})?(?:{_SENTENCE})?"
    rf"(?:\s*(?P<let>{_LETTERS})(?:\s*{_LETTERS})?)?(?:{_SENTENCE})?"
)
_PART_PLAIN = re.sub(r"\(\?P<\w+>", "(?:", _PART.pattern)
_FF = (
    r"(?:\s*(?:ff\.?|f\.|ss\.?|s\.|segg\.|seg\.|sgg\.)(?![\wÀ-ÿ]))?"
    r"(?:\s+(?:e\s+contrario|in\s+fine|i\.\s*f\.)(?!\w))?"
)
_UNIT = re.compile(
    rf"(?P<art>{_NUM})(?P<parts>\s*{_PART_PLAIN}"
    rf"(?:(?:{_AND}|{_WITH})(?={_PARA_WORD}){_PART_PLAIN})*){_FF}"
)
_UNIT_PLAIN = re.sub(r"\(\?P<\w+>", "(?:", _UNIT.pattern)
_ARTICLE = r"\b(?:[Aa]rt(?:\.|t\.|ikel|icol[oi])|Artikel)\s*"
_SEP = (
    rf"(?:{_AND}|{_WITH}|\s*;\s*|\s*[,;]?\s+(?:und|et|e|sowie|bzw\.|resp\.|oder|ou|o|bis|à)\s+)"
    rf"(?:(?:l['’]|les\s+|all['’]|gli\s+)?{_ARTICLE})?"
)
_OF = r"\s+(?:des|der|de\s+la|de\s+l['’]|du|della|dello|dell['’]|del)"
# "/" rules out cantonal laws with the same abbreviation, e.g. "Cst./FR".
_CITATION = re.compile(
    rf"{_ARTICLE}(?P<chain>{_UNIT_PLAIN}(?:{_SEP}{_UNIT_PLAIN})*?)"
    rf"(?:(?:{_OF})?,?\s*(?P<law>{_LAW_NAMES})(?![\wÀ-ÿ/])"
    rf"|{_OF}\s*[^()\n]{{3,140}}?\(\s*(?P<long>{_LAW_NAMES})(?![\wÀ-ÿ/]))"
)
_NUMBER = re.compile(_NUM)
_LET_PREFIX = re.compile(rf"{_LET_WORD}\s*")


_CANONICAL = {re.sub(r"\s+", "", name): law for name, law in LAWS.items()}


def _canonical(law: str) -> str:
    return _CANONICAL[re.sub(r"\s+", "", law)]


def _number(value: str) -> str:
    return re.sub(r"\s+", "", value)


def statutes(text: str) -> list[dict[str, Any]]:
    """Articles cited in `text`, social insurance laws first, then by article number, e.g.
    {"law": "UVG", "art": "6", "count": 4, "details": [{"para": "2", "count": 3}]}.

    `count` is the number of citations naming the article; `details` the paragraphs ("para") and
    letters or numbers ("let": lit., let., Bst., Ziff., ch.) cited, when a citation names them.
    """
    articles: Counter[tuple[str, str]] = Counter()
    details: dict[tuple[str, str], Counter[tuple[str | None, str | None]]] = {}
    for match in _CITATION.finditer(text or ""):
        law = _canonical(match.group("law") or match.group("long"))
        cited: dict[str, set[tuple[str | None, str | None]]] = {}
        for unit in _UNIT.finditer(match.group("chain")):
            cells = cited.setdefault(_number(unit.group("art")), set())
            for part in _PART.finditer(unit.group("parts")):
                if not (part.group("para") or part.group("let")):
                    continue
                paras = [_number(p) for p in _NUMBER.findall(part.group("para") or "")] or [None]
                letters = re.split(_AND, _LET_PREFIX.sub("", part.group("let") or ""))
                # Letters belong to the last paragraph: "Abs. 1 und 2 lit. a" is Abs. 1 and
                # Abs. 2 lit. a.
                cells.update((para, None) for para in paras[:-1])
                cells.update((paras[-1], _number(let) or None) for let in letters)
        for art, cells in cited.items():
            articles[law, art] += 1
            details.setdefault((law, art), Counter()).update(cells)

    def rank(item: tuple[tuple[str, str], int]) -> tuple[int, str, int, str]:
        (law, art), _ = item
        order = LAW_ORDER.index(law) if law in LAW_ORDER else len(LAW_ORDER)
        return order, law, int(re.match(r"\d+", art).group()), art

    def number(value: str | None) -> tuple[int, str]:
        digits = re.match(r"\d+", value or "")
        return (int(digits.group()) if digits else -1), value or ""

    result = []
    for (law, art), n in sorted(articles.items(), key=rank):
        entry: dict[str, Any] = {"law": law, "art": art, "count": n}
        cells = sorted(details[law, art].items(), key=lambda c: (number(c[0][0]), number(c[0][1])))
        if cells:
            entry["details"] = [
                {k: v for k, v in (("para", para), ("let", let)) if v} | {"count": count}
                for (para, let), count in cells
            ]
        result.append(entry)
    return result


# "BGE 134 V 109", "ATF 141 V 281", "DTF 143 V 418"; further references in the same list follow
# without the prefix ("BGE 145 V 361 E. 4.1; 134 V 231"), so a bare one counts within 200
# characters of the previous reference.
_BGE = re.compile(
    r"\b(?P<prefix>(?:BGE|ATF|DTF)\s+)?(?P<volume>1[0-5]\d|[4-9]\d)\s+"
    r"(?P<part>Ia|Ib|II|III|IV|V|VI|I)\s+(?P<page>\d{1,4})\b"
)
_BGE_REACH = 200


def precedents(text: str) -> list[dict[str, Any]]:
    """Leading cases (BGE) cited in `text`, e.g. {"ref": "134 V 109", "count": 2}, oldest first."""
    counts: Counter[tuple[int, str, int]] = Counter()
    last = None
    for match in _BGE.finditer(text or ""):
        if not match.group("prefix") and (last is None or match.start() - last > _BGE_REACH):
            continue
        last = match.end()
        counts[int(match["volume"]), match["part"], int(match["page"])] += 1
    parts = ["I", "Ia", "Ib", "II", "III", "IV", "V", "VI"]
    return [
        {"ref": f"{volume} {part} {page}", "count": n}
        for (volume, part, page), n in sorted(
            counts.items(), key=lambda item: (item[0][0], parts.index(item[0][1]), item[0][2])
        )
    ]


def _any(*alternatives: str) -> re.Pattern[str]:
    return re.compile("|".join(alternatives), re.IGNORECASE)


_PARTLY = _any(
    r"teilweise\s+gutgeheissen",
    r"partiellement\s+admis",
    r"admise?\s+partiellement",
    r"parzialmente\s+accolto",
    r"accolto\s+parzialmente",
)
_UPHELD = _any(r"gutgeheissen", r"\badmise?\b", r"\baccolt[oa]\b")
_REMANDED = _any(r"zurückgewiesen", r"\brenvoy[ée]e?s?\b", r"\brinviat[oa]\b")
_NOT_ENTERTAINED = _any(
    r"nicht\s+eingetreten",
    r"n.(?:est|entre)\s+pas\s+(?:entré\s+)?en\s+matière",
    r"\birrecevables?\b",
    r"\binammissibil[ei]\b",
    r"non\s+(?:si\s+)?entra\s+nel\s+merito",
)
_STRUCK_OFF = _any(r"abgeschrieben", r"rayée?s?\s+du\s+rôle", r"stralciat[oa]", r"gegenstandslos")
_DISMISSED = _any(r"abgewiesen", r"\brejetée?s?\b", r"\brespint[oa]\b")
_OPERATIVE = re.compile(
    r"^[^\n]{0,60}\b(?:erkennt|prononce|pronuncia)\b[^\n]{0,40}:[ \t]*$",
    re.MULTILINE | re.IGNORECASE,
)
_ITEM = re.compile(r"^\s*\d+\.\s*$", re.MULTILINE)
_JOINDER = _any(r"vereinigt", r"\bjointes\b", r"\bcongiunte\b")
_COSTS = _any(r"kosten", r"parteientschädigung", r"\bfrais\b", r"dépens", r"\bspese\b")


def dispositive(text: str) -> list[str]:
    """The numbered items of the operative part ("1. Die Beschwerde wird abgewiesen.")."""
    matches = list(_OPERATIVE.finditer(text or ""))
    if not matches:
        return []
    items = _ITEM.split(text[matches[-1].end() :])
    return [" ".join(item.split()) for item in items[1:5]]


def outcome(text: str) -> Outcome | None:
    """The outcome of the appeal, read from the first item of the operative part.

    A remand counts when an item sends the case back for a new decision on the merits; one
    that only sends it back for a new decision on costs does not.
    """
    items = [item for item in dispositive(text) if not _JOINDER.search(item)]
    if not items:
        return None
    first = items[0]
    remanded = any(_REMANDED.search(i) and not _COSTS.search(i) for i in items[:2])
    if _PARTLY.search(first):
        return "remanded" if remanded else "partly_upheld"
    if _UPHELD.search(first):
        return "remanded" if remanded else "upheld"
    for pattern, result in [
        (_NOT_ENTERTAINED, "not_entertained"),
        (_STRUCK_OFF, "struck_off"),
        (_DISMISSED, "dismissed"),
    ]:
        if pattern.search(first):
            return result
    return None


_PANEL = re.compile(
    r"^(?:Besetzung|Composition|Composizione)\s*\n(.*?)"
    r"(?=Gerichtsschreiber|Greffi[eè]re?|Cancellier[ea]|^(?:Verfahrensbeteiligte|Participants|"
    r"Parti\b)|\Z)",
    re.MULTILINE | re.DOTALL,
)
_PANEL_TITLES = _any(
    r"\b(?:nebenamtliche[rn]?\s+)?Bundesrichter(?:in(?:nen)?)?\b",
    r"\bpräsidierendes\s+Mitglied\b",
    r"\bJuges?\s+suppléant(?:e|s)?\b",
    r"\bGiudic[ei]\s+supplent[ei]\b",
    r"\ble\b",
    r"\bla\b",
    r"\b(?:als\s+)?(?:Einzel|Instruktions)richter(?:in)?\b",
    r"\bGiudice\s+presidente\b",
    r"\bPräsident(?:in)?\b",
    r"\b(?:Mmes?|MM|M)\.?(?=\s)",
    r"\bet\b",
    r"\bles\b",
    r"\bJuges?\s+fédéra(?:ux|les?|l)\b",
    r"\bJuges?\s+présidan(?:t|te)\b",
    r"\bJuge\s+unique\b",
    r"\bPrésident(?:e)?\b",
    r"\bGiudic[ei]\s+federal[ei]\b",
    r"\bPresidente\b",
    r"\bGiudice\s+unic[oa]\b",
    r"\bund\b",
    r"\be\b",
)


def panel_size(text: str) -> int:
    """Number of judges in the "Besetzung" block of the rubrum (0 if not found)."""
    match = _PANEL.search(text[:5000])
    if not match:
        return 0
    names = _PANEL_TITLES.sub(",", match.group(1))
    return sum(1 for name in re.split(r"[,.;\n]", names) if re.search(r"[A-ZÀ-Ý]", name))


_PUBLIC = _any(
    r"öffentliche\s+Beratung\s+durch",
    r"öffentlich\s+beraten",
    r"in\s+öffentlicher\s+Sitzung",
    r"délibéré\s+(?:sur\s+.{0,80}?)?en\s+séance\s+publique",
    r"a\s+tenu\s+une\s+(?:séance|délibération)\s+publique",
    r"deliberazione\s+pubblica\s+che\s+si\s+è\s+tenuta",
    r"in\s+seduta\s+pubblica",
)
_CITED_FOR_PUBLICATION = re.compile(
    r"\b(\d[A-Z]_\d+/\d{4})\b[^;()]{0,120}?"
    r"(?:zur\s+Publikation\s+vorgesehen|destinée?\s+à\s+(?:la\s+)?publication|"
    r"destinata\s+alla\s+pubblicazione|prevista\s+per\s+la\s+pubblicazione)"
)


def cited_for_publication(conn: sqlite3.Connection) -> set[str]:
    """Dockets that rulings in the database cite as intended for the official reports.

    The mirror holds no publication marker, but later rulings cite pending leading cases as
    "Urteil 8C_123/2025 vom ..., zur Publikation vorgesehen".
    """
    rows = conn.execute(
        "SELECT text FROM rulings WHERE text LIKE '%Publikation vorgesehen%' "
        "OR text LIKE '%à la publication%' OR text LIKE '%alla pubblicazione%' "
        "OR text LIKE '%per la pubblicazione%'"
    )
    return {m.group(1) for row in rows for m in _CITED_FOR_PUBLICATION.finditer(row["text"])}


def facts(ruling: dict[str, Any], published: set[str] = frozenset()) -> Facts:
    text = ruling.get("text") or ""
    sections = triage.split_sections(text)
    flags = []
    if panel_size(text) >= 5:
        flags.append("five_judges")
    if _PUBLIC.search(sections.facts) or _PUBLIC.search(sections.operative):
        flags.append("public_deliberation")
    if ruling["docket"] in published:
        flags.append("publication")
    return Facts(
        subject=ruling.get("title") or triage.subject(text),
        statutes=statutes(text),
        precedents=precedents(text),
        outcome=outcome(text),
        flags=flags,
    )


# ---------------------------------------------------------------- subject-line classifier

_BRANCH_WORDS = [
    ("uv", _any(r"unfallversicher", r"assurance[s]?[- ]accidents?", r"infortuni")),
    ("mv", _any(r"militärversicher", r"assurance\s+militaire", r"assicurazione\s+militare")),
    ("iv", _any(r"invalidenversicher", r"assurance[- ]invalidité", r"per\s+l.invalidità")),
    (
        "atsg",
        _any(
            r"sozialversicher",
            r"assurances?\s+sociales?",
            r"assicurazion[ei]\s+social[ei]",
            r"\bAHV\b",
            r"\bAVS\b",
            r"alters-\s+und\s+hinterlassenen",
            r"vieillesse\s+et\s+survivants",
            r"krankenversicher",
            r"assurance[- ]maladie",
            r"assicurazione\s+malattia",
            r"arbeitslosenversicher",
            r"assurance[- ]chômage",
            r"assicurazione\s+contro\s+la\s+disoccupazione",
            r"berufliche\s+vorsorge",
            r"prévoyance\s+professionnelle",
            r"previdenza\s+professionale",
            r"ergänzungsleistung",
            r"prestations?\s+complémentaires?",
            r"prestazioni\s+complementari",
            r"erwerbsersatz",
            r"allocations?\s+pour\s+perte\s+de\s+gain",
            r"familienzulage",
            r"allocations?\s+familiales",
        ),
    ),
]

# Specific topics first: the first category whose words occur in the subject is the primary one.
_CATEGORY_WORDS: list[tuple[str, re.Pattern[str]]] = [
    (
        "unfallbegriff",
        _any(
            r"unfallbegriff",
            r"listenverletzung",
            r"unfallähnlich",
            r"notion\s+d.accident",
            r"lésions?\s+(?:corporelles?\s+)?assimilées?",
            r"nozione\s+d.infortunio",
            r"lesion[ei]\s+(?:corporal[ei]\s+)?parificabil[ei]",
        ),
    ),
    (
        "adaequate-kausalitaet",
        _any(
            r"adäquat",
            r"psychisch",
            r"schleudertrauma",
            r"adéquat",
            r"troubles?\s+psychiques?",
            r"traumatisme\s+cranio",
            r"coup\s+du\s+lapin",
            r"adeguat",
        ),
    ),
    ("berufskrankheit", _any(r"berufskrankheit", r"maladie[s]?\s+professionnelle", r"malattia")),
    (
        "integritaetsentschaedigung",
        _any(r"integritätsentschädigung", r"atteinte\s+à\s+l.intégrité", r"menomazione"),
    ),
    (
        "hilflosigkeit-pflege",
        _any(
            r"hilflos",
            r"pflege",
            r"assistenzbeitrag",
            r"impotent",
            r"\bsoins\b",
            r"contribution\s+d.assistance",
            r"grandi\s+invalidi",
            r"\bcure\b",
        ),
    ),
    (
        "natuerliche-kausalitaet",
        _any(
            r"natürliche[rn]?\s+kausal",
            r"causalité\s+naturelle",
            r"causalità\s+naturale",
            r"rückfall",
            r"spätfolge",
            r"rechute",
            r"séquelles?\s+tardives?",
            r"ricaduta",
            r"status\s+quo",
            r"statu\s+quo",
        ),
    ),
    (
        "rueckforderung-erlass",
        _any(
            r"rückforderung",
            r"rückerstattung",
            r"\berlass\b",
            r"restitution",
            r"remise\s+de\s+l.obligation",
            r"\bremise\b(?!\s+des\s+moyens)",
            r"restituzione",
            r"condono",
        ),
    ),
    (
        "unterstellung-praemien",
        _any(
            r"prämie",
            r"beitrag(?:s)?pflicht",
            r"beiträge",
            r"unterstellung",
            r"versicherteneigenschaft",
            r"versicherungsdeckung",
            r"\bprimes?\b",
            r"cotisations?",
            r"assujettissement",
            r"obligation\s+d.assurance",
            r"couverture\s+d.assurance",
            r"premi\b",
            r"contributi",
            r"assoggettamento",
        ),
    ),
    (
        "taggeld-leistungskuerzung",
        _any(
            r"taggeld",
            r"versicherte[rn]?\s+verdienst",
            r"gain\s+assuré",
            r"guadagno\s+assicurato",
            r"leistungskürzung",
            r"kürzung",
            r"wagnis",
            r"grobfahrlässig",
            r"indemnités?\s+journalières?",
            r"réduction",
            r"entreprise\s+téméraire",
            r"négligence\s+grave",
            r"indennità\s+giornalier",
            r"riduzion",
            r"mitwirkungspflicht",
            r"obligation\s+de\s+collaborer",
        ),
    ),
    (
        "koordination",
        _any(
            r"koordination",
            r"überentschädigung",
            r"vorleistung",
            r"komplementärrente",
            r"coordination",
            r"surindemnisation",
            r"rente\s+complémentaire",
            r"sovraindennizzo",
            r"coordinamento",
        ),
    ),
    (
        "regress-haftung",
        _any(
            r"regress",
            r"haftung",
            r"schadenersatz",
            r"verantwortlichkeit",
            r"demande\s+en\s+réparation",
            r"dommages[- ]intérêts",
            r"risarcimento",
            r"haftpflicht",
            r"responsabilité",
            r"action\s+récursoire",
            r"regresso",
            r"responsabilità",
        ),
    ),
    (
        "heilbehandlung",
        _any(
            r"heilbehandlung",
            r"heilungskosten",
            r"medizinische\s+massnahme",
            r"hilfsmittel",
            r"kostenübernahme",
            r"fallabschluss",
            r"traitement\s+médical",
            r"frais\s+de\s+traitement",
            r"mesures?\s+médicales?",
            r"moyens?\s+auxiliaires?",
            r"cura\s+medica",
            r"mezzi\s+ausiliari",
            r"provvedimenti\s+sanitari",
        ),
    ),
    (
        "beweis-gutachten",
        _any(
            r"gutacht",
            r"beweis",
            r"abklärung",
            r"expertise",
            r"\bpreuve",
            r"perizia",
            r"\bprova\b",
        ),
    ),
    (
        "rentenrevision",
        _any(
            r"(?<!prozessuale\s)revision(?!sgesuch)",
            r"neuanmeldung",
            r"révision(?!\s+procédurale)",
            r"nouvelle\s+demande",
            r"revisione",
            r"nuova\s+domanda",
        ),
    ),
    (
        "invaliditaetsgrad",
        _any(
            r"einkommensvergleich",
            r"invaliditätsbemessung",
            r"invaliditätsgrad",
            r"valideneinkommen",
            r"invalideneinkommen",
            r"leidensabzug",
            r"restarbeitsfähigkeit",
            r"verwertbarkeit",
            r"évaluation\s+de\s+l.invalidité",
            r"taux\s+d.invalidité",
            r"degré\s+d.invalidité",
            r"revenu\s+(?:sans\s+invalidité|d.invalide|d.invalidité|hypothétique)",
            r"comparaison\s+des\s+revenus",
            r"confronto\s+dei\s+redditi",
            r"grado\s+d.invalidità",
        ),
    ),
    (
        "verfahren",
        _any(
            r"prozessvoraussetzung",
            r"verfahren",
            r"rechtspflege",
            r"rechtsbeistand",
            r"rechtsverzögerung",
            r"rechtsverweigerung",
            r"parteientschädigung",
            r"kosten",
            r"\bfrist",
            r"gehör",
            r"wiedererwägung",
            r"prozessuale\s+revision",
            r"revisionsgesuch",
            r"noven",
            r"eröffnung",
            r"recevabilité",
            r"procédure",
            r"assistance\s+judiciaire",
            r"déni\s+de\s+justice",
            r"retard\s+injustifié",
            r"retrait\s+d[eu]\s+recours",
            r"dépens",
            r"\bfrais\b",
            r"\bdélai",
            r"droit\s+d.être\s+entendu",
            r"reconsidération",
            r"révision\s+procédurale",
            r"notification",
            r"presupposto\s+processuale",
            r"procedura",
            r"assistenza\s+giudiziaria",
            r"giustizia",
            r"spese",
            r"termine",
        ),
    ),
]
# Words that name the area rather than the issue: a causal link may be natural or adequate, and a
# pension dispute may be about anything. They only count after the specific words.
_GENERIC_WORDS = [
    ("natuerliche-kausalitaet", _any(r"kausal", r"causalit", r"nesso\s+causale")),
    (
        "invaliditaetsgrad",
        _any(r"invalidenrente", r"rente\s+d.invalidité", r"rendita\s+d.invalidità"),
    ),
]


def subject_categories(subject: str) -> tuple[list[str], list[str]]:
    """The categories the subject line names: specific ones first, then generic ones."""
    # The words in parentheses name the issue; outside them only the branch is named.
    issue = subject[subject.find("(") :] if "(" in subject else subject
    specific = [slug for slug, pattern in _CATEGORY_WORDS if pattern.search(issue)]
    generic = [s for s, pattern in _GENERIC_WORDS if pattern.search(issue) and s not in specific]
    return specific, generic


def subject_branch(subject: str) -> str | None:
    for branch, pattern in _BRANCH_WORDS:
        if pattern.search(subject):
            return branch
    return None


def classify_subject(ruling: dict[str, Any], facts_: Facts) -> Classification:
    """Branch and categories from the subject line ("Unfallversicherung (Kausalzusammenhang)").

    Without a matching word, the branch falls back to the statutes cited and the category to
    "Verfahren" for rulings not entertained or struck off, else "Andere" (method "rule").
    """
    subject = facts_.subject
    branch = subject_branch(subject) or _statute_branch(facts_.statutes)
    specific, generic = subject_categories(subject)
    found = [slug for slug in specific + generic if slug in MATRIX[branch]]
    method: Literal["subject", "rule"] = "subject"
    if not found:
        method = "rule"
        procedural = facts_.outcome in ("not_entertained", "struck_off")
        found = ["verfahren" if procedural else "andere"]
    return Classification(
        branch=branch,
        primary=found[0],
        secondary=found[1 : 1 + MAX_SECONDARY],
        statutes=facts_.statutes,
        precedents=facts_.precedents,
        outcome=facts_.outcome,
        flags=facts_.flags,
        method=method,
    )


def _statute_branch(cited: list[dict[str, Any]]) -> str:
    laws = Counter()
    for s in cited:
        laws[s["law"]] += s["count"]
    uv, iv, mv = laws["UVG"] + laws["UVV"], laws["IVG"] + laws["IVV"], laws["MVG"]
    social = sum(laws[law] for law in ("ATSG", "ATSV", "AHVG", "BVG", "KVG", "AVIG", "ELG"))
    best = max((uv, "uv"), (iv, "iv"), (mv, "mv"))
    if best[0] >= 3:
        return best[1]
    return "atsg" if social >= 3 else "other"


# ---------------------------------------------------------------- Apertus classifier


def _describe(labels: dict[str, Label]) -> str:
    return "\n".join(f"- {slug}: {label.de}" for slug, label in labels.items())


def _matrix() -> str:
    return "\n".join(
        f"- {branch}: {', '.join(c for c in CATEGORIES if c in allowed)}"
        for branch, allowed in MATRIX.items()
    )


SYSTEM_PROMPT = f"""\
Du bist Jurist im Rechtsdienst der Suva und ordnest Urteile des Bundesgerichts für die \
Rechtsprechungsdatenbank einer festen Kategorienliste zu.

1. Versicherungszweig (branch), nach dem Gesetz, das der Streit betrifft:
{_describe(BRANCHES)}
Für AHV, BVG, KVG, ALV, EL, Familienzulagen und die übrigen Sozialversicherungen gilt "atsg", \
auch wenn das ATSG nicht anwendbar ist. Private Versicherungen (VVG), Sozialhilfe, Steuern, \
Haftpflicht-, Zivil-, Straf- und übriges Verwaltungsrecht sind "other". Nennt der Gegenstand \
einen Zweig (unten als Hinweis angegeben), ist er der Versicherungszweig, auch wenn das Urteil \
nur eine Verfahrensfrage entscheidet. Betrifft ein Urteil Unfall- und Invalidenversicherung, \
entscheidet der Versicherer, gegen dessen Entscheid sich die Beschwerde richtet.

2. Rechtliche Kategorie: eine Hauptkategorie (primary) für die zentrale Rechtsfrage, die das \
Bundesgericht entscheidet, und höchstens zwei Nebenkategorien (secondary) für weitere \
entschiedene Fragen:
{_describe(CATEGORIES)}

Der Gegenstand im Rubrum benennt die Streitfrage, wie das Gericht sie sieht. Nennt er eine \
Kategorie (unten als Hinweis angegeben), ist sie in der Regel die Hauptkategorie; nennt er \
mehrere, wähle die, die das Bundesgericht hauptsächlich entscheidet. Weiche nur ab, wenn das \
Urteil eine andere Frage entscheidet, z.B. nur über das Eintreten.

Hinweise: "invaliditaetsgrad" umfasst Valideneinkommen, Invalideneinkommen, LSE-Tabellen, \
Leidensabzug und die Verwertbarkeit der Restarbeitsfähigkeit. "natuerliche-kausalitaet" umfasst \
Status quo sine/ante, Rückfall und Spätfolgen. Ob eine Listenverletzung nach Art. 6 Abs. 2 UVG \
vorliegt oder überwiegend auf Abnützung oder Erkrankung zurückgeht, ob ein ungewöhnlicher \
äusserer Faktor vorliegt und ob ein Suizid versichert ist (Art. 48 UVV), gehört zu \
"unfallbegriff", nicht zur Kausalität. Wird eine laufende Rente revidiert (Art. 17 ATSG) oder \
eine Neuanmeldung geprüft, ist "rentenrevision" die Hauptkategorie, auch wenn dabei der \
Invaliditätsgrad neu bemessen wird. "beweis-gutachten" nur, wenn das Urteil eine Frage \
zum Beweisrecht klärt (Beweiswert von Gutachten, Anforderungen an Abklärungen) und keine andere \
Kategorie die Streitfrage benennt: Medizinische Berichte würdigt fast jedes Urteil. \
"verfahren" nur, wenn das Urteil eine Verfahrensfrage entscheidet (Eintreten, Fristen, \
rechtliches Gehör, Kosten, unentgeltliche Rechtspflege, Revision eines Urteils); eine materielle \
Rechtsfrage geht vor. "andere" nur, wenn keine Kategorie passt.

Erlaubte Kategorien je Versicherungszweig:
{_matrix()}

Antworte nur mit einem JSON-Objekt:
{{"rationale": "<ein Satz auf Deutsch: welche Rechtsfrage das Bundesgericht entscheidet>", \
"branch": "<Zweig>", "primary": "<Kategorie>", "secondary": ["<Kategorie>", ...]}}"""

RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "classification",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "rationale": {"type": "string"},
                "branch": {"type": "string", "enum": list(BRANCHES)},
                "primary": {"type": "string", "enum": list(CATEGORIES)},
                "secondary": {
                    "type": "array",
                    "items": {"type": "string", "enum": list(CATEGORIES)},
                    "maxItems": MAX_SECONDARY,
                },
            },
            "required": ["rationale", "branch", "primary", "secondary"],
            "additionalProperties": False,
        },
    },
}


def build_messages(ruling: dict[str, Any], facts_: Facts) -> list[Message]:
    cited = ", ".join(f"Art. {s['art']} {s['law']}" for s in facts_.statutes[:12]) or "keine"
    hints = [f"Gegenstand laut Rubrum: {facts_.subject or 'nicht angegeben'}"]
    if branch := subject_branch(facts_.subject):
        hints.append(f"Vom Gegenstand genannter Zweig: {branch}")
    if named := subject_categories(facts_.subject)[0]:
        hints.append(f"Vom Gegenstand genannte Kategorie: {', '.join(named)}")
    hints.append(f"Meistzitierte Normen: {cited}")
    if facts_.outcome:
        hints.append(f"Ausgang: {OUTCOMES[facts_.outcome].de}")
    user = (
        f"Urteil {ruling['docket']} vom {ruling.get('decision_date') or '?'}\n"
        + "\n".join(hints)
        + f"\n\n{triage.excerpt(ruling.get('text') or '', EXCERPT_CHARS)}"
    )
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]


def validate(data: Any) -> tuple[str, str, list[str], str | None]:
    """Check a reply against the taxonomy; raises ValueError naming what is wrong."""
    if not isinstance(data, dict):
        raise ValueError(f"Erwartet wird ein JSON-Objekt, nicht {data!r}.")
    branch, primary = data.get("branch"), data.get("primary")
    if branch not in BRANCHES:
        raise ValueError(f'"branch" muss einer von {", ".join(BRANCHES)} sein, nicht {branch!r}.')
    if primary not in MATRIX[branch]:
        raise ValueError(
            f'"primary" {primary!r} ist für den Zweig "{branch}" nicht erlaubt; erlaubt sind '
            f"{', '.join(c for c in CATEGORIES if c in MATRIX[branch])}."
        )
    secondary = data.get("secondary") or []
    if not isinstance(secondary, list):
        secondary = [secondary]
    # Secondary labels that do not fit are dropped rather than retried: the primary carries the
    # classification, and a second round trip for a side label is not worth it.
    secondary = list(
        dict.fromkeys(s for s in secondary if s in MATRIX[branch] and s not in (primary, "andere"))
    )[:MAX_SECONDARY]
    rationale = " ".join(str(data.get("rationale") or "").split()) or None
    return branch, primary, secondary, rationale


def classify_llm(ruling: dict[str, Any], facts_: Facts, llm: LLMClient) -> Classification:
    """Classify with Apertus; after `MAX_ATTEMPTS` invalid replies, fall back to the subject."""
    messages = build_messages(ruling, facts_)
    for _ in range(MAX_ATTEMPTS):
        reply = llm.chat(messages, max_tokens=300, response_format=RESPONSE_FORMAT)
        try:
            branch, primary, secondary, rationale = validate(parse_json(reply))
        except ValueError as exc:  # json.JSONDecodeError is a ValueError too
            messages = [
                *messages,
                {"role": "assistant", "content": reply},
                {"role": "user", "content": f"Ungültige Antwort: {exc} Antworte erneut."},
            ]
            continue
        return Classification(
            branch=branch,
            primary=primary,
            secondary=secondary,
            statutes=facts_.statutes,
            precedents=facts_.precedents,
            outcome=facts_.outcome,
            flags=facts_.flags,
            method="llm",
            model=llm.model,
            rationale=rationale,
        )
    return classify_subject(ruling, facts_)


# The docket starts with the division: 8 and 9 are the two social-law divisions (IV. and III.
# öffentlich-rechtliche Abteilung). Registers in the corpus: 8C, 8F, 8G, 9C, 9D, 9F, 9G. Division 9
# also decides tax law; Apertus puts those rulings in "other".
SOCIAL_LAW_DIVISIONS = ("8", "9")


def classify_ruling(
    ruling: dict[str, Any], llm: LLMClient, published: set[str] = frozenset()
) -> Classification:
    """Apertus for rulings of the social-law divisions; every other ruling is "other"."""
    facts_ = facts(ruling, published)
    if ruling["docket"].startswith(SOCIAL_LAW_DIVISIONS):
        return classify_llm(ruling, facts_, llm)
    return Classification(
        branch="other",
        primary="andere",
        secondary=[],
        statutes=facts_.statutes,
        precedents=facts_.precedents,
        outcome=facts_.outcome,
        flags=facts_.flags,
        method="rule",
    )


def classify(conn: sqlite3.Connection, docket: str, llm: LLMClient) -> Classification:
    """Classify ruling `docket`. Does not persist."""
    ruling = db.get_ruling(conn, docket)
    if ruling is None:
        raise KeyError(docket)
    return classify_ruling(ruling, llm, cited_for_publication(conn))


def save(conn: sqlite3.Connection, docket: str, result: Classification) -> None:
    db.save_classification(conn, docket, **asdict(result), prompt_version=VERSION)


def classify_batch(
    conn: sqlite3.Connection, dockets: list[str], llm: LLMClient, workers: int = 8
) -> Iterator[tuple[str, Classification | Exception]]:
    """Classify many rulings with parallel LLM calls, yielding results as they complete.

    A failed ruling yields its exception instead of stopping the batch; rerunning picks it up.
    """
    published = cited_for_publication(conn)
    rulings = [db.get_ruling(conn, docket) for docket in dockets]
    with ThreadPoolExecutor(workers) as pool:
        futures = {
            pool.submit(classify_ruling, ruling, llm, published): ruling["docket"]
            for ruling in rulings
            if ruling is not None
        }
        for future in as_completed(futures):
            try:
                yield futures[future], future.result()
            except Exception as exc:
                yield futures[future], exc
