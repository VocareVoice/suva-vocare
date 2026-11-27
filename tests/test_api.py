import pytest
from fastapi.testclient import TestClient

from suva import api, summarize


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
