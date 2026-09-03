from fastapi.testclient import TestClient

import backend.api as backend_api
from ai.retrieval.rag_pipeline import ContextItem, RAGResponse


class FakeRag:
    def query(self, question, collection, top_k, additional_context=None):
        return RAGResponse(
            answer="The concern requires review.",
            confidence_score=0.8,
            confidence_label="High",
            source_citations=["Test Act Section 1"],
            context_items=[ContextItem("Test Act Section 1", "Source text", 0.8, "statute", {})],
            retrieval_metrics=[],
            query=question,
            model_used="test-model",
            data_sufficiency="sufficient",
            structured_answer={
                "registrable_assessment": "possibly registrable",
                "registration_conditions": ["Confirm jurisdiction"],
                "registration_forum": "Appropriate court",
                "next_steps": ["Preserve evidence"],
            },
        )


def test_health_exposes_non_secret_status():
    response = TestClient(backend_api.app).get("/health")
    assert response.status_code == 200
    assert "openrouter_configured" in response.json()
    assert "OPENROUTER_API_KEY" not in response.text


def test_assess_returns_frontend_contract(monkeypatch):
    monkeypatch.setattr(backend_api, "get_rag_pipeline", lambda: FakeRag())
    response = TestClient(backend_api.app).post(
        "/assess",
        json={"question": "My landlord threatens eviction without notice", "jurisdiction": "Delhi"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "The concern requires review."
    assert body["structured_answer"]["next_steps"] == ["Preserve evidence"]
    assert body["source_citations"] == ["Test Act Section 1"]
    assert body["request_id"]


def test_assess_can_skip_llm(monkeypatch):
    def fail_pipeline():
        raise AssertionError("RAG should not be initialized")

    monkeypatch.setattr(backend_api, "get_rag_pipeline", fail_pipeline)
    response = TestClient(backend_api.app).post(
        "/assess",
        json={"question": "My landlord threatens eviction without notice", "include_rag_answer": False},
    )
    assert response.status_code == 200
    assert response.json()["confidence_label"] == "Low"
