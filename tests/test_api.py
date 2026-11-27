import pytest
from fastapi.testclient import TestClient

from suva import api, db, summarize


class FakeLLM:
    model = "fake-apertus"


@pytest.fixture
def client(conn, monkeypatch):
    def fake_summarize(conn, docket, llm):
        return {"de": f"Zusammenfassung {docket}", "fr": f"Résumé {docket}"}

    monkeypatch.setattr(summarize, "summarize", fake_summarize)
    api.app.dependency_overrides[api.get_conn] = lambda: conn
    api.app.dependency_overrides[api.get_llm] = FakeLLM
    yield TestClient(api.app)
    api.app.dependency_overrides.clear()


def test_list_and_search(client):
    body = client.get("/api/rulings").json()
    assert body["total"] == 3
    body = client.get("/api/rulings", params={"q": "Rente", "sort": "date"}).json()
    assert [item["docket"] for item in body["items"]] == ["8C_135/2025"]


def test_detail_and_unknown(client):
    detail = client.get("/api/rulings/8C_129/2025").json()
    assert detail["docket"] == "8C_129/2025"
    assert "Kausalzusammenhang" in detail["text"]
    assert detail["triage"] is None
    assert detail["summaries"] == {"de": None, "fr": None}
    assert client.get("/api/rulings/1C_1/2000").status_code == 404


def test_summarize_on_demand(client):
    response = client.post("/api/rulings/8C_129/2025/summarize")
    assert response.status_code == 200
    summaries = response.json()["summaries"]
    assert summaries["de"]["text"] == "Zusammenfassung 8C_129/2025"
    assert summaries["fr"]["model"] == "fake-apertus"
    listed = client.get("/api/rulings", params={"q": "Kausalzusammenhang"}).json()
    assert listed["items"][0]["has_summary"] is True


def test_feedback(client):
    response = client.post(
        "/api/rulings/8C_135/2025/feedback",
        json={"verdict": "relevant", "corrected_score": 85, "comment": "Leitentscheid"},
    )
    assert response.status_code == 201
    assert response.json()["feedback"][0]["corrected_score"] == 85
    bad = client.post("/api/rulings/8C_135/2025/feedback", json={"verdict": "maybe"})
    assert bad.status_code == 422


def test_serves_frontend(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "<html" in response.text


def test_list_filters_and_order(client, conn):
    for docket, score, label, reasoning in [
        ("8C_129/2025", 90, "relevant", "UVG"),
        ("4A_106/2025", 5, "not_relevant", "Miete"),
    ]:
        db.save_triage(
            conn,
            docket,
            score=score,
            label=label,
            reasoning_de=reasoning,
            reasoning_fr=f"FR {reasoning}",
            model=None,
            prompt_version=None,
        )

    def dockets(**params):
        items = client.get("/api/rulings", params=params).json()["items"]
        return [item["docket"] for item in items]

    assert dockets() == ["8C_129/2025", "4A_106/2025", "8C_135/2025"]
    assert dockets(order="asc") == ["4A_106/2025", "8C_129/2025", "8C_135/2025"]
    assert dockets(sort="date", order="asc") == ["4A_106/2025", "8C_129/2025", "8C_135/2025"]
    assert dockets(sort="docket", order="asc") == ["4A_106/2025", "8C_129/2025", "8C_135/2025"]
    assert dockets(sort="title", order="asc")[0] == "8C_135/2025"
    assert dockets(max_score=50) == ["4A_106/2025"]
    assert dockets(language="fr") == ["8C_135/2025"]
    assert dockets(division="I. zivilrechtliche Abteilung") == ["4A_106/2025"]
    client.post("/api/rulings/8C_135/2025/summarize")
    assert dockets(has_summary=True) == ["8C_135/2025"]
    assert dockets(has_summary=False) == ["8C_129/2025", "4A_106/2025"]
    body = client.get("/api/rulings", params={"limit": 1}).json()
    assert body["stats"] == {
        "total": 3,
        "relevant": 1,
        "with_summary": 1,
        "relevant_without_summary": 1,
    }
    item = body["items"][0]
    assert (item["reasoning_de"], item["reasoning_fr"]) == ("UVG", "FR UVG")
    detail = client.get("/api/rulings/8C_129/2025").json()
    assert (detail["triage"]["reasoning_de"], detail["triage"]["reasoning_fr"]) == ("UVG", "FR UVG")
    assert item["feedback_verdict"] is None


def test_facets(client):
    body = client.get("/api/facets").json()
    assert body["total"] == 3
    assert body["demo"] is False
    assert body["date_min"] == "2025-09-25"
    assert {"value": "fr", "count": 1} in body["languages"]
    assert len(body["divisions"]) == 2
