import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from suva import api, classify, db

RULING_TEXT = """Bundesgericht
8C_1/2026
Urteil vom 5. Januar 2026
IV. öffentlich-rechtliche Abteilung
Besetzung
Bundesrichter Wirthlin, Präsident,
Bundesrichterinnen Heine, Viscione,
Bundesrichter Métral, Maillard,
Gerichtsschreiber Grunder.
Verfahrensbeteiligte
A.________,
Beschwerdeführer,
gegen
Schweizerische Unfallversicherungsanstalt (Suva), Fluhmattstrasse 1, 6002 Luzern,
Beschwerdegegnerin.
Gegenstand
Unfallversicherung (Kausalzusammenhang),
Beschwerde gegen das Urteil des Versicherungsgerichts des Kantons Aargau.
Sachverhalt:
A. Der Versicherte stürzte von einer Leiter.
B. Das Bundesgericht führte am 3. Januar 2026 eine öffentliche Beratung durch.
Erwägungen:
1. Streitig ist der adäquate Kausalzusammenhang nach Art. 6 Abs. 1 UVG und Art. 4 ATSG.
2. Nach Art. 6 UVG und art. 6 al. 1 LAA sowie Art. 16 ATSG gilt Folgendes.
Demnach erkennt das Bundesgericht:
1.
{first}
2.
{second}
3.
Dieses Urteil wird den Parteien mitgeteilt.
"""


def ruling(
    first="Die Beschwerde wird abgewiesen.",
    second="Die Gerichtskosten werden dem Beschwerdeführer auferlegt.",
    docket="8C_1/2026",
    title="Unfallversicherung (Kausalzusammenhang)",
):
    text = RULING_TEXT.format(first=first, second=second)
    return {"docket": docket, "title": title, "text": text, "decision_date": "2026-01-05"}


class FakeLLM:
    model = "fake-apertus"

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    def chat(self, messages, **params):
        self.calls.append((messages, params))
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        return reply if isinstance(reply, str) else json.dumps(reply)


def test_taxonomy_matrix_only_names_known_labels():
    assert set(classify.MATRIX) == set(classify.BRANCHES)
    for allowed in classify.MATRIX.values():
        assert allowed <= set(classify.CATEGORIES)
        assert {"verfahren", "beweis-gutachten", "andere"} <= allowed
    assert "adaequate-kausalitaet" not in classify.MATRIX["iv"]
    taxonomy = classify.taxonomy({"branches": {"uv": 2}, "categories": {"verfahren": {"iv": 1}}})
    uv = next(b for b in taxonomy["branches"] if b["value"] == "uv")
    assert (uv["de"], uv["fr"], uv["count"]) == (
        "Unfallversicherung (UVG)",
        "Assurance-accidents (LAA)",
        2,
    )
    verfahren = next(c for c in taxonomy["categories"] if c["value"] == "verfahren")
    assert verfahren["counts"] == {"iv": 1}
    assert set(verfahren["branches"]) == set(classify.BRANCHES)


def test_statutes_are_canonical_and_counted():
    cited = classify.statutes(ruling()["text"])
    assert cited[:3] == [
        {"law": "UVG", "art": "6", "count": 3},
        {"law": "ATSG", "art": "4", "count": 1},
        {"law": "ATSG", "art": "16", "count": 1},
    ]
    assert classify.statutes("art. 21bis al. 2 let. a de la LPGA et Art. 73 lit. b UVV") == [
        {"law": "UVV", "art": "73", "count": 1},
        {"law": "ATSG", "art": "21bis", "count": 1},
    ]


@pytest.mark.parametrize(
    ("first", "second", "expected"),
    [
        ("Die Beschwerde wird abgewiesen.", "Die Gerichtskosten trägt A.", "dismissed"),
        ("Auf die Beschwerde wird nicht eingetreten.", "Keine Kosten.", "not_entertained"),
        ("Die Beschwerde wird abgewiesen, soweit darauf einzutreten ist.", "-", "dismissed"),
        ("Die Beschwerde wird gutgeheissen.", "Die Gerichtskosten trägt die Suva.", "upheld"),
        (
            "Die Beschwerde wird gutgeheissen. Die Sache wird zu neuer Verfügung an die Suva "
            "zurückgewiesen.",
            "-",
            "remanded",
        ),
        (
            "Die Beschwerde wird teilweise gutgeheissen.",
            "Die Sache wird zur Neuverlegung der Kosten an die Vorinstanz zurückgewiesen.",
            "partly_upheld",
        ),
        ("Die Verfahren 8C_1/2026 und 8C_2/2026 werden vereinigt.", "Le recours est rejeté.", None),
        ("Das Verfahren wird als gegenstandslos abgeschrieben.", "-", "struck_off"),
    ],
)
def test_outcome_from_the_dispositive(first, second, expected):
    # A joinder in item 1 moves the decision to item 2.
    expected = "dismissed" if "vereinigt" in first else expected
    assert classify.outcome(ruling(first, second)["text"]) == expected


def test_outcome_in_french_and_without_dispositive():
    text = "Faits:\nA.\nConsidérant en droit:\n1.\nPar ces motifs, la Présidente prononce :\n"
    assert classify.outcome(text + "1.\nLe recours est irrecevable.\n") == "not_entertained"
    assert classify.outcome(text + "1.\nLe recours est admis.\n") == "upheld"
    assert classify.outcome("Kein Dispositiv.") is None


def test_flags_five_judges_public_deliberation_and_publication(conn):
    facts = classify.facts(ruling(), published={"8C_1/2026"})
    assert facts.flags == ["five_judges", "public_deliberation", "publication"]
    three = ruling()["text"].replace("Bundesrichter Métral, Maillard,\n", "")
    assert classify.panel_size(three) == 3
    assert classify.facts({**ruling(), "text": three}).flags == ["public_deliberation"]

    citing = {
        "docket": "8C_9/2026",
        "text": "Vgl. Urteil 8C_135/2025 vom 14. November 2025 E. 3, zur Publikation vorgesehen.",
    }
    db.upsert_ruling(conn, citing)
    assert classify.cited_for_publication(conn) == {"8C_135/2025"}


@pytest.mark.parametrize(
    ("title", "branch", "primary", "secondary", "method"),
    [
        (
            "Unfallversicherung (Kausalzusammenhang; psychisches Leiden)",
            "uv",
            "adaequate-kausalitaet",
            ["natuerliche-kausalitaet"],
            "subject",
        ),
        (
            "Assurance-invalidité (allocation pour impotent)",
            "iv",
            "hilflosigkeit-pflege",
            [],
            "subject",
        ),
        (
            "Assurance-accidents (révision; rente d'invalidité)",
            "uv",
            "rentenrevision",
            ["invaliditaetsgrad"],
            "subject",
        ),
        ("Invalidenversicherung (Prozessvoraussetzung)", "iv", "verfahren", [], "subject"),
        # Integrity compensation does not exist in invalidity insurance.
        ("Invalidenversicherung (Integritätsentschädigung)", "iv", "andere", [], "rule"),
        ("Krankenversicherung", "atsg", "andere", [], "rule"),
        ("Mietrecht", "uv", "andere", [], "rule"),
    ],
)
def test_subject_classifier(title, branch, primary, secondary, method):
    # "Mietrecht" falls back to the statutes cited, which are UVG articles.
    r = ruling(title=title)
    result = classify.classify_subject(r, classify.facts(r))
    assert (result.branch, result.primary, result.secondary, result.method) == (
        branch,
        primary,
        secondary,
        method,
    )


def test_subject_classifier_without_hints_reads_the_outcome():
    r = ruling(first="Auf die Beschwerde wird nicht eingetreten.", title="Strafrecht")
    r["text"] = "Demnach erkennt die Präsidentin:\n1.\nAuf die Beschwerde wird nicht eingetreten.\n"
    result = classify.classify_subject(r, classify.facts(r))
    assert (result.branch, result.primary, result.method) == ("other", "verfahren", "rule")


def test_llm_classification_passes_the_schema_and_hints():
    llm = FakeLLM(
        {
            "rationale": "Adäquanz.",
            "branch": "uv",
            "primary": "adaequate-kausalitaet",
            "secondary": ["natuerliche-kausalitaet", "adaequate-kausalitaet", "andere"],
        }
    )
    result = classify.classify_ruling(ruling(title="Unfallversicherung (Schleudertrauma)"), llm)
    assert (result.branch, result.primary, result.secondary) == (
        "uv",
        "adaequate-kausalitaet",
        ["natuerliche-kausalitaet"],
    )
    assert (result.method, result.model, result.rationale) == ("llm", "fake-apertus", "Adäquanz.")
    assert result.outcome == "dismissed"
    messages, params = llm.calls[0]
    assert params["response_format"]["json_schema"]["schema"]["properties"]["branch"]["enum"]
    assert "Vom Gegenstand genannte Kategorie: adaequate-kausalitaet" in messages[1]["content"]
    assert "Art. 6 UVG" in messages[1]["content"]


def test_llm_classification_retries_a_category_outside_the_branch():
    llm = FakeLLM(
        {"branch": "iv", "primary": "adaequate-kausalitaet", "secondary": []},
        {"branch": "uv", "primary": "adaequate-kausalitaet", "secondary": []},
    )
    result = classify.classify_ruling(ruling(), llm)
    assert (result.branch, result.primary, result.method) == ("uv", "adaequate-kausalitaet", "llm")
    retry = llm.calls[1][0]
    assert retry[-2]["role"] == "assistant"
    assert "nicht erlaubt" in retry[-1]["content"]


def test_llm_classification_falls_back_to_the_subject_after_invalid_replies():
    llm = FakeLLM("kein JSON")
    result = classify.classify_ruling(ruling(), llm)
    assert len(llm.calls) == classify.MAX_ATTEMPTS
    assert (result.method, result.primary) == ("subject", "natuerliche-kausalitaet")


def test_prefiltered_rulings_never_reach_the_llm(conn):
    llm = FakeLLM({"branch": "uv", "primary": "andere", "secondary": []})
    result = classify.classify(conn, "4A_106/2025", llm)
    assert llm.calls == []
    assert (result.branch, result.method) == ("other", "rule")


def save(conn, docket, **values):
    defaults = {
        "branch": "uv",
        "primary": "natuerliche-kausalitaet",
        "secondary": [],
        "statutes": [{"law": "UVG", "art": "6", "count": 1}],
        "outcome": "dismissed",
        "flags": [],
        "method": "llm",
        "rationale": "r",
        "model": "m",
        "prompt_version": "v1",
    }
    db.save_classification(conn, docket, **{**defaults, **values})


def test_storage_filters_and_facets(conn):
    save(conn, "8C_129/2025", primary="adaequate-kausalitaet", secondary=["verfahren"])
    save(conn, "8C_135/2025", primary="invaliditaetsgrad", flags=["five_judges"])
    save(conn, "4A_106/2025", branch="other", primary="andere", method="rule")
    save(conn, "4A_106/2025", branch="other", primary="verfahren", method="rule")

    detail = db.get_ruling_detail(conn, "8C_129/2025")["classification"]
    assert detail["primary"] == "adaequate-kausalitaet"
    assert detail["secondary"] == ["verfahren"]
    assert detail["statutes"] == [{"law": "UVG", "art": "6", "count": 1}]

    def dockets(**filters):
        return sorted(item["docket"] for item in db.list_rulings(conn, **filters)[1])

    assert dockets(branch="uv") == ["8C_129/2025", "8C_135/2025"]
    # The latest classification counts, and secondary categories match too.
    assert dockets(category="verfahren") == ["4A_106/2025", "8C_129/2025"]
    assert dockets(category="andere") == []
    assert dockets(branch="uv", category="verfahren") == ["8C_129/2025"]

    item = next(i for i in db.list_rulings(conn)[1] if i["docket"] == "8C_135/2025")
    assert item["classification"] == {
        "branch": "uv",
        "primary": "invaliditaetsgrad",
        "secondary": [],
        "outcome": "dismissed",
        "flags": ["five_judges"],
    }
    counts = db.facets(conn)["classification"]
    assert counts["branches"] == {"uv": 2, "other": 1}
    assert counts["categories"]["verfahren"] == {"uv": 1, "other": 1}
    assert "andere" not in counts["categories"]


def test_unclassified_dockets_export_and_import(conn, tmp_path):
    save(conn, "8C_129/2025", prompt_version="v1")
    assert db.unclassified_dockets(conn) == ["4A_106/2025", "8C_135/2025"]
    assert db.unclassified_dockets(conn, date_from="2025-10-01", prompt_version="v2") == [
        "8C_129/2025",
        "8C_135/2025",
    ]
    path = tmp_path / "classification.jsonl"
    assert db.export_classification(conn, path) == 1
    row = json.loads(path.read_text())
    assert (row["docket"], row["primary"], row["secondary"]) == (
        "8C_129/2025",
        "natuerliche-kausalitaet",
        [],
    )

    fresh = db.connect(tmp_path / "fresh.db")
    db.upsert_ruling(fresh, {"docket": "8C_129/2025", "text": "x"})
    assert db.import_classification(fresh, path) == 1
    assert db.import_classification(fresh, path) == 0
    assert db.get_classification(fresh, "8C_129/2025")["created_at"] == row["created_at"]


def test_databases_from_before_classification_still_load(tmp_path):
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.executescript(db.SCHEMA)
    old.execute("INSERT INTO rulings (docket, text) VALUES ('8C_1/2026', 'x')")
    old.commit()
    old.close()
    conn = db.connect(path)
    assert db.list_rulings(conn)[1][0]["classification"] is None
    assert db.get_ruling_detail(conn, "8C_1/2026")["classification"] is None


def test_api_filters_detail_and_facets(conn):
    save(conn, "8C_129/2025", primary="adaequate-kausalitaet")
    save(conn, "4A_106/2025", branch="other", primary="andere", method="rule")
    api.app.dependency_overrides[api.get_conn] = lambda: conn
    try:
        client = TestClient(api.app)
        body = client.get("/api/rulings", params={"branch": "uv"}).json()
        assert [i["docket"] for i in body["items"]] == ["8C_129/2025"]
        assert body["items"][0]["classification"]["primary"] == "adaequate-kausalitaet"
        assert body["stats"]["total"] == 1
        body = client.get("/api/rulings", params={"category": "andere"}).json()
        assert [i["docket"] for i in body["items"]] == ["4A_106/2025"]
        detail = client.get("/api/rulings/8C_129/2025").json()
        assert detail["classification"]["method"] == "llm"
        facets = client.get("/api/facets").json()["classification"]
        uv = next(b for b in facets["branches"] if b["value"] == "uv")
        assert uv["count"] == 1
        assert {"value": "remanded", "de": "zurückgewiesen", "fr": "renvoyé"} in facets["outcomes"]
    finally:
        api.app.dependency_overrides.clear()
