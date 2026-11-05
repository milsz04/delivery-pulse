from fastapi.testclient import TestClient

from pulse import api, llm

client = TestClient(api.app)


def test_index_page_is_served():
    resp = client.get("/")
    assert resp.status_code == 200 and "Delivery Pulse AI" in resp.text


def test_ask_endpoint(monkeypatch):
    monkeypatch.setattr(api.ask_module, "ask", lambda q: {"question": q, "answer": "42", "rows": []})
    resp = client.post("/api/ask", json={"question": "How many?"})
    assert resp.status_code == 200 and resp.json()["answer"] == "42"


def test_ask_validation_error():
    assert client.post("/api/ask", json={"question": ""}).status_code == 422


def test_llm_error_maps_to_502(monkeypatch):
    def boom(q):
        raise llm.LLMError("ANTHROPIC_API_KEY is not set")

    monkeypatch.setattr(api.ask_module, "ask", boom)
    resp = client.post("/api/ask", json={"question": "x"})
    assert resp.status_code == 502 and "ANTHROPIC_API_KEY" in resp.json()["detail"]
