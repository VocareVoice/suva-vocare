"""Dependency-free text metrics for comparing generated and human summaries."""

import re
from collections import Counter

WORD_RE = re.compile(r"\w+")


def normalise(text: str) -> str:
    return text.replace("’", "'").replace(" ", " ").replace(" ", " ").lower()


def tokenize(text: str) -> list[str]:
    return WORD_RE.findall(normalise(text))


def word_count(text: str) -> int:
    return len(text.split())


def _lcs_length(a: list[str], b: list[str]) -> int:
    if len(a) < len(b):
        a, b = b, a
    previous = [0] * (len(b) + 1)
    for token in a:
        current = [0]
        for j, other in enumerate(b, start=1):
            current.append(previous[j - 1] + 1 if token == other else max(previous[j], current[-1]))
        previous = current
    return previous[-1]


def rouge_l(candidate: str, reference: str) -> float:
    """ROUGE-L F1 over lowercased word tokens."""
    cand, ref = tokenize(candidate), tokenize(reference)
    if not cand or not ref:
        return 0.0
    lcs = _lcs_length(cand, ref)
    if lcs == 0:
        return 0.0
    precision, recall = lcs / len(cand), lcs / len(ref)
    return 2 * precision * recall / (precision + recall)


def _char_ngrams(text: str, n: int) -> Counter[str]:
    return Counter(text[i : i + n] for i in range(len(text) - n + 1))


def chrf(candidate: str, reference: str, char_order: int = 6, beta: float = 2.0) -> float:
    """chrF on a 0-100 scale, following sacrebleu's defaults (whitespace removed, beta=2)."""
    hyp = "".join(candidate.split())
    ref = "".join(reference.split())
    precisions, recalls = [], []
    for n in range(1, char_order + 1):
        hyp_ngrams, ref_ngrams = _char_ngrams(hyp, n), _char_ngrams(ref, n)
        hyp_total, ref_total = sum(hyp_ngrams.values()), sum(ref_ngrams.values())
        if hyp_total == 0 or ref_total == 0:
            continue
        matches = sum((hyp_ngrams & ref_ngrams).values())
        precisions.append(matches / hyp_total)
        recalls.append(matches / ref_total)
    if not precisions:
        return 0.0
    precision = sum(precisions) / len(precisions)
    recall = sum(recalls) / len(recalls)
    if precision == 0 and recall == 0:
        return 0.0
    factor = beta**2
    return 100 * (1 + factor) * precision * recall / (factor * precision + recall)


def term_forms(entry: dict, lang: str) -> list[str]:
    return [entry[lang], *entry.get(f"{lang}_variants", [])]


def contains_term(text: str, forms: list[str]) -> bool:
    """Case-insensitive match anchored at a word start; all-caps abbreviations match whole words."""
    lowered = normalise(text)
    for form in forms:
        if form.isupper():
            if re.search(rf"(?<![\w-]){re.escape(form)}(?!\w)", text):
                return True
        elif re.search(rf"(?<!\w){re.escape(normalise(form))}", lowered):
            return True
    return False


def term_support(entry: dict, examples: list[dict]) -> int:
    """Number of examples whose `text_de` uses the German and `text_fr` the French term."""
    return sum(
        contains_term(e["text_de"], term_forms(entry, "de"))
        and contains_term(e["text_fr"], term_forms(entry, "fr"))
        for e in examples
    )


def glossary_usage(candidate: str, reference: str, glossary: dict, lang: str) -> dict:
    """Which glossary terms the human reference uses, and how many of them the candidate reuses."""
    expected = [e for e in glossary["terms"] if contains_term(reference, term_forms(e, lang))]
    missing = [e[lang] for e in expected if not contains_term(candidate, term_forms(e, lang))]
    avoid_hits = [
        form
        for e in glossary["terms"]
        for form in e.get(f"{lang}_avoid", [])
        if contains_term(candidate, [form])
    ]
    return {
        "expected": len(expected),
        "used": len(expected) - len(missing),
        "recall": (len(expected) - len(missing)) / len(expected) if expected else None,
        "missing": missing,
        "avoid_hits": avoid_hits,
    }


CITATION_RULES = {
    "de": [
        (r"\bconsid\. ?\d", "'consid.' instead of 'E.'"),
        (r"\bal\. \d", "'al.' instead of 'Abs.'"),
        (r"\blet\. [a-z]\b", "'let.' instead of 'Bst.'/'lit.'"),
        (r"\bart\. \d", "lowercase 'art.'"),
    ],
    "fr": [
        (r"\(E\. ?\d|\bErw\. ?\d", "'E.'/'Erw.' instead of 'consid.'"),
        (r"\bAbs\. \d", "'Abs.' instead of 'al.'"),
        (r"\b(?:lit|Bst)\. [a-z]\b", "'lit.'/'Bst.' instead of 'let.'"),
        (r"(?<=[a-zà-ÿ,;] )Art\. \d", "capitalised 'Art.' mid-sentence"),
    ],
}


def citation_issues(text: str, lang: str) -> list[str]:
    return [message for pattern, message in CITATION_RULES[lang] if re.search(pattern, text)]


def foreign_statutes(text: str, glossary: dict, lang: str) -> list[str]:
    """Statute abbreviations of the other language, e.g. `OLAA` inside a German summary."""
    other = "fr" if lang == "de" else "de"
    return [
        statute[other]
        for statute in glossary["statutes"]
        if re.search(rf"(?<![\w-]){re.escape(statute[other])}(?![\w-])", text)
        and statute[other] != statute[lang]
    ]
