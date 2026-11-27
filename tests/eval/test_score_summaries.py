import json

import pytest

from suva.eval import score_summaries
from suva.eval.examples import EXAMPLES_PATH, load_split, read_jsonl
from suva.eval.glossary import load_glossary


@pytest.fixture(scope="module")
def examples():
    return read_jsonl(EXAMPLES_PATH)


def test_references_score_perfectly(examples):
    holdout = load_split()["holdout"]
    generated = {
        (e["docket"], lang): e[f"text_{lang}"]
        for e in examples
        if e["docket"] in holdout
        for lang in ("de", "fr")
    }
    rows = score_summaries.score_all(generated, examples, holdout, load_glossary())
    assert len(rows) == 20
    for row in rows:
        assert row["length_ratio"] == 1.0
        assert row["rouge_l"] == 1.0
        assert row["chrf"] == 100.0
        assert row["glossary_recall"] in (1.0, None)


def test_score_text_flags_style_issues():
    row = score_summaries.score_text(
        "Die Invaliditätsrente nach Art. 18 OLAA wird bestätigt (consid. 4).",
        "Die Invalidenrente nach Art. 18 UVV wird bestätigt (E. 4).",
        "de",
        load_glossary(),
    )
    assert row["style_issues"] == [
        "avoid 'Invaliditätsrente'",
        "foreign statute 'OLAA'",
        "'consid.' instead of 'E.'",
    ]
    assert row["glossary_missing"] == ["Invalidenrente"]


def test_main_writes_report(tmp_path, examples):
    by_docket = {e["docket"]: e for e in examples}
    generated = tmp_path / "generated.jsonl"
    generated.write_text(
        json.dumps(
            {"docket": "8C 78/2025", "lang": "de", "text": by_docket["8C_78/2025"]["text_de"]}
        )
        + "\n"
        + json.dumps({"docket": "8C_656/2024", "lang": "de", "text": "Kurz."})
        + "\n",
        encoding="utf-8",
    )
    out = tmp_path / "report.md"
    score_summaries.main([str(generated), "--out", str(out)])
    report = out.read_text(encoding="utf-8")
    assert "| 8C_78/2025 | de (orig) |" in report
    assert "- 8C_78/2025 fr" in report
    assert "## Skipped (not a scored docket)\n\n- 8C_656/2024 de" in report


def test_judge_prompt_and_parsing():
    prompt = score_summaries.judge_prompt("8C_78/2025", "fr", "Candidat.", "Référence.")
    assert "Ruling: 8C_78/2025" in prompt and "French" in prompt
    assert "Candidat." in prompt and "Référence." in prompt and "$" not in prompt

    answer = (
        'Here you go:\n{"legal_accuracy": 4, "coverage": 3, "style": 5, "terminology": 4, '
        '"comment": "ok"}'
    )
    assert score_summaries.parse_judgement(answer) == {
        "legal_accuracy": 4,
        "coverage": 3,
        "style": 5,
        "terminology": 4,
        "comment": "ok",
    }
    with pytest.raises(ValueError):
        score_summaries.parse_judgement(
            '{"legal_accuracy": 9, "coverage": 3, "style": 5, "terminology": 4}'
        )
    with pytest.raises(ValueError):
        score_summaries.parse_judgement('["not", "an", "object"]')
    unescaped = (
        '{"legal_accuracy": 2, "coverage": 3, "style": 2, "terminology": 4, '
        '"comment": "uses first person ("Das Bundesgericht schützt")"}'
    )
    assert score_summaries.parse_judgement(unescaped)["style"] == 2
    assert "schützt" in score_summaries.parse_judgement(unescaped)["comment"]
    with pytest.raises(KeyError):
        score_summaries.parse_judgement('{"legal_accuracy": 2, "comment": "a "b" c"}')


class FakeJudge:
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.prompts: list[str] = []

    def chat(self, messages):
        self.prompts.append(messages[-1]["content"])
        return self.reply


def test_judge_scores_reach_report(examples):
    judge = FakeJudge(
        '```json\n{"legal_accuracy": 5, "coverage": 4, "style": 4, "terminology": 3, '
        '"comment": "Fine."}\n```'
    )
    example = next(e for e in examples if e["docket"] == "8C_78/2025")
    rows = score_summaries.score_all(
        {("8C_78/2025", "de"): example["text_de"]},
        examples,
        ["8C_78/2025"],
        load_glossary(),
        judge=judge,
    )
    assert len(judge.prompts) == 1 and example["text_de"] in judge.prompts[0]
    report = score_summaries.render_report(rows, [], [], "generated.jsonl")
    assert "| legal_accuracy | 5.00 | - | 5.00 |" in report
    assert "judge: Fine." in report
