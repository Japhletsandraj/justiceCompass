"""Structured legal concern assessment and action planning."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class LegalAssessment:
    concern_assessment: str
    legal_domain: str
    jurisdiction: str | None
    legal_issues: list[str] = field(default_factory=list)
    applicable_laws: list[str] = field(default_factory=list)
    immediate_steps: list[str] = field(default_factory=list)
    evidence_to_collect: list[str] = field(default_factory=list)
    possible_forums: list[str] = field(default_factory=list)
    deadlines: list[str] = field(default_factory=list)
    missing_information: list[str] = field(default_factory=list)
    professional_help_needed: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_DOMAIN_KEYWORDS = {
    "criminal": ("arrest", "police", "fir", "bail", "crime", "accused", "criminal"),
    "family": ("divorce", "custody", "maintenance", "marriage", "domestic violence"),
    "consumer": ("consumer", "refund", "defective", "service", "seller", "product"),
    "employment": ("salary", "termination", "employer", "job", "workplace", "employee"),
    "tenancy_property": ("rent", "tenant", "landlord", "eviction", "property", "lease"),
    "constitutional": ("fundamental right", "discrimination", "writ", "constitutional"),
}


def classify_domain(question: str) -> str:
    text = question.lower()
    scores = {domain: sum(term in text for term in terms) for domain, terms in _DOMAIN_KEYWORDS.items()}
    domain, score = max(scores.items(), key=lambda item: item[1])
    return domain if score else "unknown"


def assess_question(
    question: str,
    jurisdiction: str | None = None,
    date_context: str | None = None,
) -> LegalAssessment:
    """Create a cautious triage assessment without claiming legal validity."""
    domain = classify_domain(question)
    missing = []
    if not jurisdiction:
        missing.append("Country, state, and city where the events occurred")
    if not date_context:
        missing.append("Important event dates and whether any notice or court deadline has passed")
    if len(question.split()) < 8:
        missing.append("A factual timeline, parties involved, and the harm or remedy requested")

    issue = (
        "The facts may indicate a legal concern requiring further review."
        if domain != "unknown"
        else "The question may involve a legal concern, but the legal area cannot yet be identified."
    )
    steps = [
        "Write a dated timeline using only facts you can support.",
        "Preserve original documents, messages, notices, photographs, and transaction records.",
        "Avoid deleting evidence or contacting the other party in a way that could escalate risk.",
        "Have a qualified lawyer or legal-aid clinic verify jurisdiction, deadlines, and filing strategy.",
    ]
    evidence = [
        "Identity and contact details of relevant parties",
        "Contracts, notices, receipts, orders, or police/court documents",
        "Messages, emails, call records, photographs, and witness details",
    ]
    forums = [
        "The appropriate local court, tribunal, police authority, or statutory grievance body must be confirmed for this jurisdiction."
    ]

    return LegalAssessment(
        concern_assessment=issue,
        legal_domain=domain,
        jurisdiction=jurisdiction,
        legal_issues=[f"Potential {domain.replace('_', ' ')} issue"],
        immediate_steps=steps,
        evidence_to_collect=evidence,
        possible_forums=forums,
        missing_information=missing,
    )
