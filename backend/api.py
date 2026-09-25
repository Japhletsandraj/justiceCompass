"""HTTP API for JusticeCompass legal-information assessments and predictions."""

from __future__ import annotations
from ai.retrieval.explainable import predict_score_v2

import json
import os
import re
import uuid
from functools import lru_cache
from typing import Any

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from ai.retrieval.assessment import assess_question
from ai.retrieval.caselaw_loader import CaselawIndex, load_cases
from ai.retrieval.indiankanoon_client import IndianKanoonClient
from ai.retrieval.prediction import (
    PredictionEvaluator,
    PredictionResult,
    estimate_bail_outcome,
    estimate_historical_outcome,
    predict_outcome,
)
from ai.retrieval.rag_pipeline import LegalRAGPipeline

app = FastAPI(title="JusticeCompass Assessment API", version="0.3.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_rag_pipeline: LegalRAGPipeline | None = None


# ============================================================================
# Caselaw index — loaded once at startup
# ============================================================================

@lru_cache(maxsize=1)
def get_caselaw_index() -> CaselawIndex:
    """Load the full caselaw/ folder once and cache the index."""
    return CaselawIndex(load_cases())


# ============================================================================
# Request / Response schemas
# ============================================================================
_rag_pipeline: LegalRAGPipeline | None = None


def get_rag_pipeline() -> LegalRAGPipeline:
    global _rag_pipeline
    if _rag_pipeline is None:
        _rag_pipeline = LegalRAGPipeline()
    return _rag_pipeline
class AssessmentRequest(BaseModel):
    question: str = Field(min_length=8, max_length=10000)
    jurisdiction: str | None = Field(default=None, max_length=200)
    date_context: str | None = Field(default=None, max_length=1000)
    case_type: str | None = Field(default=None, max_length=100)
    region: str | None = Field(default=None, max_length=100)
    cited_section: str | None = Field(default=None, max_length=50)
    statute: str | None = Field(default=None, max_length=200)
    court_level: str | None = Field(default=None, max_length=50)
    year_from: int | None = Field(default=None, ge=1947, le=2100)
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
    severity_assessment: str
    potential_consequences: list[str]
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


class PredictRequest(BaseModel):
    question: str = Field(min_length=8, max_length=10000)
    case_type: str | None = Field(default=None, max_length=100)
    region: str | None = Field(default=None, max_length=100)
    court_level: str | None = Field(default=None, max_length=50)
    statute: str | None = Field(default=None, max_length=200)
    cited_section: str | None = Field(default=None, max_length=50)
    year_from: int | None = Field(default=None, ge=1947, le=2100)
    min_cases: int = Field(default=5, ge=1, le=1000)
    fetch_external_sources: bool = False
    max_external: int = Field(default=50, ge=1, le=200)


class ExplainablePayload(BaseModel):
    final_score: float
    base_rate_raw: float
    base_rate_calibrated: float
    likelihood_adjusted_rate: float
    evidence_adjusted_rate: float
    comparable_cases: int
    stratum: list[str] = []
    feature_contributions: dict[str, float] = {}
    basis: str = ""
    limitations: list[str] = []


class PredictResponse(BaseModel):
    request_id: str
    prediction: dict[str, Any]
    historical_outcome_estimate: dict[str, Any]
    comparable_cases: int
    basis: str
    limitations: list[str]
    model_name: str
    disclaimer: str
    matched_case_type: str | None = None
    matched_case_type_counts: dict[str, int] = Field(default_factory=dict)
    explainable: ExplainablePayload | None = None      # ← NEW


class ExplainRequest(BaseModel):
    question: str = Field(min_length=8, max_length=10000)
    case_type: str | None = Field(default=None, max_length=100)
    region: str | None = Field(default=None, max_length=100)
    court_level: str | None = Field(default=None, max_length=50)
    year_from: int | None = Field(default=None, ge=1947, le=2100)
    min_cases: int = Field(default=20, ge=1, le=1000)


class ExplainResponse(BaseModel):
    request_id: str
    matched_case_type: str | None
    explainable: ExplainablePayload
    disclaimer: str

class EvaluateRequest(BaseModel):
    y_true: list[str] = Field(min_length=1)
    y_pred: list[str] = Field(min_length=1)
    y_pred_ranked: list[list[str]] | None = None
    labels: list[str] | None = None
    k_values: list[int] = Field(default_factory=lambda: [1, 3, 5])


class EvaluateResponse(BaseModel):
    accuracy: float
    micro_f1: float
    macro_f1: float
    weighted_f1: float
    micro_precision: float
    micro_recall: float
    macro_precision: float
    macro_recall: float
    precision_per_class: dict[str, float]
    recall_per_class: dict[str, float]
    f1_per_class: dict[str, float]
    support_per_class: dict[str, int]
    top_k_accuracy: dict[int, float]
    mean_reciprocal_rank: float
    confusion_matrix: list[list[int]]
    label_order: list[str]
    n_cases: int


# ============================================================================
# Helpers
# ============================================================================

DISCLAIMER = (
    "JusticeCompass provides general legal information, not legal advice "
    "or a guarantee of court outcome. Verify current law, deadlines, and "
    "strategy with a qualified lawyer or legal-aid service."
)


# Case-type keyword patterns (keep these in sync with caselaw_loader outputs)
_CASE_TYPE_PATTERNS: list[tuple[re.Pattern, str]] = [
    # --- Criminal ---
    (re.compile(r"\b(cheque|check)\w*.*(bounce|dishonou?r|138|ni act|negotiable instrument)\w*", re.I),
     "cheque_bounce"),
    (re.compile(r"\b(498a|dowry death|304b|dowry harass\w*|matrimonial cruelty)\b", re.I),
     "dowry_harassment"),
    (re.compile(r"\b482\b|\bquash\w*\s+(?:fir|proceedings|charges?)\b", re.I),
     "quashing"),
    (re.compile(r"\b(cheat\w*|fraud\w*|420|forgery|467|468|471)\b", re.I),
     "cheating_fraud"),

    # --- Bail ---
    (re.compile(r"\banticipatory bail\b|\b438\b", re.I),
     "bail_anticipatory"),
    (re.compile(r"\bbail\w*.*(?:murder|302)\b|\b(?:murder|302)\b.*\bbail\w*\b", re.I),
     "bail_regular_murder"),
    (re.compile(r"\bbail\w*.*(?:ndps|narcotic\w*|drug\w*|ganja|heroin)\b", re.I),
     "bail_regular_narcotics"),
    (re.compile(r"\bbail\w*.*(?:rape|pocso|sexual)\b", re.I),
     "bail_regular_sexual_offense"),
    (re.compile(r"\bbail\b", re.I),
     "bail_regular_generic"),

    # --- Consumer ---
    (re.compile(r"\bdeficien\w*\s+(?:of\s+)?service\b|\bpoor service\b", re.I),
     "deficiency_service"),
    (re.compile(r"\bdefective\w*\s+(?:product|goods?)\b|\bfaulty\s+(?:product|goods?)\b", re.I),
     "defective_product"),
    (re.compile(r"\b(?:builder|real estate|flat|possession delay|rera)\b", re.I),
     "builder_delay"),
    (re.compile(r"\binsurance\b.*\b(?:claim|reject\w*|repudiat\w*)\b", re.I),
     "insurance_claim"),
    (re.compile(r"\bmedical negligence\b|\b(?:doctor|hospital)\b.*\bnegligence\b", re.I),
     "medical_negligence"),

    # --- Family ---
    (re.compile(r"\bdivorce\b|\bcruelty\b|\b13\(1\)\b", re.I),
     "divorce"),
    (re.compile(r"\bmaintenance\b|\b125 crpc\b|\balimony\b", re.I),
     "maintenance"),
    (re.compile(r"\bcustody\b|\bguardian\w*\b", re.I),
     "custody"),
    (re.compile(r"\bdomestic violence\b|\bdv act\b|\b498a\b", re.I),
     "domestic_violence"),

    # --- Tenancy / Property ---
    (re.compile(r"\bevict\w*\b|\bkabza\b", re.I),
     "eviction"),
    (re.compile(r"\brent\b.*\b(?:arrears?|due|unpaid)\b", re.I),
     "rent_arrears"),
    (re.compile(r"\bsecurity deposit\b|\bdeposit refund\b", re.I),
     "deposit_refund"),
    (re.compile(r"\btenan\w*\b|\blandlord\b|\blease\b|\bleasehold\b", re.I),
     "injunction"),
    (re.compile(r"\bspecific performance\b|\bsale agreement\b|\bsale deed\b", re.I),
     "specific_performance"),

    # --- Constitutional ---
    (re.compile(r"\bmandamus\b|\barticle\s*226\b|\bwrit of mandamus\b", re.I),
     "mandamus"),
    (re.compile(r"\barticle\s*14\b|\bequality\b|\bdiscriminat\w*\b", re.I),
     "article_14"),
    (re.compile(r"\barticle\s*21\b|\blife and liberty\b|\bpersonal liberty\b", re.I),
     "article_21"),
]


def _infer_case_type(question: str, provided: str | None) -> str | None:
    if provided:
        return provided
    for pattern, ctype in _CASE_TYPE_PATTERNS:
        if pattern.search(question):
            return ctype
    return None


def _resolve_case_type_in_index(
    idx: CaselawIndex, candidate: str | None
) -> tuple[str | None, dict[str, int]]:
    """Match a candidate case_type against what's actually in the index.

    Handles naming drift (e.g. bail_regular_murder vs bail_Regular_Murder)
    and returns the best match plus a count of near-misses.
    """
    if not candidate:
        return None, {}

    all_types = idx.all_case_types()
    if candidate in all_types:
        return candidate, {}

    lower = candidate.lower()
    # Exact case-insensitive match
    for ct in all_types:
        if ct.lower() == lower:
            return ct, {}

    # Substring / prefix match — pick the biggest bucket
    matches = {ct: n for ct, n in all_types.items()
               if lower in ct.lower() or ct.lower() in lower}
    if matches:
        best = max(matches.items(), key=lambda x: x[1])
        return best[0], matches
    return None, {}


# ============================================================================
# Routes
# ============================================================================

@app.get("/health")
def health() -> dict[str, Any]:
    idx = get_caselaw_index()
    return {
        "status": "ok",
        "service": "justicecompass-backend",
        "caselaw_loaded": len(idx.cases),
        "case_types_available": len(idx.by_case_type),
        "provider": os.getenv("LLM_PROVIDER", "openrouter"),
        "openrouter_configured": bool(os.getenv("OPENROUTER_API_KEY")),
        "indian_kanoon_configured": bool(os.getenv("INDIAN_KANOON_API_TOKEN")),
    }


@app.get("/case-types")
def case_types() -> dict[str, int]:
    """Return the case_type → count map for debugging the UI."""
    return get_caselaw_index().all_case_types()


@app.post("/assess", response_model=AssessmentResponse)
def assess(request: AssessmentRequest) -> AssessmentResponse:
    result = assess_question(
        request.question, request.jurisdiction, request.date_context
    )

    idx = get_caselaw_index()
    candidate = _infer_case_type(request.question, request.case_type)
    matched_type, _ = _resolve_case_type_in_index(idx, candidate)

    estimate_dict: dict | None = None
    if matched_type and matched_type.startswith("bail"):
        pool = idx.filter(
            case_type=matched_type,
            region=request.region,
            court_level=request.court_level,
            year_from=request.year_from,
            statute=request.statute,
            section=request.cited_section,
        )
        if pool:
            estimate_dict = estimate_bail_outcome(
                pool, region=request.region,
                cited_section=request.cited_section, min_cases=1,
            ).to_dict()
    elif matched_type:
        pool = idx.filter(
            case_type=matched_type,
            region=request.region,
            court_level=request.court_level,
            year_from=request.year_from,
        )
        if pool:
            estimate_dict = estimate_historical_outcome(
                pool, min_cases=1
            ).to_dict()

    external_sources: list[dict[str, Any]] = []
    additional_context = None
    if request.fetch_external_sources:
        try:
            client = IndianKanoonClient()
            if request.fetch_full_judgments:
                external_sources = client.search_judgments(
                    request.question,
                    max_documents=request.max_full_judgments,
                )
                additional_context = "\n\n".join(
                    f"Case number: {item.get('document_id')}\n"
                    f"Title: {item.get('title')}\n"
                    f"Outcome: {item.get('outcome') or 'Not extracted'}\n"
                    f"{item.get('text', '')[:1800]}"
                    for item in external_sources[:10]
                )
            else:
                external_sources = client.search_records(request.question)
        except (ValueError, OSError, requests.RequestException) as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Indian Kanoon request failed: {exc}",
            ) from exc

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
            raise HTTPException(
                status_code=502,
                detail=f"RAG/LLM request failed: {exc}",
            ) from exc

    structured = rag_response.structured_answer if rag_response else None
    structured_laws = (
        structured.get("applicable_law", [])
        if isinstance(structured, dict) else []
    )
    structured_steps = (
        structured.get("next_steps", [])
        if isinstance(structured, dict) else []
    )
    issue_specific_steps = structured_steps
    severity_assessment = (
        structured.get("severity_assessment", "Severity cannot be determined from the supplied facts.")
        if isinstance(structured, dict) else "Severity cannot be determined from the supplied facts."
    )
    potential_consequences = (
        structured.get("potential_consequences", [])
        if isinstance(structured, dict) else []
    )

    assessment_data = result.to_dict()
    assessment_data["applicable_laws"] = structured_laws or result.applicable_laws
    # Use the LLM steps when available; otherwise keep the assessment-layer
    # guidance visible while the model has not produced a response.
    assessment_data["immediate_steps"] = issue_specific_steps or result.immediate_steps

    return AssessmentResponse(
        request_id=str(uuid.uuid4()),
        answer=rag_response.answer if rag_response else result.concern_assessment,
        confidence_score=rag_response.confidence_score if rag_response else 0.0,
        confidence_label=rag_response.confidence_label if rag_response else "Low",
        data_sufficiency=rag_response.data_sufficiency if rag_response else "insufficient",
        source_citations=rag_response.source_citations if rag_response else [],
        context_items=[
            {
                "source": item.source,
                "text": item.text,
                "confidence": item.confidence,
                "source_type": item.source_type,
                "metadata": item.metadata,
            }
            for item in rag_response.context_items
        ] if rag_response else [],
        structured_answer=structured,
        severity_assessment=severity_assessment,
        potential_consequences=potential_consequences,
        **assessment_data,
        historical_outcome_estimate=estimate_dict,
        external_sources=external_sources,
        disclaimer=DISCLAIMER,
    )


@app.post("/predict/explain", response_model=PredictResponse)
def predict(request: PredictRequest) -> PredictResponse:
    idx = get_caselaw_index()
    candidate = _infer_case_type(request.question, request.case_type)
    matched_type, near_misses = _resolve_case_type_in_index(idx, candidate)

    # Gather records
    records = idx.filter(
        case_type=matched_type,
        region=request.region,
        court_level=request.court_level,
        year_from=request.year_from,
        statute=request.statute,
        section=request.cited_section,
    )

    # Optional external enrichment
    if request.fetch_external_sources:
        try:
            client = IndianKanoonClient()
            external = client.search_records(request.question)
            for item in external[:request.max_external]:
                records.append({
                    "outcome": (item.get("outcome") or "").lower(),
                    "region": item.get("region"),
                    "cited_sections": item.get("cited_sections", []),
                    "summary": item.get("text", ""),
                    "case_type": matched_type or "external",
                })
        except (ValueError, OSError, requests.RequestException):
            pass

    if not records:
        empty = PredictionResult(
            predicted_outcome="insufficient_data",
            predicted_label="Insufficient data",
            confidence=0.0,
            confidence_label="Low",
            historical_rate=None,
            historical_lower=None,
            historical_upper=None,
            comparable_cases=0,
            basis=(
                f"No comparable cases for case_type={matched_type!r}. "
                f"Try leaving case_type blank or check /case-types."
            ),
            limitations=[
                "This is not a probability of winning or legal advice.",
                "The comparable-case sample is empty for the selected filters.",
            ],
            class_probabilities={},
            model_name="historical-baseline",
        )
        return PredictResponse(
            request_id=str(uuid.uuid4()),
            prediction=empty.to_dict(),
            historical_outcome_estimate=empty.to_frontend(),
            comparable_cases=0,
            basis=empty.basis,
            limitations=empty.limitations,
            model_name=empty.model_name,
            disclaimer=DISCLAIMER,
            matched_case_type=matched_type,
            matched_case_type_counts=near_misses,
        )

    result = predict_outcome(
        records,
        case_type=matched_type,
        region=request.region,
        cited_section=request.cited_section,
        min_cases=request.min_cases,
    )

    return PredictResponse(
        request_id=str(uuid.uuid4()),
        prediction=result.to_dict(),
        historical_outcome_estimate=result.to_frontend(),
        comparable_cases=result.comparable_cases,
        basis=result.basis,
        limitations=result.limitations,
        model_name=result.model_name,
        disclaimer=DISCLAIMER,
        matched_case_type=matched_type,
        matched_case_type_counts=near_misses,
    )


@app.post("/evaluate", response_model=EvaluateResponse)
def evaluate(request: EvaluateRequest) -> EvaluateResponse:
    if len(request.y_true) != len(request.y_pred):
        raise HTTPException(
            status_code=400,
            detail="y_true and y_pred must be the same length.",
        )
    evaluator = PredictionEvaluator(labels=request.labels)
    if request.y_pred_ranked is not None:
        score = evaluator.evaluate_ranked(
            request.y_true, request.y_pred_ranked,
            k_values=request.k_values,
        )
    else:
        score = evaluator.evaluate(request.y_true, request.y_pred)
    return EvaluateResponse(**score.to_dict())