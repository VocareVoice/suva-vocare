import json

import pytest

from suva.eval import score_triage


def test_ranking_metrics():
    relevant = {"8C_1/2025", "8C_2/2025", "8C_3/2025", "8C_4/2025"}
    scores = {"8C_1/2025": 0.9, "8C_9/2025": 0.8, "8C_2/2025": 0.7, "8C_8/2025": 0.1}
    ranked = score_triage.rank(scores)
    assert ranked == ["8C_1/2025", "8C_9/2025", "8C_2/2025", "8C_8/2025"]
    assert score_triage.precision_at(ranked, relevant, 2) == 0.5
    assert score_triage.recall_at(ranked, relevant, 3) == 0.5

    metrics = score_triage.evaluate(scores, relevant, threshold=0.75)
    assert metrics["coverage"] == 0.5
    assert metrics["precision@10"] == pytest.approx(0.2)
    assert metrics["recall@60"] == 0.5
    assert metrics["predicted_relevant"] == 2
    assert metrics["recall@threshold"] == 0.25
    assert metrics["precision@threshold"] == 0.5
    assert metrics["missed"] == [
        {"docket": "8C_3/2025", "rank": None, "score": None},
        {"docket": "8C_4/2025", "rank": None, "score": None},
    ]


def test_ties_are_broken_by_docket():
    assert score_triage.rank({"8C_10/2025": 1, "8C_9/2025": 1, "9C_1/2024": 1}) == [
        "8C_9/2025",
        "8C_10/2025",
        "9C_1/2024",
    ]


def test_relevant_outside_top_60_is_missed():
    relevant = {"8C_1/2025"}
    scores = {f"8C_{i}/2026": 1.0 for i in range(1, 61)} | {"8C_1/2025": 0.5}
    metrics = score_triage.evaluate(scores, relevant)
    assert metrics["missed"] == [{"docket": "8C_1/2025", "rank": 61, "score": 0.5}]


def test_load_triage_formats(tmp_path):
    jsonl = tmp_path / "triage.jsonl"
    jsonl.write_text(
        "\n".join(
            json.dumps(row)
            for row in [
                {"docket": "8C 78/2025", "score": 0.4},
                {"docket": "8C_78/2025", "score": 0.6},
                {"docket": "9C_65/2025", "score": "0.1"},
            ]
        ),
        encoding="utf-8",
    )
    assert score_triage.load_triage(jsonl) == {"8C_78/2025": 0.6, "9C_65/2025": 0.1}

    csv_path = tmp_path / "triage.csv"
    csv_path.write_text("docket,score\n8C_78/2025,0.6\n", encoding="utf-8")
    assert score_triage.load_triage(csv_path) == {"8C_78/2025": 0.6}

    bad = tmp_path / "bad.jsonl"
    bad.write_text(json.dumps({"docket": "unknown", "score": 1}), encoding="utf-8")
    with pytest.raises(ValueError):
        score_triage.load_triage(bad)


def test_main_against_labelled_list(tmp_path):
    relevant, unscoreable = score_triage.load_relevant()
    assert len(relevant) == 59
    assert unscoreable == ["Entscheid des Kantonsgerichts Basel-Landschaft vom 5. Februar 2026"]

    triage = tmp_path / "triage.jsonl"
    rows = [{"docket": d, "score": 1.0} for d in sorted(relevant)]
    triage.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    out = tmp_path / "report.md"
    score_triage.main([str(triage), "--out", str(out)])
    report = out.read_text(encoding="utf-8")
    assert "| coverage (relevant rulings present in the output) | 1.00 |" in report
    assert "| precision@30 | 1.00 |" in report
    assert "Kantonsgerichts Basel-Landschaft" in report
