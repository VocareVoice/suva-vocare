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


DE = "Unfallversicherung, die Suva ist Partei. Das Urteil ist für die Suva relevant."
FR = "Assurance-accidents, la Suva est partie. L'arrêt est pertinent pour la Suva."


class FakeLLM:
    model = "fake-apertus"

    def __init__(self, *replies, tmp_path):
        self.replies = list(replies)
        self.logprobs = None
        self.calls = []
        examples = tmp_path / "examples.jsonl"
        examples.write_text(
            "".join(
                json.dumps({"docket": docket, "text_de": text}) + "\n"
                for docket, text in [
                    ("8C_129/2025", "Die Reinigung fällt unter Art. 73 UVV."),
                    ("8C_9/2025", "Der Unfallbegriff setzt Folgendes voraus."),
                    ("8C_78/2025", "Hold-out: Listenverletzung nach Art. 6 Abs. 2 UVG."),
                ]
            )
        )
        split = {"fewshot_pool": ["8C_129/2025", "8C_9/2025"], "holdout": ["8C_78/2025"]}
        (tmp_path / "split.json").write_text(json.dumps(split))
        glossary = {
            "statutes": [
                {"de": "UVG", "fr": "LAA"},
                {"de": "IVG", "fr": "LAI"},
                {"de": "IVV", "fr": "RAI"},
            ],
            "terms": [
                {"de": "Kausalzusammenhang", "fr": "lien de causalité", "support": 3},
                {"de": "Taggeld", "fr": "indemnité journalière", "support": 5},
            ],
        }
        (tmp_path / "glossary.json").write_text(json.dumps(glossary))
        self.settings = SimpleNamespace(examples_path=examples)

    def complete(self, messages, **params):
        self.calls.append(messages)
        reply = self.replies[min(len(self.calls), len(self.replies)) - 1]
        if isinstance(reply, Exception):
            raise reply
        return Completion(json.dumps(reply), self.logprobs)


def ruling(docket="8C_1/2026", title="Unfallversicherung (Kausalzusammenhang)", filler=""):
    return {"docket": docket, "title": title, "text": RULING_TEXT.format(filler=filler)}


def test_prior_recognises_suva_accident_cases():
    p = triage.prior(ruling())
    assert p.score >= 70
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


def test_substance_signals_only_affect_ranking():
    full = triage.prior(ruling(filler="Begründung. " * 1500))
    assert "ausführlich begründet" in full.factors
    dismissed = ruling().copy()
    dismissed["text"] = dismissed["text"].replace(
        "Die Beschwerde wird abgewiesen.", "Auf die Beschwerde wird nicht eingetreten."
    )
    short = triage.prior(dismissed)
    assert short.score == full.score
    assert short.ranking < full.ranking
    assert "Nichteintreten oder Abschreibung" in short.factors


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
    ("reply", "prior", "level", "label"),
    [
        ({"relevanz": 9, "reasoning_de": "Klar.", "reasoning_fr": "Clair."}, 100, 9, "relevant"),
        ({"relevanz": "7", "reasoning_de": "Eher relevant."}, 40, 7, "relevant"),
        ({"relevanz": 3, "reasoning_de": ["Satz eins.", "Satz  zwei."]}, 40, 3, "not_relevant"),
        ({"relevanz": 12, "reasoning_de": "Zu hoch."}, 100, 9, "relevant"),
        ({"relevanz": -1, "reasoning_de": "Nein."}, 0, 0, "not_relevant"),
    ],
)
def test_parse_result_blends_level_and_prior(reply, prior, level, label):
    result = triage.parse_result(reply, "m", prior_score=prior)
    w = triage.PRIOR_WEIGHT
    assert result.score == round(100 * ((1 - w) * level / 9 + w * prior / 100))
    assert (result.label, result.model) == (label, "m")
    assert "  " not in result.reasoning_de
    assert result.reasoning_fr == reply.get("reasoning_fr", "")


@pytest.mark.parametrize("reply", [[1, 2], {"reasoning_de": "kein Score"}, {"relevanz": "hoch"}])
def test_parse_result_rejects_malformed_replies(reply):
    with pytest.raises((ValueError, KeyError)):
        triage.parse_result(reply, "m")


@pytest.mark.parametrize(
    ("text", "lang"),
    [
        (DE, "de"),
        (FR, "fr"),
        (
            "IV-Urteil, keine Änderung seit 2019, Gutachten massgeblich, Beschwerde abgewiesen.",
            "de",
        ),
        ("Assicurazione contro gli infortuni: la sentenza non è rilevante per la Suva.", "it"),
        ("Unfallversicherung (UVG).", None),
        ("", None),
    ],
)
def test_language_of_an_explanation(text, lang):
    assert triage.language(text) == lang


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Die Suva ist Partei. Stufe 7.", "Die Suva ist Partei."),
        ("Daher Grenzfall (Stufe 5-6).", "Daher Grenzfall."),
        ("La Suva est partie. Niveau de pertinence: 7.", "La Suva est partie."),
        ("Klärt die Adäquanz. Relevanz: 8 (materielles Urteil).", "Klärt die Adäquanz."),
        ("Pour une personne qualifiée, le niveau 2 est approprié.", None),
        ("Art. 6 Abs. 2 UVG ist anwendbar.", None),
    ],
)
def test_the_level_is_dropped_from_the_explanation(text, expected):
    assert triage.without_level(text) == (expected or text)


def test_expected_level_weights_the_digit_by_its_probability():
    tokens = ['{"', "reasoning_de", '":', ' "Ein Satz 7."', ', "', "relevanz", '":', " 7", "}"]
    logprobs = [TokenLogprob(t, {t: 0.0}) for t in tokens]
    logprobs[7] = TokenLogprob(" 7", {" 7": math.log(0.5), "8": math.log(0.5), "x": -1.0})
    assert triage.expected_level(logprobs) == pytest.approx(7.5)
    # A full-width digit among the alternatives must not replace the probability of its ASCII twin.
    logprobs[7] = TokenLogprob("9", {"9": -1e-6, "0": -15.6, "８": -16.0, "９": -21.4})
    assert triage.expected_level(logprobs) == pytest.approx(9.0, abs=1e-3)
    # The digit inside the reasoning is not the level.
    assert triage.expected_level(logprobs[:7]) is None
    assert triage.expected_level(None) is None


def test_triage_calls_the_llm_with_examples_and_glossary(conn, tmp_path):
    llm = FakeLLM({"reasoning_de": DE, "reasoning_fr": FR, "relevanz": 9}, tmp_path=tmp_path)
    tokens = [json.dumps({"reasoning_de": DE, "reasoning_fr": FR})[:-1] + ', "relevanz": ', "9"]
    llm.logprobs = [TokenLogprob(t, {t: 0.0}) for t in tokens + ["}"]]
    llm.logprobs[1] = TokenLogprob("9", {"9": math.log(0.5), "6": math.log(0.5)})

    result = triage.triage(conn, "8C_129/2025", llm)

    prior = triage.prior(db.get_ruling(conn, "8C_129/2025")).score
    w = triage.PRIOR_WEIGHT
    expected = round(100 * ((1 - w) * 7.5 / 9 + w * prior / 100))
    assert (result.score, result.label, result.model) == (expected, "relevant", "fake-apertus")
    assert (result.reasoning_de, result.reasoning_fr) == (DE, FR)
    assert len(llm.calls) == 1
    prompt = llm.calls[0][1]["content"]
    assert "8C_9/2025: Der Unfallbegriff" in prompt
    # The ruling's own example summary must not leak into its prompt.
    assert "8C_129/2025: Die Reinigung" not in prompt
    assert "Hold-out" not in prompt
    # Only the glossary entries that occur in the ruling.
    assert "- Kausalzusammenhang = lien de causalité" in prompt
    assert "Taggeld" not in prompt
    assert "IVG = LAI" not in prompt


def test_reasoning_in_the_wrong_language_is_rewritten(conn, tmp_path):
    llm = FakeLLM(
        {"reasoning_de": FR, "reasoning_fr": FR, "relevanz": 8},
        {"reasoning_de": DE},
        tmp_path=tmp_path,
    )
    result = triage.triage(conn, "8C_135/2025", llm)
    assert (result.reasoning_de, result.reasoning_fr) == (DE, FR)
    assert "reasoning_de" in llm.calls[1][-1]["content"]
    assert "reasoning_fr" not in llm.calls[1][-1]["content"]


def test_the_other_languages_statute_abbreviations_are_replaced(conn, tmp_path):
    llm = FakeLLM(
        {
            "reasoning_de": DE + " Art. 6 LAA, IVG/LAI, OAI.",
            "reasoning_fr": FR + " LAA/UVG",
            "relevanz": 8,
        },
        tmp_path=tmp_path,
    )
    result = triage.triage(conn, "8C_135/2025", llm)
    assert result.reasoning_de.endswith("Art. 6 UVG, IVG, IVV.")
    assert result.reasoning_fr.endswith(" LAA")
    assert len(llm.calls) == 1


def test_reasoning_that_stays_in_the_wrong_language_fails(conn, tmp_path):
    llm = FakeLLM({"reasoning_de": DE, "reasoning_fr": DE, "relevanz": 8}, tmp_path=tmp_path)
    with pytest.raises(ValueError, match="fr"):
        triage.triage(conn, "8C_135/2025", llm)
    assert len(llm.calls) == 2


def test_prefiltered_rulings_never_reach_the_llm(conn, tmp_path):
    llm = FakeLLM({"relevanz": 9}, tmp_path=tmp_path)
    result = triage.triage(conn, "4A_106/2025", llm)
    assert result.label == "not_relevant"
    assert result.model == triage.PREFILTER_MODEL
    assert "Vorprüfung" in result.reasoning_de
    assert "examen préliminaire" in result.reasoning_fr
    assert triage.wrong_language(result) == []
    assert llm.calls == []


def test_prefilter_lists_its_hints_in_both_languages():
    p = triage.prior({"docket": "9C_3/2026", "title": "Direkte Bundessteuer", "text": "ATSG"})
    result = triage.prefiltered(p)
    assert "Abteilung 9C, ATSG zitiert" in result.reasoning_de
    assert "cour 9C, LPGA citée" in result.reasoning_fr


def test_batch_reports_failures_without_stopping(conn, tmp_path):
    llm = FakeLLM(ValueError("kein JSON"), tmp_path=tmp_path)
    results = dict(triage.triage_batch(conn, db.untriaged_dockets(conn), llm, workers=2))
    assert isinstance(results["8C_129/2025"], ValueError)
    assert results["4A_106/2025"].model == triage.PREFILTER_MODEL


def test_untriaged_dockets_by_date_and_prompt_version(conn):
    db.save_triage(
        conn,
        "8C_129/2025",
        score=80,
        label="relevant",
        reasoning_de="r",
        reasoning_fr="r",
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
        reasoning_de="Deutsch",
        reasoning_fr="Français",
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
    assert (detail["triage"]["reasoning_de"], detail["triage"]["reasoning_fr"]) == (
        "Deutsch",
        "Français",
    )


def test_import_of_results_with_only_a_german_explanation(conn, tmp_path):
    path = tmp_path / "v3.jsonl"
    row = {"docket": "8C_129/2025", "score": 70, "label": "relevant", "reasoning": "Alt."}
    path.write_text(json.dumps({**row, "model": "m", "prompt_version": "v3"}) + "\n")
    assert db.import_triage(conn, path) == 1
    triage_ = db.get_ruling_detail(conn, "8C_129/2025")["triage"]
    assert (triage_["reasoning_de"], triage_["reasoning_fr"]) == ("Alt.", None)
