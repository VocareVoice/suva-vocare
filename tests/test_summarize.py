import json
from dataclasses import replace

import pytest

from suva import db, summarize
from suva.eval.examples import SPLIT_PATH, load_split
from suva.llm import parse_json

RULING = """Bundesgericht
Tribunal fédéral
8C_1/2026
Urteil vom 5. Januar 2026
IV. öffentlich-rechtliche Abteilung
Besetzung
Bundesrichterin Viscione, Präsidentin,
Bundesrichter Maillard, Métral,
Bundesrichterinnen Heine, Scherrer Reber,
Gerichtsschreiber Grünvogel.
Verfahrensbeteiligte
Schweizerische Unfallversicherungsanstalt (Suva), Fluhmattstrasse 1, 6002 Luzern,
Beschwerdeführerin,
gegen
A.________,
Beschwerdegegner.
Gegenstand
Unfallversicherung (Kausalzusammenhang),

Sachverhalt:
A.
A.________ stürzte am 3. März 2024. Die Suva stellte die Leistungen per 30. Juni 2024 ein.
B.
Das kantonale Gericht hiess die Beschwerde gut.

Erwägungen:
1.
Die Beschwerde ist zulässig.
2.
2.1. Die Leistungspflicht setzt einen natürlichen Kausalzusammenhang voraus (Art. 6 Abs. 1 UVG).
2.2. Der Versicherte war zu 20 % arbeitsunfähig.
3.
Die Gerichtskosten werden dem Beschwerdegegner auferlegt (Art. 66 Abs. 1 BGG).

Demnach erkennt das Bundesgericht:
1.
Die Beschwerde wird gutgeheissen. Der Einspracheentscheid der Suva wird bestätigt.
2.
Die Gerichtskosten von Fr. 800.- werden dem Beschwerdegegner auferlegt.
3.
Dieses Urteil wird den Parteien schriftlich mitgeteilt.
Luzern, 5. Januar 2026
"""

GOOD_DE = (
    "Der Versicherte stürzte. Die Suva stellte die Leistungen per 30. Juni 2024 ein.\n\n"
    "Auf Beschwerde des Versicherten hin hiess das kantonale Gericht die Beschwerde gut.\n\n"
    "Das Bundesgericht erinnert daran, dass die Leistungspflicht einen natürlichen "
    "Kausalzusammenhang voraussetzt (Art. 6 Abs. 1 UVG; E. 2.1).\n\n"
    # The closing sentence copies an example's outcome; the pipeline must correct it.
    "Letztlich wies das Bundesgericht die Beschwerde der Suva ab."
)
GOOD_FR = (
    "L'assuré a chuté. La Suva a mis fin aux prestations au 30 juin 2024.\n\n"
    "Saisi d'un recours de l'assuré, le tribunal cantonal l'a admis.\n\n"
    "Le Tribunal fédéral rappelle que l'obligation de prester suppose un lien de causalité "
    "naturelle (art. 6 al. 1 LAA; consid. 2.1).\n\n"
    "En définitive, le Tribunal fédéral a admis le recours de la Suva."
)


class FakeLLM:
    model = "fake-apertus"

    def __init__(self, draft_de=GOOD_DE, draft_fr=GOOD_FR, claims=()):
        self.draft = {"de": draft_de, "fr": draft_fr}
        self.claims = list(claims)
        self.prompts: list[list[dict]] = []

    def chat(self, messages, **params):
        self.prompts.append(messages)
        task = messages[-1]["content"]
        if "Answer with JSON only" in task:
            return json.dumps({"claims": self.claims})
        if "List the conclusions" in task:
            return "E. 2.1: Die Leistungspflicht setzt einen natürlichen Kausalzusammenhang voraus."
        lang = "de" if "German summary" in task else "fr"
        if "found these problems" in task:
            return self.draft[lang].replace("CHF 999.-", "CHF 800.-")
        return self.draft[lang]

    def chat_json(self, messages, **params):
        return parse_json(self.chat(messages, **params))


@pytest.fixture
def ruling(conn):
    db.upsert_ruling(
        conn,
        {"docket": "8C_1/2026", "decision_date": "2026-01-05", "language": "de", "text": RULING},
    )
    return db.get_ruling(conn, "8C_1/2026")


def test_split_sections_drops_costs_and_signature():
    sections = summarize.split_sections(RULING)
    assert sections["header"].startswith("Bundesgericht")
    assert sections["facts"].startswith("Sachverhalt:")
    assert "2.1. Die Leistungspflicht" in sections["reasons"]
    assert sections["ruling"].endswith("Der Einspracheentscheid der Suva wird bestätigt.")
    assert "Gerichtskosten" not in sections["ruling"] + sections["reasons"]


def test_five_judges_counts_the_bench():
    assert summarize.five_judges(summarize.split_sections(RULING)["header"])
    three = "Composition\nMme et MM. les Juges fédéraux Viscione, Présidente, Maillard et Métral.\n"
    assert not summarize.five_judges(three + "Greffière : Mme Fretz Perrin.")


def test_appellant_and_outcome():
    header = summarize.split_sections(RULING)["header"]
    assert summarize.appellant(header) == ("suva", True)
    assert summarize.result("Le recours est partiellement admis.") == "partly upheld"
    assert summarize.result("Die Beschwerde wird abgewiesen, soweit darauf einzutreten ist.") == (
        "dismissed"
    )
    assert summarize.result("Auf die Beschwerde wird nicht eingetreten.") == "inadmissible"
    case = summarize.Case("8C_1/2026", "", "insured", True, "Le recours est rejeté.", "dismissed")
    assert summarize.outcome_sentence(case, "fr") == (
        "En définitive, le Tribunal fédéral a rejeté le recours de l'assurée."
    )
    wrong = "Faits.\n\nEn définitive, le Tribunal fédéral a rejeté le recours de la Suva."
    assert summarize.fix_outcome(wrong, case, "fr").endswith("le recours de l'assurée.")
    right = "Faits.\n\nLe recours de l'assurée est rejeté."
    assert summarize.fix_outcome(right, case, "fr") == right


def test_form_issues_find_rule_violations(ruling):
    sections = summarize.split_sections(ruling["text"])
    case = summarize.Case("8C_1/2026", sections["reasons"], "suva", True, "", "upheld")
    draft = (
        "Dr. med. D. bestätigte 35 %. Die Vaudoise wandte Art. 99 UVG an. Die Opposition wurde "
        "abgewiesen."
    )
    issues = " | ".join(summarize.form_issues(draft, case, "de"))
    for expected in ("Dr. med. D.", "35 %", "UVG 99", "Vaudoise", "Einsprache", "(E. 4.2)"):
        assert expected in issues.replace("art. 99 UVG", "UVG 99")
    clean = "Die Leistungspflicht setzt einen Kausalzusammenhang voraus (E. 2.1). 20 %."
    assert summarize.form_issues(clean, case, "de") == []


def test_clean_applies_house_conventions():
    text = "**Résumé:** La CNA a versé 16'751 fr. 65 selon l'Art. 6 LAA."
    assert summarize.clean(text, "fr") == "La Suva a versé CHF 16'751.65 selon l'art. 6 LAA."
    assert summarize.clean("Gemäss Art. 6 lit. g UVV, Fr. 800.-, Straße.", "de") == (
        "Gemäss Art. 6 Bst. g UVV, CHF 800.-, Strasse."
    )
    assert summarize.clean(
        "Der 1987 geborene Versicherte A. stürzte. Der Suvaarzt, Dr. med. D., hielt fest, z. B. "
        "die Beurteilung des Dr. med. E. (E. 4.2).",
        "de",
    ) == (
        # The name in the genitive stays for `finish`; deleting it would break the sentence.
        "Der Versicherte stürzte. Der Suvaarzt hielt fest, z. B. die Beurteilung des Dr. med. E. "
        "(E. 4.2)."
    )
    assert summarize.clean("L'assurée, née en 1971, a chuté.", "fr") == "L'assurée a chuté."
    assert summarize.clean("Der A.________ erhielt.", "de") == "Der A.________ erhielt."
    assert summarize.clean("Unter diesen Umständen wies es die Beschwerde der Suva gut.", "de") == (
        "Unter diesen Umständen hiess es die Beschwerde der Suva gut."
    )
    assert summarize.clean("(E. 4.2; Erw. 5)", "fr") == "(consid. 4.2; consid. 5)"
    assert summarize.clean("(consid. 4.2; Erw.5)", "de") == "(E. 4.2; E. 5)"


def test_few_shots_are_the_evaluators_summaries_never_held_out():
    held_out = set(load_split(SPLIT_PATH)["holdout"])
    for lang in ("de", "fr"):
        dockets = [docket for docket, _ in summarize.few_shots(lang, "8C_1/2026")]
        assert dockets == list(summarize.STYLE_EXAMPLES)
        assert not held_out & set(dockets)
    # German prompts get the corrected rendering of the French original, not the translation.
    de = dict(summarize.few_shots("de", "8C_1/2026"))
    assert "Valideneinkommen" in de["8C_7/2025"]
    assert "8C_7/2025" not in dict(summarize.few_shots("fr", "8C_7/2025"))


def test_summarize_writes_both_languages_from_the_ruling(conn, ruling):
    llm = FakeLLM()
    texts = summarize.summarize(conn, "8C_1/2026", llm)

    assert set(texts) == {"de", "fr"}
    # The wrong outcome copied from an example is replaced from the operative part.
    assert "Letztlich hiess das Bundesgericht die Beschwerde der Suva gut." in texts["de"]
    assert texts["fr"].endswith("le recours de la Suva.\n\nDécision à cinq.")
    assert texts["de"].endswith("Fünfer-Entscheid.")
    tasks = [messages[-1]["content"] for messages in llm.prompts]
    drafts = [task for task in tasks if "summary of this ruling" in task]
    # German (the ruling's language) first; French from the ruling with the corrected German
    # summary as outline.
    assert "Write the German summary" in drafts[0]
    assert "Write the French summary" in drafts[1]
    assert "Die Beschwerde der Suva gut." in drafts[1].replace("die Beschwerde", "Die Beschwerde")
    assert all("2.1. Die Leistungspflicht" in task for task in tasks)
    # The Court's conclusions are extracted once and handed to both drafts.
    assert "List the conclusions" in tasks[0]
    assert len(drafts) == 2 and all("E. 2.1: Die Leistungspflicht" in task for task in drafts)
    assert all("Gerichtskosten" not in task for task in tasks)
    # The check sees the rules only, never the few-shot examples.
    checks = [m for m in llm.prompts if "Answer with JSON only" in m[-1]["content"]]
    assert checks and all("Example 1" not in m[0]["content"] for m in checks)
    assert "Example 1 (8C_7/2025)" in llm.prompts[1][0]["content"]


def test_unsupported_claims_and_ungrounded_figures_are_revised(conn, ruling):
    claim = {"draft": "x", "ruling": "y", "supported": False, "fix": "z"}
    llm = FakeLLM(draft_de=GOOD_DE + " CHF 999.-", claims=[claim])
    texts = summarize.summarize(conn, "8C_1/2026", llm)
    revisions = [
        m[-1]["content"] for m in llm.prompts if "found these problems" in m[-1]["content"]
    ]
    assert any("CHF 999" in task and '"x" is not supported' in task for task in revisions)
    assert "CHF 999" not in texts["de"]


def test_dockets_to_summarize(conn, ruling):
    for docket, score in (("8C_129/2025", 90), ("8C_135/2025", 40), ("8C_1/2026", 70)):
        db.save_triage(
            conn,
            docket,
            score=score,
            label="relevant",
            reasoning_de="",
            reasoning_fr=None,
            model="m",
            prompt_version="v",
        )
    pick = {"min_score": 50, "prompt_version": summarize.PROMPT_VERSION}
    assert db.dockets_to_summarize(conn, **pick) == ["8C_129/2025", "8C_1/2026"]
    db.save_summary(
        conn, "8C_129/2025", lang="de", text="t", model="m", prompt_version=summarize.PROMPT_VERSION
    )
    db.save_summary(conn, "8C_1/2026", lang="de", text="t", model="m", prompt_version="old")
    assert db.dockets_to_summarize(conn, **pick) == ["8C_1/2026"]


def test_long_reasons_are_condensed_chunk_by_chunk(conn, ruling, monkeypatch):
    monkeypatch.setattr(summarize, "SOURCE_BUDGET", 800)
    monkeypatch.setattr(summarize, "CHUNK_SIZE", 120)
    llm = FakeLLM()
    summarize.summarize(conn, "8C_1/2026", llm)
    notes = [m[-1]["content"] for m in llm.prompts if "of the reasons of" in m[-1]["content"]]
    assert len(notes) >= 2 and "Part 1 of" in notes[0]
    assert "Reasons (condensed from the full text)" in llm.prompts[-1][-1]["content"]


@pytest.mark.parametrize(
    "closing",
    [
        # Mixed-up verb, a party that did not appeal, a trailing legal aid sentence.
        "Letztlich wies das Bundesgericht die Beschwerde der IV-Stelle gut.",
        "Letztlich wies das Bundesgericht die Beschwerde des Versicherten ab und bestätigte die "
        "Verfügung der IV-Stelle des Kantons St. Gallen vom 22. August 2024.",
        "Letztlich hiess das Bundesgericht die Beschwerde der IV-Stelle gut. Dem Versicherten "
        "wurde die unentgeltliche Rechtspflege gewährt (E. 6).",
    ],
)
def test_fix_outcome_replaces_wrong_closing_sentences(closing):
    case = summarize.Case(
        "8C_185/2025", "", "iv", True, "Die Beschwerde wird gutgeheissen.", "upheld"
    )
    text = f"Sachverhalt (E. 1).\n\nErwägungen (E. 5.2). {closing}"
    fixed = summarize.fix_outcome(text, case, "de")
    assert fixed == (
        "Sachverhalt (E. 1).\n\nErwägungen (E. 5.2).\n\n"
        "Letztlich hiess das Bundesgericht die Beschwerde der IV-Stelle gut."
    )
    assert summarize.fix_outcome(fixed, case, "de") == fixed


def test_contradicting_languages_are_revised(conn, ruling):
    class Contradicting(FakeLLM):
        def chat(self, messages, **params):
            if "German summary:" in messages[-1]["content"]:
                self.prompts.append(messages)
                wrong = {"de": "a", "fr": "b", "ruling": "c", "wrong": "de", "fix": "d"}
                return json.dumps({"contradictions": [wrong]})
            return super().chat(messages, **params)

    llm = Contradicting()
    summarize.summarize(conn, "8C_1/2026", llm)
    revisions = [
        m[-1]["content"] for m in llm.prompts if "found these problems" in m[-1]["content"]
    ]
    assert len(revisions) == 1 and "contradicts the other language" in revisions[0]
    assert "Output only the revised German summary" in revisions[0]


def test_finish_replaces_names_by_roles_and_flags_suva_outside_its_cases():
    named = "Der Versicherte stürzte, wie Dr. med. D. festhielt (E. 2.1)."

    class Renaming(FakeLLM):
        def chat(self, messages, **params):
            self.prompts.append(messages)
            if "Replace each of these anonymised names" in messages[-1]["content"]:
                return "Der Versicherte stürzte, wie der Suvaarzt festhielt (E. 2.1)."
            # The general revision keeps the name, as Apertus often does.
            return named

    header = summarize.split_sections(RULING)["header"]
    assert summarize.parties(header).startswith("Schweizerische Unfallversicherungsanstalt")
    case = summarize.Case("8C_1/2026", RULING, "suva", True, "", None, suva_party=True)
    system = {"role": "system", "content": ""}
    text = summarize.finish(Renaming(), case, system, "de", named)
    assert text == "Der Versicherte stürzte, wie der Suvaarzt festhielt (E. 2.1)."
    insurer = "Die Suva stellte die Leistungen ein (E. 2.1)."
    issues = summarize.form_issues(insurer, replace(case, suva_party=False), "de")
    assert any("Suva is not a party" in issue for issue in issues)
