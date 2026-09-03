"""HTTP API for JusticeCompass legal-information assessments."""

from __future__ import annotations

import json
import os
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import requests

from ai.retrieval.assessment import assess_question
from ai.retrieval.indiankanoon_client import IndianKanoonClient
from ai.retrieval.prediction import estimate_bail_outcome, estimate_historical_outcome
from ai.retrieval.rag_pipeline import LegalRAGPipeline

app = FastAPI(title="JusticeCompass Assessment API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_rag_pipeline: LegalRAGPipeline | None = None


class AssessmentRequest(BaseModel):
    question: str = Field(min_length=8, max_length=10000)
    jurisdiction: str | None = Field(default=None, max_length=200)
    date_context: str | None = Field(default=None, max_length=1000)
    case_type: str | None = Field(default=None, max_length=100)
    region: str | None = Field(default=None, max_length=100)
    cited_section: str | None = Field(default=None, max_length=50)
    fetch_external_sources: bool = False
    fetch_full_judgments: bool = False
    max_full_judgments: int = Field(default=20, ge=1, le=20)
    include_rag_answer: bool = True


class AssessmentResponse(BaseModel):
    request_id: str
    answer: str
    confidence_score: float
    confidence_label: str
    data_sufficiency: str
    source_citations: list[str]
    context_items: list[dict[str, Any]]
    structured_answer: dict[str, Any] | None
    concern_assessment: str
    legal_domain: str
    jurisdiction: str | None
    legal_issues: list[str]
    applicable_laws: list[str]
    immediate_steps: list[str]
    evidence_to_collect: list[str]
    possible_forums: list[str]
    deadlines: list[str]
    missing_information: list[str]
    professional_help_needed: bool
    historical_outcome_estimate: dict | None
    external_sources: list[dict]
    disclaimer: str


def get_rag_pipeline() -> LegalRAGPipeline:
    global _rag_pipeline
    if _rag_pipeline is None:
        _rag_pipeline = LegalRAGPipeline()
    return _rag_pipeline


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "justicecompass-backend",
        "provider": os.getenv("LLM_PROVIDER", "openrouter"),
        "model": os.getenv("LLM_MODEL") or os.getenv("OPENROUTER_MODEL"),
        "openrouter_configured": bool(os.getenv("OPENROUTER_API_KEY")),
        "indian_kanoon_configured": bool(os.getenv("INDIANKANOON_API_TOKEN")),
    }


@app.post("/assess", response_model=AssessmentResponse)
def assess(request: AssessmentRequest) -> AssessmentResponse:
    import uuid

    result = assess_question(request.question, request.jurisdiction, request.date_context)
    estimate = None
    external_sources = []
    additional_context = None
    if request.fetch_external_sources:
        try:
            client = IndianKanoonClient()
            if request.fetch_full_judgments:
                external_sources = client.search_judgments(
                    request.question,
                    max_documents=request.max_full_judgments,
                )
                estimate = estimate_historical_outcome(external_sources, min_cases=5).to_dict()
                additional_context = "\n\n".join(
                    f"Case number: {item.get('document_id')}\nTitle: {item.get('title')}\nOutcome: {item.get('outcome') or 'Not confidently extracted'}\n{item.get('text', '')}"
                    for item in external_sources
                )
            else:
                external_sources = client.search_records(request.question)
        except (ValueError, OSError, requests.RequestException) as exc:
            raise HTTPException(status_code=502, detail=f"Indian Kanoon request failed: {exc}") from exc
    if request.case_type == "bail" and estimate is None:
        root_dir = os.path.dirname(os.path.abspath(__file__))
        case_path = os.path.join(root_dir, "knowledge_base", "caselaw", "criminal_law", "indianbail_1200.json")
        with open(case_path, "r", encoding="utf-8") as handle:
            records = json.load(handle)
        estimate = estimate_bail_outcome(
            records,
            region=request.region,
            cited_section=request.cited_section,
        ).to_dict()

    rag_response = None
    if request.include_rag_answer:
        try:
            rag_response = get_rag_pipeline().query(
                request.question,
                collection="all",
                top_k=5,
                additional_context=additional_context,
            )
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"RAG/LLM request failed: {exc}") from exc

    structured = rag_response.structured_answer if rag_response else None
    return AssessmentResponse(
        request_id=str(uuid.uuid4()),
        answer=rag_response.answer if rag_response else result.concern_assessment,
        confidence_score=rag_response.confidence_score if rag_response else 0.0,
        confidence_label=rag_response.confidence_label if rag_response else "Low",
        data_sufficiency=rag_response.data_sufficiency if rag_response else "insufficient",
        source_citations=rag_response.source_citations if rag_response else [],
        context_items=[
            {"source": item.source, "text": item.text, "confidence": item.confidence, "source_type": item.source_type}
            for item in rag_response.context_items
        ] if rag_response else [],
        structured_answer=structured,
        **result.to_dict(),
        historical_outcome_estimate=estimate,
        external_sources=external_sources,
        disclaimer=(
            "JusticeCompass provides general legal information, not legal advice or a guarantee of court outcome. "
            "Verify current law, deadlines, and strategy with a qualified lawyer or legal-aid service."
        ),
    )
