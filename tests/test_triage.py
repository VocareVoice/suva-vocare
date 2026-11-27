import json
import math
from types import SimpleNamespace

import pytest

from suva import db, triage
from suva.llm import Completion, TokenLogprob

RULING_TEXT = """Bundesgericht
8C_1/2026
Urteil vom 5. Januar 2026
IV. öffentlich-rechtliche Abteilung
Besetzung
Bundesrichterin Viscione, Präsidentin,
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
Erwägungen:
1. Streitig ist der adäquate Kausalzusammenhang nach Art. 6 Abs. 1 UVG.
2. {filler}
Demnach erkennt das Bundesgericht:
1. Die Beschwerde wird abgewiesen.
"""


class FakeLLM:
    model = "fake-apertus"

    def __init__(self, reply, tmp_path):
        self.reply = reply
        self.logprobs = None
        self.calls = []
        examples = tmp_path / "examples.jsonl"
        examples.write_text(
            json.dumps({"docket": "8C_129/2025", "de": "Die Reinigung fällt unter Art. 73 UVV."})
            + "\n"
            + json.dumps({"docket": "8C_9/2025", "de": "Der Unfallbegriff setzt Folgendes voraus."})
            + "\n"
        )
        self.settings = SimpleNamespace(examples_path=examples)

    def complete(self, messages, **params):
        self.calls.append(messages)
        if isinstance(self.reply, Exception):
            raise self.reply
        return Completion(json.dumps(self.reply), self.logprobs)


def ruling(docket="8C_1/2026", title="Unfallversicherung (Kausalzusammenhang)", filler=""):
    return {"docket": docket, "title": title, "text": RULING_TEXT.format(filler=filler)}


def test_prior_recognises_suva_accident_cases():
    p = triage.prior(ruling())
    assert p.score >= 80
    assert "Suva ist Partei" in p.factors
    assert any(f.startswith("Gegenstand: Unfallversicherung") for f in p.factors)


def test_prior_without_title_reads_the_subject_from_the_text():
    assert triage.subject(RULING_TEXT) == "Unfallversicherung (Kausalzusammenhang)"
    assert triage.prior(ruling(title=None)).score == triage.prior(ruling()).score


@pytest.mark.parametrize(
    ("docket", "title", "text"),
    [
        ("6B_1/2026", "Raub", "Der Beschwerdeführer wurde wegen Raubes verurteilt."),
        ("9C_1/2026", "Direkte Bundessteuer", "Streitig ist die Steuerperiode 2021."),
        ("4A_1/2026", "Mietrecht", "Streit über die Kündigung eines Mietvertrags."),
    ],
)
def test_prior_rules_out_unrelated_rulings(docket, title, text):
    p = triage.prior({"docket": docket, "title": title, "text": text})
    assert p.score < triage.PRIOR_CUTOFF


def test_invalidity_insurance_reaches_the_llm():
    p = triage.prior(
        {"docket": "9C_2/2026", "title": "Invalidenversicherung", "text": "Art. 16 ATSG"}
    )
    assert p.score >= triage.PRIOR_CUTOFF


def test_split_sections_and_excerpt_keep_rubrum_and_operative_part():
    text = RULING_TEXT.format(filler="Lange Begründung. " * 5000)
    sections = triage.split_sections(text)
    assert "Gegenstand" in sections.rubrum
    assert sections.facts.startswith("Sachverhalt:")
    assert sections.reasons.startswith("Erwägungen:")
    assert sections.operative.startswith("Demnach erkennt")

    short = triage.excerpt(text, limit=8000)
    assert len(short) < 9000
    assert "Schweizerische Unfallversicherungsanstalt" in short
    assert "Die Beschwerde wird abgewiesen." in short
    assert "[...]" in short


@pytest.mark.parametrize(
    ("reply", "prior", "score", "label"),
    [
        ({"relevanz": 9, "reasoning": "Klar."}, 100, 100, "relevant"),
        ({"relevanz": "6", "reasoning": "Grenzfall."}, 40, 60, "relevant"),
        ({"relevanz": 3, "reasoning": ["Satz eins.", "Satz zwei."]}, 40, 35, "not_relevant"),
        ({"relevanz": 12, "reasoning": "Zu hoch."}, 0, 75, "relevant"),
        ({"relevanz": -1, "reasoning": "Nein."}, 0, 0, "not_relevant"),
    ],
)
def test_parse_result_blends_level_and_prior(reply, prior, score, label):
    result = triage.parse_result(reply, "m", prior_score=prior)
    assert (result.score, result.label, result.model) == (score, label, "m")
    assert "  " not in result.reasoning


@pytest.mark.parametrize("reply", [[1, 2], {"reasoning": "kein Score"}, {"relevanz": "hoch"}])
def test_parse_result_rejects_malformed_replies(reply):
    with pytest.raises((ValueError, KeyError)):
        triage.parse_result(reply, "m")


def test_expected_level_weights_the_digit_by_its_probability():
    tokens = ['{"', "reasoning", '":', ' "Ein Satz 7."', ', "', "relevanz", '":', " 7", "}"]
    logprobs = [TokenLogprob(t, {t: 0.0}) for t in tokens]
    logprobs[7] = TokenLogprob(" 7", {" 7": math.log(0.5), "8": math.log(0.5), "x": -1.0})
    assert triage.expected_level(logprobs) == pytest.approx(7.5)
    # The digit inside the reasoning is not the level.
    assert triage.expected_level(logprobs[:7]) is None
    assert triage.expected_level(None) is None


def test_triage_calls_the_llm_with_examples_and_feedback(conn, tmp_path):
    db.save_feedback(conn, "8C_135/2025", verdict="relevant", corrected_score=90, comment="BGE")
    llm = FakeLLM({"reasoning": "Suva-Fall.", "relevanz": 9}, tmp_path)
    tokens = ['{"reasoning": "Suva-Fall.", "relevanz": ', "9", "}"]
    llm.logprobs = [TokenLogprob(t, {t: 0.0}) for t in tokens]
    llm.logprobs[1] = TokenLogprob("9", {"9": math.log(0.5), "6": math.log(0.5)})

    result = triage.triage(conn, "8C_129/2025", llm)

    prior = triage.prior(db.get_ruling(conn, "8C_129/2025")).score
    w = triage.PRIOR_WEIGHT
    expected = round(100 * ((1 - w) * 7.5 / 9 + w * prior / 100))
    assert (result.score, result.label, result.model) == (expected, "relevant", "fake-apertus")
    prompt = llm.calls[0][1]["content"]
    assert "8C_9/2025: Der Unfallbegriff" in prompt
    # The ruling's own example summary must not leak into its prompt.
    assert "8C_129/2025: Die Reinigung" not in prompt
    assert "8C_135/2025 (Assurance-accidents (rente d'invalidité)): relevant, Score 90" in prompt
    assert "Kommentar: BGE" in prompt


def test_prefiltered_rulings_never_reach_the_llm(conn, tmp_path):
    llm = FakeLLM({"relevanz": 9}, tmp_path)
    result = triage.triage(conn, "4A_106/2025", llm)
    assert result.label == "not_relevant"
    assert result.model == triage.PREFILTER_MODEL
    assert "Vorprüfung" in result.reasoning
    assert llm.calls == []


def test_batch_reports_failures_without_stopping(conn, tmp_path):
    llm = FakeLLM(ValueError("kein JSON"), tmp_path)
    results = dict(triage.triage_batch(conn, db.untriaged_dockets(conn), llm, workers=2))
    assert isinstance(results["8C_129/2025"], ValueError)
    assert results["4A_106/2025"].model == triage.PREFILTER_MODEL


def test_untriaged_dockets_by_date_and_prompt_version(conn):
    db.save_triage(
        conn,
        "8C_129/2025",
        score=80,
        label="relevant",
        reasoning="r",
        model="m",
        prompt_version="old",
    )
    assert db.untriaged_dockets(conn) == ["4A_106/2025", "8C_135/2025"]
    assert db.untriaged_dockets(conn, prompt_version="new") == [
        "4A_106/2025",
        "8C_129/2025",
        "8C_135/2025",
    ]
    assert db.untriaged_dockets(conn, date_from="2025-10-01", prompt_version="new") == [
        "8C_129/2025",
        "8C_135/2025",
    ]


def test_export_and_import_round_trip(conn, tmp_path):
    db.save_triage(
        conn,
        "8C_129/2025",
        score=80,
        label="relevant",
        reasoning="r",
        model="m",
        prompt_version="v1",
    )
    path = tmp_path / "results.jsonl"
    assert db.export_triage(conn, path) == 1

    fresh = db.connect(tmp_path / "fresh.db")
    db.upsert_ruling(fresh, {"docket": "8C_129/2025", "text": "x"})
    assert db.import_triage(fresh, path) == 1
    assert db.import_triage(fresh, path) == 0
    detail = db.get_ruling_detail(fresh, "8C_129/2025")
    assert detail["triage"]["score"] == 80
    assert detail["triage"]["prompt_version"] == "v1"
