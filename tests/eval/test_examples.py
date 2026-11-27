from datetime import date

import pytest

from suva.eval.examples import (
    JUDGEMENTS_DIR,
    RELEVANT_XLSX,
    load_examples,
    load_relevant,
    load_split,
    normalise_docket,
    parse_date,
    parse_example,
)
from suva.eval.glossary import load_glossary, with_support


@pytest.fixture(scope="module")
def examples():
    return load_examples()


@pytest.fixture(scope="module")
def relevant(examples):
    return load_relevant(RELEVANT_XLSX, examples)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("8C_129/2025", "8C_129/2025"),
        ("Export_8C_176_2025 3", "8C_176/2025"),
        ("Arrêt du TF 8C_613_2025 du 27 mars 2026", "8C_613/2025"),
        ("aza://11-11-2025-8C_129-2025&lang=de", "8C_129/2025"),
        ("BGer-Urteil-8C67-2025-vom-20.-Januar-2026", "8C_67/2025"),
        ("9C_065/2025", "9C_65/2025"),
        ("BGer-Urteil 458/2025 vom 18. November 2025", None),
        ("Entscheid des Kantonsgerichts Basel-Landschaft", None),
    ],
)
def test_normalise_docket(text, expected):
    assert normalise_docket(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("BGer-Urteil 8C_313/2024 vom 13. November 2025", date(2025, 11, 13)),
        ("Arrêt du TF 8C_330/2025 du 1er septembre 2025", date(2025, 9, 1)),
        ("Sentenza del TF 9C_65/2025 del 29 gennaio 2026", date(2026, 1, 29)),
        ("BGer-Urteil-8C_18-2026-vom-2.-März-2026", date(2026, 3, 2)),
        ("BGer-Urteil-9C_699-2024-vom-24.-Okober-2025", date(2025, 10, 24)),
        ("BGer-Urteil-8C_605", None),
    ],
)
def test_parse_date(text, expected):
    assert parse_date(text) == expected


def test_parse_example_minimal_html(tmp_path):
    path = tmp_path / "Export_8C_1_2025.html"
    path.write_text(
        "<html><body><h1>BGer-Urteil 8C_1/2025 vom 2. Mai 2025</h1>"
        "<h2>Text DE</h2><p>Erster   Absatz.</p><p>Zweiter&nbsp;Absatz.</p>"
        "<h2>Text FR</h2><p>Premier paragraphe.</p>"
        "<h2>Link zum Urteil</h2><p>https://example.org/x?highlight_docid=aza://02-05-2025-8C_1-2025</p>"
        "<h2>Autor</h2><p>Muster Anna (MUA), Rechtsanwältin, Teamleiterin</p></body></html>",
        encoding="utf-8",
    )
    example = parse_example(path)
    assert example.docket == "8C_1/2025"
    assert example.ruling_date == "2025-05-02"
    assert example.ruling_lang == "de"
    assert example.text_de == "Erster Absatz.\n\nZweiter Absatz."
    assert example.text_fr == "Premier paragraphe."
    assert example.url.endswith("aza://02-05-2025-8C_1-2025")
    assert (example.author, example.author_code, example.author_role) == (
        "Muster Anna",
        "MUA",
        "Rechtsanwältin, Teamleiterin",
    )
    assert not example.leading_case


def test_every_example_parses_with_consistent_docket(examples):
    files = sorted(JUDGEMENTS_DIR.glob("*.html"))
    assert len(examples) == len(files) == 55
    for example in examples:
        assert normalise_docket(example.source_file) == example.docket
        assert example.text_de and example.text_fr
        assert example.ruling_date and example.ruling_lang in {"de", "fr", "it"}
        assert example.author_code


def test_irregular_examples(examples):
    by_docket = {e.docket: e for e in examples}
    assert by_docket["8C_176/2025"].source_file == "Export_8C_176_2025 3.html"
    assert by_docket["8C_458/2025"].title.startswith("BGer-Urteil 458/2025")
    assert by_docket["8C_275/2025"].url.startswith("https://search.bger.ch/")
    assert by_docket["9C_65/2025"].leading_case
    assert by_docket["9C_65/2025"].ruling_lang == "it"
    assert by_docket["8C_626/2024"].text_de.endswith("Fünfer-Entscheid")


def test_relevant_list(relevant):
    assert len(relevant) == 60
    by_label = {r.label: r for r in relevant}
    partial = by_label["BGer-Urteil 458/2025 vom 18. November 2025"]
    assert partial.docket == "8C_458/2025" and partial.has_example
    cantonal = by_label["Entscheid des Kantonsgerichts Basel-Landschaft vom 5. Februar 2026"]
    assert cantonal.docket is None and cantonal.ruling_date == "2026-02-05"
    assert sum(r.has_example for r in relevant) == 32


def test_quarter_matches_ruling_date(relevant):
    for ruling in relevant:
        if ruling.ruling_date:
            year, month = int(ruling.ruling_date[:4]), int(ruling.ruling_date[5:7])
            assert ruling.quarter == f"{year} Q{(month - 1) // 3 + 1}", ruling


def test_split_partitions_examples(examples):
    split = load_split()
    dockets = {e.docket for e in examples}
    holdout, pool = set(split["holdout"]), set(split["fewshot_pool"])
    assert len(split["holdout"]) == 10
    assert holdout | pool == dockets and not holdout & pool
    assert {label["docket"] for label in split["labels"]} == dockets
    langs = {e.ruling_lang for e in examples if e.docket in holdout}
    assert {"de", "fr"} <= langs
    assert len({label["topic"] for label in split["labels"] if label["docket"] in holdout}) >= 8
    for lang, recommended in split["recommended_fewshot"].items():
        for docket in recommended:
            assert docket in pool
            assert next(e for e in examples if e.docket == docket).ruling_lang == lang


def test_glossary_support_is_current(examples):
    glossary = load_glossary()
    records = [{"text_de": e.text_de, "text_fr": e.text_fr} for e in examples]
    assert with_support(glossary, records) == glossary
    assert all(term["support"] > 0 for term in glossary["terms"])
