import pytest

from suva.eval.metrics import (
    chrf,
    citation_issues,
    contains_term,
    foreign_statutes,
    glossary_usage,
    rouge_l,
    tokenize,
)

GLOSSARY = {
    "statutes": [{"de": "UVG", "fr": "LAA"}, {"de": "UVV", "fr": "OLAA"}],
    "terms": [
        {"de": "Einsprache", "fr": "opposition", "de_avoid": ["Einspruch"]},
        {"de": "Invalidenrente", "fr": "rente d'invalidité", "de_avoid": ["Invaliditätsrente"]},
        {"de": "IV-Stelle", "fr": "office AI"},
        {
            "de": "Valideneinkommen",
            "fr": "revenu sans invalidité",
            "fr_variants": ["revenu de valide"],
        },
    ],
}


def test_tokenize_normalises_case_and_apostrophes():
    assert tokenize("L’assuré a recouru.") == ["l", "assuré", "a", "recouru"]


def test_rouge_l():
    assert rouge_l("die Beschwerde wird abgewiesen", "Die Beschwerde wird abgewiesen.") == 1.0
    assert rouge_l("völlig anders", "die Beschwerde") == 0.0
    assert rouge_l("", "die Beschwerde") == 0.0
    # LCS "a c" of length 2: precision 2/3, recall 2/4
    assert rouge_l("a b c", "a x c y") == pytest.approx(2 * (2 / 3) * (2 / 4) / (2 / 3 + 2 / 4))


def test_chrf():
    assert chrf("Die Beschwerde wird abgewiesen.", "Die Beschwerde wird abgewiesen.") == 100.0
    assert chrf("xyz", "abc") == 0.0
    assert chrf("", "abc") == 0.0
    close = chrf("Die Beschwerde wird abgewiesen.", "Die Beschwerde wurde abgewiesen.")
    far = chrf("Die Suva gewinnt.", "Die Beschwerde wurde abgewiesen.")
    assert 0 < far < close < 100


def test_contains_term_anchors_at_word_start():
    assert contains_term("die Versicherten", ["Versicherte"])
    assert contains_term("l'incapacité de travail", ["incapacité de travail"])
    assert not contains_term("l'incapacité de travail", ["capacité de travail"])
    assert contains_term("Die IV-Stelle verfügte", ["IV"])
    assert not contains_term("eine aktive Tätigkeit", ["IV"])


def test_glossary_usage():
    reference = "Die Einsprache gegen die Invalidenrente wurde abgewiesen."
    usage = glossary_usage("Der Einspruch betraf die Invalidenrente.", reference, GLOSSARY, "de")
    assert usage["expected"] == 2 and usage["used"] == 1
    assert usage["recall"] == 0.5
    assert usage["missing"] == ["Einsprache"]
    assert usage["avoid_hits"] == ["Einspruch"]
    fr = glossary_usage("le revenu de valide", "le revenu sans invalidité", GLOSSARY, "fr")
    assert fr["recall"] == 1.0
    assert glossary_usage("x", "kein Fachbegriff", GLOSSARY, "de")["recall"] is None


def test_foreign_statutes():
    assert foreign_statutes("Art. 73 lit. b OLAA und Art. 6 UVG", GLOSSARY, "de") == ["OLAA"]
    assert foreign_statutes("l'art. 6 al. 2 LAA", GLOSSARY, "fr") == []
    assert foreign_statutes("selon l'art. 6 UVG", GLOSSARY, "fr") == ["UVG"]


def test_citation_issues():
    assert citation_issues("Art. 6 Abs. 2 Bst. g UVG (E. 4.3)", "de") == []
    assert citation_issues("gemäss art. 6 al. 2 UVG (consid. 4)", "de") == [
        "'consid.' instead of 'E.'",
        "'al.' instead of 'Abs.'",
        "lowercase 'art.'",
    ]
    assert citation_issues("Art. 6 al. 2 let. g LAA (consid. 4.3)", "fr") == []
    assert citation_issues("selon Art. 6 Abs. 2 lit. g LAA (E. 4.3)", "fr") == [
        "'E.'/'Erw.' instead of 'consid.'",
        "'Abs.' instead of 'al.'",
        "'lit.'/'Bst.' instead of 'let.'",
        "capitalised 'Art.' mid-sentence",
    ]
