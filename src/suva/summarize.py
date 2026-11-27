"""German and French summaries of a ruling in Suva's house style (docs/style_guide.md).

Pipeline: cut the ruling down to its decisive parts (facts, reasons, operative part) and list
the Court's conclusions per consideration; write the summary in the ruling's language from the
ruling, with the evaluator's own summaries as style examples, and the other language from the
ruling with the first as outline; check each draft (rule checks plus a claim-by-claim model
check against the ruling), revise and shorten it; let the model compare the two languages and
fix contradictions; finally replace names by roles and make the closing sentence state the
operative part. A one-line headline per language is written from the extracted conclusions.
"""

import json
import re
import sqlite3
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, replace
from functools import cache
from pathlib import Path
from string import Template
from typing import NamedTuple

from suva import db
from suva.eval.examples import EXAMPLES_PATH, SPLIT_PATH, load_split, read_jsonl
from suva.eval.glossary import load_glossary
from suva.eval.metrics import citation_issues, contains_term, foreign_statutes, term_forms
from suva.llm import LLMClient, Message

# Pinned like classify.MODEL, whatever LLM_NAME says: the thinking variant wrote no better
# summaries.
MODEL = "apertus-v1-5-70b"
PROMPT_VERSION = "v2"
HEADLINE_VERSION = "v2"
LANGUAGES = ("de", "fr")
LANGUAGE_NAMES = {"de": "German", "fr": "French", "it": "Italian"}
PROMPTS_DIR = Path(__file__).parent / "prompts"

SOURCE_BUDGET = 70_000  # characters of ruling text sent to the model, about 20k tokens
FACTS_BUDGET = 8_000
CHUNK_SIZE = 40_000
# Villa Rebeca (VIL), who evaluates the summaries: her style anchors every prompt. Her third
# summary, 8C_613/2025, is in the evaluation hold-out and therefore not used.
STYLE_EXAMPLES = ("8C_7/2025", "8C_172/2025")
LENGTH = {"de": "150 to 200 words, about 180", "fr": "160 to 220 words, about 190"}
MAX_WORDS = {"de": 230, "fr": 250}
FIVE_JUDGES = {"de": "Fünfer-Entscheid.", "fr": "Décision à cinq."}
HEADLINE_WORDS = 12
# The prompt asks for 12 words; a remand on two points needs a few more, French more than German.
MAX_HEADLINE_WORDS = {"de": 15, "fr": 17}
HEADLINE_EXAMPLES = {
    "de": (
        "Keine analoge Anwendung von Art. 26bis IVV in der Unfallversicherung",
        "Psychische Beschwerden nach Auffahrunfall nicht adäquat kausal",
        "Rückweisung zur Einholung eines Gerichtsgutachtens zur Arbeitsfähigkeit",
    ),
    "fr": (
        "Pas d'application par analogie de l'art. 26bis RAI dans l'assurance-accidents",
        "Troubles psychiques après une collision par l'arrière sans causalité adéquate",
        "Renvoi pour une expertise judiciaire sur la capacité de travail",
    ),
}
# Function words that tell a German from a French headline.
_MARKERS = {
    lang: set(words.split())
    for lang, words in {
        "de": "der die das den dem und ein eine einer kein keine nicht von im in zur zum bei "
        "für auf mit nach",
        "fr": "le la les du de et un une pas au aux dans pour sur par l d en",
    }.items()
}

# Statute abbreviations: French and Italian forms mapped to the German one.
STATUTES = {
    "LAA": "UVG",
    "LAINF": "UVG",
    "OLAA": "UVV",
    "OAINF": "UVV",
    "LPGA": "ATSG",
    "OPGA": "ATSV",
    "LAI": "IVG",
    "RAI": "IVV",
    "OAI": "IVV",
    "LTF": "BGG",
    "LCA": "VVG",
    "LAMal": "KVG",
    "OPAS": "KLV",
    "LAVS": "AHVG",
    "LPP": "BVG",
    "Cst.": "BV",
    "CEDH": "EMRK",
    "CO": "OR",
    "CC": "ZGB",
    "LRCF": "VG",
}

SECTIONS = {
    "facts": r"(?:Sachverhalt|Faits|Fatti)\s*:",
    "reasons": r"(?:Erwägungen?|Considérant(?: en droit)?|(?:Considerando in )?[Dd]iritto)\s*:",
    "ruling": r"(?:Demnach erkennt|Par ces motifs|Per questi motivi)\b.*",
}
# Points of the operative part that a summary leaves out: costs, legal aid, notification.
_COSTS = (
    r"\n(?:\d+\.\n)?(?:\S+ ){0,3}(?:Gerichtskosten|Parteientschädigung|unentgeltliche"
    r"|Dieses Urteil wird|frais judiciaires|dépens|assistance judiciaire|présent arrêt est"
    r"|spese giudiziarie|ripetibili|gratuito patrocinio|Comunicazione)"
)
# Accident and health insurers other than Suva, which the summaries do not name.
_INSURERS = re.compile(
    r"\b(?:AXA|Allianz|Zurich|Zürich Versicherung|Helvetia|Generali|Mobiliar|Mobilière|Vaudoise"
    r"|Baloise|Bâloise|Basler|SWICA|CSS|Visana|Groupe Mutuel|Sanitas|Helsana|Concordia|Sympany"
    r"|Assura|Atupri|ÖKK|EGK|Elvia|Emmental|Solida)\b"
)
_PERSONAL = re.compile(
    r"\b(?:19|20)\d\d geboren|\bJahrgang (?:19|20)\d\d|\d+-jährig|\bnée? en (?:19|20)\d\d"
    r"|\bâgée? de \d+ ans"
)
_MONTHS = {
    month: number
    for names in (
        "januar februar märz april mai juni juli august september oktober november dezember",
        "janvier février mars avril mai juin juillet août septembre octobre novembre décembre",
        "gennaio febbraio marzo aprile maggio giugno luglio agosto settembre ottobre novembre"
        " dicembre",
    )
    for number, month in enumerate(names.split(), 1)
}
SUVA = (
    r"Suva|SUVA|\bCNA\b|Caisse nationale suisse|Unfallversicherungsanstalt|INSAI|Istituto nazionale"
)
# Who appealed: description for the prompt, German and French genitive (masculine, feminine)
# for the outcome sentence, and the pattern that names this party in a closing sentence.
APPELLANTS = {
    "suva": ("Suva", "der Suva", "de la Suva", r"(?:Beschwerde der|recours de la) Suva"),
    "insured": (
        "the insured person",
        ("des Versicherten", "der Versicherten"),
        ("de l'assuré", "de l'assurée"),
        r"Beschwerde de[rs] Versicherten|recours de l.assurée?",
    ),
    "iv": ("the IV office", "der IV-Stelle", "de l'office AI", r"IV-Stelle|office AI"),
    "insurer": (
        "an accident insurer other than Suva",
        "des Unfallversicherers",
        "de l'assureur-accidents",
        r"Beschwerde des Unfallversicherers|recours de l.assureur",
    ),
    "other": ("another party", "", "", ""),
}
# Anonymised names and initials: "A.________", "Dr. med. D.", "Dr D.", "B. SA".
_NAMES = re.compile(
    r"\b[A-Z]\._+|\b(?:Dr|Prof)\.? (?:med\. )?[A-Z]\.|\b[A-Z]\. ?(?:SA|AG|GmbH|Sàrl|Sagl)\b"
)
# Openings of a closing outcome sentence, and words that belong to costs, not to the outcome.
_OUTCOME_START = re.compile(
    r"\b(?:Letztlich|Im Ergebnis|En définitive|En conclusion|Das Bundesgericht (?:hiess|wies|trat)"
    r"|Le Tribunal fédéral (?:a admis|a rejeté|a partiellement|n'est pas entré|admet|rejette))\b"
)
_COSTS_WORDS = re.compile(
    r"unentgeltliche|Gerichtskosten|Parteientschädigung|assistance judiciaire|frais judiciaires"
    r"|dépens"
)
# Checked in this order: a partly upheld appeal also contains "upheld" and "dismissed" words.
OUTCOMES = {
    "partly upheld": r"teilweise gut|partiellement admis|admet partiellement|parzialmente accolto",
    "inadmissible": r"nicht eingetreten|tr[ia]tt?\b[^.]*\bnicht\b[^.]*\bein\b|irrecevable"
    r"|entré en matière|entre pas en matière|inammissibile",
    "upheld": r"gutgeheissen|(?:hiess|heisst)\b[^.]*\bgut\b|\badm(?:is|et)\b|\baccolto",
    "dismissed": r"abgewiesen|(?:wies|weist)\b[^.]*\bab\b|rejet(?:é|te)\b|respinto",
}
# A sentence in which the Federal Supreme Court decides the appeal, the Court first ("Das
# Bundesgericht weist die Beschwerde ... ab").
_COURT_DECIDES = re.compile(
    r"(?:(?:Das|das|Le|le) )?(?:Bundesgericht|Tribunal fédéral)\s+(?:\S+\s+){0,2}?"
    r"(?:weist|wies|heisst|hiess|tritt|trat|rejette|admet|a rejeté|a admis|a partiellement admis"
    r"|n'entre|n'est pas entré)\b[^.]*\."
)
# Statute and institution abbreviations of Italian rulings: German and French forms.
ITALIAN = {"LAINF": ("UVG", "LAA"), "OAINF": ("UVV", "OLAA"), "INSAI": ("Suva", "Suva")}
_BENCH_TITLES = re.compile(
    r"Bundesrichter\w*|Mmes?\b|MM?\.|les Juges fédéraux|Giudic[ei] federal[ei]|Präsident\w*"
    r"|Présidente?|Presidente|präsidierendes Mitglied|Juges? suppléant\w*|nebenamtlich\w*"
)


@dataclass(frozen=True)
class Case:
    """What every step needs to know about the ruling being summarised."""

    docket: str
    source: str  # the decisive parts of the ruling, as sent to the model
    appellant: str  # key of APPELLANTS
    feminine: bool  # grammatical gender of the appellant ("Beschwerdeführerin", "recourante")
    operative: str  # first point of the operative part
    result: str | None  # key of OUTCOMES
    suva_party: bool = False  # Suva is a party, so the summary may name it
    holdings: str = ""  # the Court's conclusions, consideration by consideration


class Result(NamedTuple):
    summaries: dict[str, str]  # by language; empty when only headlines were written
    headlines: dict[str, str]  # by language; a language without a valid headline is missing


def summarize(conn: sqlite3.Connection, docket: str, llm: LLMClient) -> Result:
    """Summaries and headlines of ruling `docket` in German and French. Does not persist."""
    ruling = db.get_ruling(conn, docket)
    if ruling is None:
        raise KeyError(f"Unknown ruling {docket}")
    return summarize_ruling(ruling, llm)


def save(conn: sqlite3.Connection, docket: str, result: Result, model: str) -> None:
    for lang, text in result.summaries.items():
        db.save_summary(
            conn, docket, lang=lang, text=text, model=model, prompt_version=PROMPT_VERSION
        )
    for lang, text in result.headlines.items():
        db.save_headline(
            conn, docket, lang=lang, text=text, model=model, prompt_version=HEADLINE_VERSION
        )


def summarize_batch(
    conn: sqlite3.Connection,
    dockets: list[str],
    llm: LLMClient,
    workers: int = 4,
    *,
    headlines_only: bool = False,
) -> Iterator[tuple[str, Result | Exception]]:
    """Summarise many rulings (or only write their headlines) in parallel, yielding results as
    they complete.

    A failed ruling yields its exception instead of stopping the batch; rerunning picks it up.
    """
    step = headline_ruling if headlines_only else summarize_ruling
    rulings = [db.get_ruling(conn, docket) for docket in dockets]
    with ThreadPoolExecutor(workers) as pool:
        futures = {pool.submit(step, ruling, llm): ruling["docket"] for ruling in rulings if ruling}
        for future in as_completed(futures):
            try:
                yield futures[future], future.result()
            except Exception as exc:
                yield futures[future], exc


def prepare_case(ruling: dict, sections: dict[str, str], llm: LLMClient) -> Case:
    operative = re.sub(r"\s+", " ", re.sub(r"^.*?\n1\.\n", "", sections["ruling"], flags=re.S))
    party, feminine = appellant(sections["header"])
    case = Case(
        docket=ruling["docket"],
        source=prepare_source(ruling, sections, llm),
        appellant=party,
        feminine=feminine,
        operative=operative,
        result=result(operative),
        suva_party=bool(re.search(SUVA, parties(sections["header"]))),
    )
    # Writing from a list of the Court's conclusions keeps the model from merging
    # considerations (8C_185/2025: "duty to notify violated" became "not violated").
    return replace(case, holdings=extract_holdings(llm, case))


def headline_ruling(ruling: dict, llm: LLMClient) -> Result:
    """Headlines only: the source and holdings steps plus one short call per language, the same
    calls a full summary makes first, so a later summary reuses them from the cache."""
    case = prepare_case(ruling, split_sections(ruling["text"]), llm)
    return Result({}, headlines(llm, case, ruling.get("title"), ruling["language"]))


def summarize_ruling(ruling: dict, llm: LLMClient) -> Result:
    docket = ruling["docket"]
    sections = split_sections(ruling["text"])
    case = prepare_case(ruling, sections, llm)
    titles = headlines(llm, case, ruling.get("title"), ruling["language"])

    # The ruling's own language first: that summary stays closest to the source and sets the
    # content; the other one is written from the ruling with it as outline.
    first = ruling["language"] if ruling["language"] in LANGUAGES else "de"
    order = [first, *(lang for lang in LANGUAGES if lang != first)]
    summaries: dict[str, str] = {}
    rules: dict[str, Message] = {}
    for lang in order:
        shots = few_shots(lang, docket)
        system: Message = {"role": "system", "content": instructions(case.source, shots, lang)}
        draft = generate(llm, case, system, lang, outline=summaries.get(first))
        # Checks and revisions see the rules only: with the examples in context the model
        # mixes them up with the ruling (it quoted an example as evidence from the ruling).
        rules[lang] = {"role": "system", "content": instructions(case.source, [], lang)}
        reviewed = review(llm, case, rules[lang], lang, draft)
        summaries[lang] = finish(llm, case, rules[lang], lang, reviewed)
    # The two languages are written apart, so where they disagree one of them is wrong.
    for lang, issues in consistency_issues(llm, case, summaries).items():
        revised = revise(llm, case, rules[lang], lang, summaries[lang], issues)
        summaries[lang] = finish(llm, case, rules[lang], lang, revised)
    # Suva flags five-judge rulings (questions of principle); the bench is in the header.
    five = five_judges(sections["header"])
    texts = {
        lang: clean(summaries[lang], lang) + (f"\n\n{FIVE_JUDGES[lang]}" if five else "")
        for lang in LANGUAGES
    }
    return Result(texts, titles)


def generate(
    llm: LLMClient, case: Case, system: Message, lang: str, *, outline: str | None = None
) -> str:
    task = (
        f"Write the {LANGUAGE_NAMES[lang]} summary of this ruling in Suva's house style, "
        f"{LENGTH[lang]}. The appeal to the Federal Supreme Court was lodged by "
        f"{APPELLANTS[case.appellant][0]}; the operative part reads: «{case.operative}» Output "
        "only the summary text."
    )
    if case.holdings:
        task += (
            "\n\nThe Court's conclusions, consideration by consideration (state them as the "
            f"Court does; the reasons above are authoritative):\n{case.holdings}"
        )
    if outline:
        task += (
            "\n\nCover the same points in the same order as this summary in the other "
            f"language, but write directly from the ruling in natural {LANGUAGE_NAMES[lang]} "
            "legal language with the terms and citation format above; do not translate it "
            f"word for word:\n\n{outline}"
        )
    messages = [system, {"role": "user", "content": f"{case.source}\n\n---\n{task}"}]
    return clean(llm.chat(messages, max_tokens=1500), lang)


def review(llm: LLMClient, case: Case, system: Message, lang: str, draft: str) -> str:
    """Check the draft against the house rules and the ruling, revise it, then trim it."""
    text = draft
    issues = form_issues(text, case, lang) + accuracy_issues(llm, case, system, text)
    # A second round only for what the rule checks still find after the first revision.
    for _ in range(2):
        if not issues:
            break
        text = revise(llm, case, system, lang, text, issues)
        issues = [i for i in form_issues(text, case, lang) if not i.startswith("The summary has")]
    for _ in range(2):
        words = len(text.split())
        if words <= MAX_WORDS[lang]:
            break
        task = (
            f"This summary has {words} words. Shorten it to {LENGTH[lang]}. Cut in this "
            "order: dates and amounts the result does not turn on, procedural history, the "
            "cantonal court's reasoning, repetitions. Keep the paragraphs separated by blank "
            "lines, the legal principles, the decisive reasons, the consideration references "
            f"and the closing outcome sentence. Output only the shortened {LANGUAGE_NAMES[lang]} "
            f"summary.\n\n{text}"
        )
        reply = llm.chat([system, {"role": "user", "content": task}], max_tokens=1500)
        shorter = clean(reply, lang)
        if (consideration_refs(text) and not consideration_refs(shorter)) or paragraphs(
            shorter
        ) < min(3, paragraphs(text)):
            break
        text = shorter
    return text or draft


def finish(llm: LLMClient, case: Case, system: Message, lang: str, text: str) -> str:
    """Last pass over every final text: rule checks, names, outcome sentence."""
    issues = [i for i in form_issues(text, case, lang) if not i.startswith("The summary has")]
    if issues:
        text = revise(llm, case, system, lang, text, issues)
    if names := sorted(set(_NAMES.findall(text))):
        task = (
            f"{case.source}\n\n---\nSummary:\n\n{text}\n\n---\nReplace each of these anonymised "
            f"names by the person's role as the ruling describes it: {', '.join(names)}. "
            "For example der Suvaarzt, der behandelnde Arzt, der Gutachter, der Versicherte / le "
            "médecin de la Suva, le médecin traitant, l'expert, l'assuré. Adjust articles and "
            "prepositions and change nothing else. Output only the summary."
        )
        reply = llm.chat([system, {"role": "user", "content": task}], max_tokens=1500)
        renamed = clean(reply, lang)
        if not _NAMES.search(renamed) and len(renamed.split()) >= 0.8 * len(text.split()):
            text = renamed
    return fix_outcome(fix_court_sentences(text, case, lang), case, lang)


def contradicts(sentence: str, case: Case) -> bool:
    """Whether a sentence decides the appeal otherwise than the operative part, or decides the
    appeal of a party that did not appeal."""
    other_party = any(
        re.search(pattern, sentence)
        for key, (*_, pattern) in APPELLANTS.items()
        if key != case.appellant and pattern
    )
    return bool(case.result) and (result(sentence) not in (None, case.result) or other_party)


def fix_court_sentences(text: str, case: Case, lang: str) -> str:
    """Replace a sentence that opens with the Court deciding the appeal wrongly by the operative
    part: the revisions did not reliably remove "Das Bundesgericht weist die Beschwerde des
    Versicherten ab" from a summary of Suva's upheld appeal (8C_254/2025)."""
    expected = outcome_sentence(case, lang)
    if not expected:
        return text
    stated = re.sub(r"^Letztlich (\S+) das Bundesgericht", r"Das Bundesgericht \1", expected)
    stated = stated.replace("En définitive, le", "Le")
    for sentence in _COURT_DECIDES.findall(text):
        if sentence[0].isupper() and contradicts(sentence, case):
            text = text.replace(sentence, stated)
    return text


def paragraphs(text: str) -> int:
    return len([p for p in text.split("\n\n") if p.strip()])


def fix_outcome(text: str, case: Case, lang: str) -> str:
    """Make the closing sentence state the operative part; the model sometimes copies the
    outcome of an example ("die Beschwerde der Suva wird abgewiesen") or mixes verbs."""
    expected = outcome_sentence(case, lang)
    if not expected:
        return text
    last = text.rfind("\n\n") + 2 if "\n\n" in text else 0
    starts = [m.start() for m in _OUTCOME_START.finditer(text, last)]
    start = starts[-1] if starts and len(text[starts[-1] :].split()) <= 60 else None
    closing = text[start:] if start is not None else text[last:]
    other_party = any(
        re.search(pattern, closing)
        for key, (*_, pattern) in APPELLANTS.items()
        if key != case.appellant and pattern
    )
    if result(closing) == case.result and not other_party and not _COSTS_WORDS.search(closing):
        return text
    kept = text[:start].rstrip() if start is not None else text.rstrip()
    return f"{kept}\n\n{expected}" if kept else expected


def outcome_sentence(case: Case, lang: str) -> str | None:
    if case.result is None:
        return None
    party = APPELLANTS[case.appellant][1 if lang == "de" else 2]
    party = party[case.feminine] if isinstance(party, tuple) else party
    remand = remanded(case.operative)
    if lang == "de":
        appeal = f"die Beschwerde {party}".strip()
        verbs = {
            "upheld": f"hiess das Bundesgericht {appeal} gut",
            "partly upheld": f"hiess das Bundesgericht {appeal} teilweise gut",
            "dismissed": f"wies das Bundesgericht {appeal} ab",
            "inadmissible": f"trat das Bundesgericht auf {appeal} nicht ein",
        }
        tail = " und wies die Sache zur neuen Entscheidung zurück" if remand else ""
        return f"Letztlich {verbs[case.result]}{tail}."
    appeal = f"le recours {party}".strip()
    verbs = {
        "upheld": f"a admis {appeal}",
        "partly upheld": f"a partiellement admis {appeal}",
        "dismissed": f"a rejeté {appeal}",
        "inadmissible": f"n'est pas entré en matière sur {appeal}",
    }
    tail = " et renvoyé la cause pour nouvelle décision" if remand else ""
    return f"En définitive, le Tribunal fédéral {verbs[case.result]}{tail}."


def remanded(operative: str) -> bool:
    return bool(re.search(r"zurückgewiesen|renvoyée?|rinviata", operative))


def revise(
    llm: LLMClient, case: Case, system: Message, lang: str, draft: str, issues: list[str]
) -> str:
    listed = "\n".join(f"- {issue}" for issue in issues)
    task = (
        f"Draft summary:\n\n{draft}\n\n---\nA check of the draft against the ruling and the "
        f"house style found these problems:\n{listed}\n\nRewrite the draft, fixing these "
        "problems where the ruling supports the fix and keeping everything else. Output only "
        f"the revised {LANGUAGE_NAMES[lang]} summary text."
    )
    messages = [system, {"role": "user", "content": f"{case.source}\n\n---\n{task}"}]
    return clean(llm.chat(messages, max_tokens=1500), lang) or draft


def consistency_issues(llm: LLMClient, case: Case, summaries: dict[str, str]) -> dict[str, list]:
    """Contradictions between the German and the French summary, by the language that is wrong."""
    task = (
        f"{case.source}\n\n---\nGerman summary:\n\n{summaries['de']}\n\n---\nFrench summary:"
        f"\n\n{summaries['fr']}\n\n---\n{prompt('summary_consistency')}"
    )
    try:
        reply = llm.chat_json([{"role": "user", "content": task}], max_tokens=3000)
    except ValueError:
        return {}
    contradictions = reply.get("contradictions") if isinstance(reply, dict) else None
    issues: dict[str, list] = {}
    for c in contradictions or []:
        if not isinstance(c, dict):
            continue
        for lang in LANGUAGES:
            if c.get("wrong") in (lang, "both"):
                issues.setdefault(lang, []).append(
                    f'"{c.get(lang, "")}" contradicts the other language; the ruling: '
                    f'"{c.get("ruling", "")}"; fix: {c.get("fix", "")}'
                )
    return issues


def extract_holdings(llm: LLMClient, case: Case) -> str:
    task = f"{case.source}\n\n---\n{prompt('summary_holdings')}"
    return llm.chat([{"role": "user", "content": task}], max_tokens=1500).strip()


def headlines(llm: LLMClient, case: Case, subject: str | None, language: str) -> dict[str, str]:
    """Headlines in the ruling's language first, then the other with the first as reference,
    so that both state the same point."""
    first = language if language in LANGUAGES else "de"
    result: dict[str, str] = {}
    for lang in [first, *(lang for lang in LANGUAGES if lang != first)]:
        if text := headline(llm, case, subject, lang, reference=result.get(first)):
            result[lang] = text
    return result


def headline(
    llm: LLMClient, case: Case, subject: str | None, lang: str, *, reference: str | None = None
) -> str | None:
    """One line saying what the Court decided, written in `lang` from the holdings; None when
    the model gives no valid headline after two corrections."""
    task = Template(prompt("headline")).substitute(
        language=LANGUAGE_NAMES[lang],
        words=HEADLINE_WORDS,
        examples="\n".join(f"- {example}" for example in HEADLINE_EXAMPLES[lang]),
    )
    if reference:
        task += (
            f"\n\nState the same point as this headline in the other language, in your own "
            f"{LANGUAGE_NAMES[lang]} wording: {reference}"
        )
    if terms := terminology(case.source, lang):
        task += f"\n\nTerminology (German - French), use the {LANGUAGE_NAMES[lang]} form:\n{terms}"
    # The outcome spelled out: from "a remand is superfluous" in the holdings the model
    # wrote a remand headline for a dismissed appeal (8C_344/2025).
    outcome = (
        f"the appeal by {APPELLANTS[case.appellant][0]} was "
        f"{case.result or 'decided as in the operative part'}; "
        + ("the case is remitted" if remanded(case.operative) else "no remand")
    )
    context = (
        f"Subject: {subject or 'unknown'}\nOperative part: «{case.operative}»\nOutcome: "
        f"{outcome}\n\nThe Court's conclusions, consideration by consideration:\n{case.holdings}"
    )
    request = f"{context}\n\n---\n{task}"
    for attempt in range(3):
        messages: list[Message] = [{"role": "user", "content": request}]
        # Some sampling on the corrections: at temperature 0 the model kept the same draft.
        reply = llm.chat(messages, max_tokens=100, temperature=0.4 if attempt else 0.0)
        text = clean_headline(reply, lang)
        issues = headline_issues(text, lang)
        if not issues:
            return text
        # A fresh request rather than a follow-up turn: in a conversation the model repeated
        # its overlong headline unchanged.
        listed = "\n".join(f"- {issue}" for issue in issues)
        request = (
            f"{context}\n\n---\n{task}\n\nThis draft headline breaks the rules:\n{text}\n"
            f"Problems:\n{listed}\nWrite a new headline of at most {HEADLINE_WORDS} words."
        )
    return None


def clean_headline(text: str, lang: str) -> str:
    lines = [line for line in clean(text, lang).splitlines() if line.strip()]
    line = lines[0] if lines else ""
    line = re.sub(
        r"^(?:Headline|Schlagzeile|Titel|Titre|(?:Das |Le )?(?:Bundesgericht|Tribunal fédéral)"
        r"(?: bestätigt| confirme)?)\s*:\s*",
        "",
        line,
        flags=re.I,
    )
    # One paragraph number goes; with several ("Art. 10 Abs. 1 und Abs. 5") the rest would
    # read as a list of articles.
    if len(re.findall(r" (?:Abs|al)\. \d+\b", line)) == 1:
        line = re.sub(r" (?:Abs|al)\. \d+\b", "", line)
    # "Zurückweisung" is a rejection; a remand is a "Rückweisung".
    line = re.sub(r"^Zurückweisung zur\b", "Rückweisung zur", line)
    line = _HEADLINE_DATE.sub("", line)
    line = line[:1].upper() + line[1:]
    return line.strip(" \t\"'«»“”„").rstrip(".").strip()


# A date with the preposition that introduces it ("über den 30. November 2023 hinaus", "au-delà
# du 30 novembre 2023"): the model kept such dates through every correction.
_HEADLINE_DATE = re.compile(
    r"\s*(?:(?:über|ab|per|seit|bis|nach|vom|zum|am|au-delà du|à partir du|dès le|depuis le"
    r"|jusqu'au|au|du|le)\s+)?(?:den\s+|dem\s+)?\d{1,2}(?:\.|er)?\s*(?:"
    + "|".join(_MONTHS)
    + r")\s+\d{4}(?:\s+hinaus)?",
    re.I,
)


def headline_issues(text: str, lang: str) -> list[str]:
    if not text:
        return ["The headline is empty."]
    issues = []
    words = len(text.split())
    if words > MAX_HEADLINE_WORDS[lang]:
        issues.append(
            f"The headline has {words} words; use at most {HEADLINE_WORDS}: keep the legal "
            "point and drop the rest (the confirmation of a decision, paragraph numbers)."
        )
    if re.match(r"(?:Das |Le )?(?:Bundesgericht|Tribunal fédéral)\b", text):
        issues.append("State the decision itself; do not start with the Court.")
    if re.search(r"\b\d{1,2}[A-Z]_\d+/\d{4}\b", text):
        issues.append("Remove the docket number.")
    if any(re.fullmatch(r"\d{4}-\d\d-\d\d", f) for f in figures(text)) or re.search(
        r"\b\d{1,2}\.\d{1,2}\.\d{4}\b", text
    ):
        issues.append("Remove the date.")
    if names := _NAMES.findall(text):
        issues.append(f"Remove the anonymised names ({', '.join(sorted(set(names)))}).")
    tokens = re.findall(r"[a-zà-ÿ]+", text.lower())
    other = "fr" if lang == "de" else "de"
    if sum(t in _MARKERS[other] for t in tokens) > sum(t in _MARKERS[lang] for t in tokens):
        issues.append(f"Write the headline in {LANGUAGE_NAMES[lang]}.")
    return issues + term_issues(text, lang)


def parties(header: str) -> str:
    """The parties block of the rubrum."""
    match = re.search(
        r"(?:Verfahrensbeteiligte|Participants à la procédure|Partecipanti al procedimento)\n"
        r"(.*?)\n(?:Gegenstand|Objet|Oggetto)\n",
        header,
        re.S,
    )
    return match.group(1) if match else ""


def appellant(header: str) -> tuple[str, bool]:
    """Who appealed to the Federal Supreme Court (key of APPELLANTS) and whether the role is
    feminine, from the parties block of the header."""
    match = re.search(
        r"(?:Verfahrensbeteiligte|Participants à la procédure|Partecipanti al procedimento)\n"
        r"(.*?)\n(Beschwerdeführer\w*|recourante?|ricorrente)",
        header,
        re.S,
    )
    if not match:
        return "other", False
    party, role = match.group(1), match.group(2)
    # Italian "ricorrente" has no gender; the participle of the representation has.
    feminine = role in ("Beschwerdeführerin", "recourante") or bool(
        re.search(r"\b(?:patrocinata|rappresentata)\b", party)
    )
    if re.search(SUVA, party):
        return "suva", feminine
    if re.search(r"IV-Stelle|assurance-invalidité|Office AI|assicurazione per l'invalidità", party):
        return "iv", feminine
    if re.match(r"[A-Z]\._+", party):
        return "insured", feminine
    if re.search(r"Versicherung|Assurance|Assicurazion|Accidents|\bAG\b|\bSA\b|\bSE\b", party):
        return "insurer", feminine
    return "other", feminine


def result(text: str) -> str | None:
    """Outcome category of an operative part or of a summary's closing sentence."""
    for category, pattern in OUTCOMES.items():
        if re.search(pattern, text, re.I):
            return category
    return None


def form_issues(draft: str, case: Case, lang: str) -> list[str]:
    """House rules that can be checked without the model."""
    source = case.source
    issues = []
    words = len(draft.split())
    if words > MAX_WORDS[lang]:
        issues.append(
            f"The summary has {words} words; cut it to {LENGTH[lang]} by dropping procedural "
            "history, secondary facts and repetitions, keeping the holdings and the outcome."
        )
    if paragraphs(draft) < 3 and words > 120:
        issues.append(
            "Separate the paragraphs with blank lines: facts, cantonal court, Federal Supreme "
            "Court, outcome."
        )
    cited = consideration_refs(draft)
    if not cited:
        example = "(E. 4.2)" if lang == "de" else "(consid. 4.2)"
        issues.append(
            f"Cite the consideration in brackets after each key holding, e.g. {example}, "
            "using the numbering of the ruling's reasons."
        )
    numbered = set(re.findall(r"(?:^|E\.\s*|consid\.\s*)(\d+(?:\.\d+)*)", source, re.M))
    issues += [
        f"Consideration {ref} does not exist in the ruling; correct or remove the reference."
        for ref in sorted(cited - numbered)
    ]
    issues += [
        f"The ruling does not cite art. {ref.split()[1]} {ref.split()[0]}; correct or remove it."
        for ref in sorted(statute_refs(draft) - statute_refs(source))
    ]
    if re.search(r"\b(?:BGE|ATF|DTF)\s+\d+\s+[IV]+", draft):
        issues.append("Remove the BGE/ATF citations and state the rule itself.")
    if names := _NAMES.findall(draft):
        issues.append(
            f"Remove the anonymised names ({', '.join(sorted(set(names)))}); refer to the "
            "person by role (insured person, Suva doctor, treating doctor, expert)."
        )
    if re.search(r"\bSuva\b", draft) and not case.suva_party:
        issues.append(
            "Suva is not a party to this ruling; refer to the insurer by its role "
            "(the accident insurer, the IV office)."
        )
    issues += [
        f'"{sentence}" contradicts the operative part: «{case.operative}»'
        for sentence in _COURT_DECIDES.findall(draft)
        if contradicts(sentence, case)
    ]
    if insurers := set(_INSURERS.findall(draft)):
        issues.append(
            f"Do not name the insurer ({', '.join(sorted(insurers))}); only Suva is named, "
            "other insurers are the accident insurer or the IV office."
        )
    if personal := _PERSONAL.findall(draft):
        issues.append(f"Remove the personal details ({', '.join(personal)}).")
    issues += [
        f"The figure or date {figure} does not appear in the ruling; correct or remove it."
        for figure in sorted(figures(draft) - figures(source))
    ]
    return issues + term_issues(draft, lang)


def term_issues(text: str, lang: str) -> list[str]:
    """The other language's statute abbreviations and terms, the glossary's avoid list and the
    citation format."""
    glossary = _glossary()
    issues = [
        f"Use the {LANGUAGE_NAMES[lang]} abbreviation instead of {abbr}."
        for abbr in foreign_statutes(text, glossary, lang)
    ]
    issues += [f"Citation format: {problem}." for problem in citation_issues(text, lang)]
    issues += [
        f'Do not use "{form}"; use "{term[lang]}".'
        for term in glossary["terms"]
        for form in term.get(f"{lang}_avoid", [])
        if contains_term(text, [form])
    ]
    other = "fr" if lang == "de" else "de"
    issues += [
        f'"{form}" is the {LANGUAGE_NAMES[other]} term; use "{term[lang]}".'
        for term in glossary["terms"]
        for form in term_forms(term, other)
        if form not in term_forms(term, lang) and contains_term(text, [form])
    ]
    return issues


def figures(text: str) -> set[str]:
    """Percentages, amounts and dates, normalised so that DE, FR and IT spellings compare."""
    found = {
        f"{n.replace(',', '.')} %"
        for n in re.findall(r"(\d+(?:[.,]\d+)?)\s?(?:%|Prozent|pour cent|per cento)", text)
    }
    amount = r"\d{1,3}(?:['’ ]?\d{3})*(?:[.,]\d{2})?"
    for before, after in re.findall(
        rf"(?:CHF|Fr\.|fr\.)\s?({amount})|({amount})\s?(?:CHF|Fr\.|fr\.|francs|Franken)", text
    ):
        found.add("CHF " + re.sub(r"['’ ]", "", before or after).replace(",", "."))
    for day, month, year in re.findall(r"\b(\d{1,2})(?:\.|er|°)?\s+([^\W\d_]+)\s+(\d{4})", text):
        if month.lower() in _MONTHS:
            found.add(f"{year}-{_MONTHS[month.lower()]:02d}-{int(day):02d}")
    return found


def accuracy_issues(llm: LLMClient, case: Case, system: Message, draft: str) -> list[str]:
    """Let the model verify the draft claim by claim against the ruling, quoting its evidence."""
    check = f"{case.source}\n\n---\nDraft summary:\n\n{draft}\n\n---\n{prompt('summary_check')}"
    try:
        reply = llm.chat_json([system, {"role": "user", "content": check}], max_tokens=3000)
    except ValueError:
        return []
    claims = reply.get("claims") if isinstance(reply, dict) else None
    return [
        f'"{c.get("draft", "")}" is not supported; the ruling: "{c.get("ruling", "")}"; '
        f"fix: {c.get('fix', '')}"
        for c in claims or []
        if isinstance(c, dict) and c.get("supported") is False
    ]


def instructions(source: str, shots: list[tuple[str, str]], lang: str) -> str:
    parts = [
        Template(prompt("summary_style")).substitute(length=LENGTH[lang]),
        prompt(f"summary_{lang}"),
    ]
    if terms := terminology(source, lang):
        parts.append(
            "Terminology - use these terms of the summary's language "
            "(German - French; avoid the forms marked as such):\n" + terms
        )
    if shots:
        listed = "\n\n".join(
            f"Example {i} ({docket}):\n{text}" for i, (docket, text) in enumerate(shots, 1)
        )
        parts.append(
            "Summaries Suva's lawyers wrote for other rulings. Match their structure, citations "
            f"and terminology, not their content or length:\n\n{listed}"
        )
    return "\n\n".join(parts)


def terminology(source: str, lang: str) -> str:
    """Glossary entries whose German or French form occurs in the ruling."""
    glossary = _glossary()
    lines = [
        f"- {s['de']} - {s['fr']}"
        for s in glossary["statutes"]
        if contains_term(source, [s["de"]]) or contains_term(source, [s["fr"]])
    ]
    for term in glossary["terms"]:
        if contains_term(source, term_forms(term, "de")) or contains_term(
            source, term_forms(term, "fr")
        ):
            avoid = term.get(f"{lang}_avoid")
            lines.append(
                f"- {term['de']} - {term['fr']}"
                + (f" (avoid: {', '.join(avoid)})" if avoid else "")
            )
    return "\n".join(lines)


@cache
def _glossary() -> dict:
    return load_glossary()


@cache
def prompt(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8").strip()


def clean(text: str, lang: str) -> str:
    text = re.sub(r"[­​‌‍﻿]", "", text)
    text = re.sub(r"\*\*|^#+\s*", "", text.strip(), flags=re.M)
    text = re.sub(r"^(Zusammenfassung|Résumé|Summary)\s*(\([^)]*\))?\s*:\s*", "", text, flags=re.I)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(
        r"\s*(Fünfer-Entscheid|Décision à cinq|Arrêt (rendu )?à cinq juges)\.?\s*$", "", text
    )
    text = re.sub(r"\b(\d{1,3}(?:'\d{3})*) fr\. (\d{2})\b", r"CHF \1.\2", text)
    text = re.sub(r"\b(\d{1,3}(?:'\d{3})*) fr\.(?=[\s,;)])", r"CHF \1.-", text)
    text = re.sub(r"\bFr\. (?=\d)", "CHF ", text)
    # Suva's summaries always say Suva, also where French rulings say CNA (Italian: INSAI).
    text = re.sub(r"\bCNA\b", "Suva", text)
    text = re.sub(r"\b([Ll])['’]INSAI\b", lambda m: f"{m[1]}a Suva", text)
    text = re.sub(r"\b(?:LAINF|OAINF|INSAI)\b", lambda m: ITALIAN[m[0]][lang == "fr"], text)
    # OAI is the Italian IVV, but in French also the IV office, so only after an article number.
    text = re.sub(
        r"(\d\w*(?:\s+(?:Abs|al|cpv)\.\s*\d+)*(?:\s+(?:lit|let|Bst)\.\s*\w+)?\s+)OAI\b",
        rf"\1{'RAI' if lang == 'fr' else 'IVV'}",
        text,
    )
    # An anonymised place or employer goes without its preposition ("in U.________").
    text = re.sub(r" (?:in|bei|à|chez|auprès de) [A-Z]\._+", "", text)
    # Names in apposition or brackets go without touching the grammar ("der Suvaarzt,
    # Dr. med. D., hielt fest"); others are replaced by the person's role in `finish`.
    text = re.sub(
        r" \((?:Dr\.?|Prof\.) (?:med\. )?[A-Z]\.\)|, (?:Dr\.?|Prof\.) (?:med\. )?[A-Z]\.,", "", text
    )
    # Birth years are personal details the summaries never give.
    text = re.sub(r"\b(?:19|20)\d\d geboren\w* (?=[A-ZÄÖÜ])", "", text)
    text = re.sub(r"(?:, née? en (?:19|20)\d\d,| née? en (?:19|20)\d\d)(?=[,. ])", "", text)
    if lang == "de":
        # "Der Dachdecker A. rutschte": an initial after a noun (five letters or more, so never
        # after an article: "Der A.________ erhielt" is left to `finish`).
        text = re.sub(r"\b([A-ZÄÖÜ][a-zäöüß]{4,}) [A-Z]\.(?= [a-zäöü])", r"\1", text)
        # "wies die Beschwerde ... gut" mixes up "hiess ... gut" and "wies ... ab".
        text = re.sub(r"\bwies\b([^.]*?)\bgut\b", r"hiess\1gut", text)
        text = re.sub(r"\b(?:consid|Erw)\. ?(?=\d)", "E. ", text)
        text = text.replace("ß", "ss")
        text = re.sub(r"\blit\. (?=[a-z]{1,4}\b)", "Bst. ", text)
        text = re.sub(r"\bart\. (?=\d)", "Art. ", text)
    else:
        text = re.sub(r"(?<![\w.])(?:E|Erw)\. ?(?=\d)", "consid. ", text)
        text = re.sub(r"(?:(?<=[a-zà-ÿ,;] )|(?<=['’]))Art\. (?=\d)", "art. ", text)
    return text.strip()


def consideration_refs(text: str) -> set[str]:
    return set(re.findall(r"\b(?:E\.|Erw\.|consid\.)\s*(\d+(?:\.\d+)*)", text))


_ART = re.compile(
    r"\bart\.?\s*(\d+[a-z]?)(?:\s*(?:abs\.|al\.|cpv\.)\s*\d+)?"
    r"(?:\s*(?:lit\.|let\.|bst\.|ziff\.|par\.)\s*\w+)?(?:\s*(?:und|et|e|bis|ss|ff\.?)\s*\d*)?\s+("
    + "|".join(re.escape(s) for s in sorted({*STATUTES, *STATUTES.values()}, key=len, reverse=True))
    + r")(?!\w)",
    re.I,
)
_CANON = {k.lower(): v for k, v in STATUTES.items()} | {v.lower(): v for v in STATUTES.values()}


def statute_refs(text: str) -> set[str]:
    """Statute articles cited in `text`, language-neutral ("UVG 6")."""
    return {f"{_CANON[law.lower()]} {number}" for number, law in _ART.findall(text)}


# --- Source extraction ---------------------------------------------------------------------


def split_sections(text: str) -> dict[str, str]:
    """Split a ruling into header, facts, reasons and operative part ("ruling")."""
    text = re.sub(r"\n\s*\n+", "\n", text)
    bounds = {}
    pos = 0
    for name, pattern in SECTIONS.items():
        if match := re.compile(rf"^{pattern}$", re.M).search(text, pos):
            bounds[name] = match.start()
            pos = match.end()
    if "reasons" not in bounds:
        return {"header": "", "facts": "", "reasons": text.strip(), "ruling": ""}
    starts = sorted(bounds.items(), key=lambda item: item[1])
    sections = {"header": text[: starts[0][1]], "facts": "", "ruling": ""}
    for (name, start), (_, end) in zip(starts, [*starts[1:], ("end", len(text))], strict=True):
        sections[name] = text[start:end]
    sections["ruling"] = re.split(_COSTS, sections["ruling"])[0]
    # The considerations on the costs of the federal proceedings (Art. 64-68 BGG) likewise.
    sections["reasons"] = "\n".join(
        line
        for line in sections["reasons"].split("\n")
        if not re.search(
            r"\bart\. 6[4-8](?:\s+(?:abs|al|lit|let|bst|satz)\.?\s*\w+)*\s+(?:BGG|LTF)\b",
            line,
            re.I,
        )
    )
    return {name: sections[name].strip() for name in ("header", "facts", "reasons", "ruling")}


def prepare_source(ruling: dict, sections: dict[str, str], llm: LLMClient) -> str:
    """The decisive parts of the ruling, within the model's working budget."""
    facts = sections["facts"]
    if len(facts) > FACTS_BUDGET:
        facts = facts[: FACTS_BUDGET * 2 // 3] + "\n[...]\n" + facts[-FACTS_BUDGET // 3 :]
    reasons = sections["reasons"]
    room = SOURCE_BUDGET - len(sections["header"]) - len(facts) - len(sections["ruling"])
    if len(reasons) > room:
        reasons = condense_reasons(llm, reasons, ruling["language"])
    meta = f"Ruling {ruling['docket']} of {ruling.get('decision_date') or 'unknown date'}"
    parts = (meta, sections["header"], facts, reasons, sections["ruling"])
    return "\n\n".join(part for part in parts if part)


def condense_reasons(llm: LLMClient, reasons: str, language: str | None) -> str:
    """Map step for very long rulings: notes on each chunk of the reasons replace the text."""
    chunks, current = [], ""
    for paragraph in reasons.split("\n"):
        if current and len(current) + len(paragraph) > CHUNK_SIZE:
            chunks.append(current)
            current = ""
        current += paragraph + "\n"
    chunks.append(current)
    name = LANGUAGE_NAMES.get(language or "de", "German")
    notes = []
    for i, chunk in enumerate(chunks, 1):
        task = (
            f"Part {i} of {len(chunks)} of the reasons of a Federal Supreme Court ruling:\n\n"
            f"{chunk}\n\n---\nExtract in {name} every legal principle the Court states and every "
            "decisive finding and conclusion, each with its consideration number, staying close "
            "to the Court's wording. Skip admissibility and standard-of-review boilerplate unless "
            "it is contested. Output the notes only."
        )
        notes.append(llm.chat([{"role": "user", "content": task}], max_tokens=3000).strip())
    return "Reasons (condensed from the full text):\n" + "\n\n".join(notes)


def five_judges(header: str) -> bool:
    """Five-judge benches decide questions of principle (Art. 20 Abs. 2 BGG)."""
    match = re.search(
        r"(?:Besetzung|Composition|Composizione)\n(.*?)\n(?:Gerichtsschreiber|Greffi|Cancellier)",
        header,
        re.S,
    )
    if not match:
        return False
    bench = _BENCH_TITLES.sub(",", match.group(1))
    names = [name for name in re.split(r",|\.|\n|\b(?:et|e|und)\b", bench) if name.strip()]
    return len(names) >= 5


# --- Few-shot examples ---------------------------------------------------------------------


@cache
def _examples() -> tuple[dict, ...]:
    return tuple(read_jsonl(EXAMPLES_PATH))


@cache
def _style_de() -> dict[str, str]:
    return json.loads((PROMPTS_DIR / "style_examples_de.json").read_text(encoding="utf-8"))


def few_shots(lang: str, docket: str) -> list[tuple[str, str]]:
    """(docket, text) pairs of the evaluator's own summaries.

    VIL wrote French originals; their German texts in the examples are translations with
    artefacts, so German prompts get the corrected renderings in style_examples_de.json. A
    further example picked by similarity to the ruling was dropped: the model copied facts
    from it (8C_450/2025 got the 3.5 m fall onto a concrete slab of 8C_72/2025). Hold-out
    examples of data/eval/split.json are never shown.
    """
    allowed = set(load_split(SPLIT_PATH)["fewshot_pool"]) - {docket}
    return [
        (ex["docket"], _style_de()[ex["docket"]] if lang == "de" else ex["text_fr"])
        for ex in _examples()
        if ex["docket"] in STYLE_EXAMPLES and ex["docket"] in allowed
    ]
