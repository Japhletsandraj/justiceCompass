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
    "tenancy_property": ("rent", "tenant", "landlord", "eviction", "property", "lease", "neighbour", "neighbor", "renovation", "cement", "car damage"),
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
    if domain == "tenancy_property" and any(term in question.lower() for term in ("deposit", "security", "refund")):
        steps = [
            "Check the rental agreement for the deposit amount, refund timeline, permitted deductions, and handover terms.",
            "Ask the landlord in writing for the reason and itemized proof for every deduction, including rent, utilities, repairs, or cleaning.",
            "Send a written demand for the undisputed deposit balance, stating the tenancy dates, vacating date, amount due, and payment details.",
            "If payment is still refused, have a lawyer or legal-aid service send a formal notice and identify the appropriate recovery forum for the state.",
            "Keep the agreement, payment proof, handover record, exit photographs, utility clearances, and all messages together.",
        ]
        evidence = [
            "Rental agreement and any written deposit or deduction clause",
            "Security-deposit payment proof, rent receipts, and utility clearances",
            "Handover or vacating proof and dated photographs of the premises",
            "Written demand, landlord replies, and itemized repair or deduction records",
        ]
    elif domain == "tenancy_property" and any(term in question.lower() for term in ("neighbour", "neighbor", "renovation", "cement", "car", "damage")):
        steps = [
            "Document the damage immediately with timestamped photographs or video, a garage repair estimate, and witness details.",
            "Send the neighbour a written demand for compensation within a clear period, attaching the photographs and repair estimate.",
            "If the demand is ignored, have an advocate send a formal legal notice seeking the repair cost and any provable consequential loss.",
            "Try mediation or Lok Adalat through the local District Legal Services Authority before starting litigation.",
            "If settlement fails, ask a lawyer about a civil claim for damages in the appropriate local court and whether the renovation contractor shares liability.",
            "Make a police complaint only if the facts support a separate criminal element such as intentional damage, intimidation, or another cognizable offence.",
        ]
        evidence = [
            "Timestamped photographs or video showing cement on the vehicle and the surrounding renovation work",
            "Garage inspection report, repair estimate, invoices, and proof of consequential loss",
            "Vehicle ownership documents, witness details, messages, and the neighbour's renovation details",
            "Copies of the written demand, advocate notice, replies, mediation record, or police complaint",
        ]
    else:
        steps = [
            "Write down the exact timeline, parties, location, harm, and remedy requested.",
            "Identify the document, notice, payment, communication, or event that created the dispute.",
            "Send a factual written request for the explanation, correction, payment, or other remedy available for this issue.",
            "Check the applicable notice and limitation deadlines before choosing a court, tribunal, authority, or police route.",
            "Have a qualified lawyer or legal-aid clinic verify jurisdiction, evidence, and filing strategy where the facts remain disputed.",
        ]
        evidence = [
            "Agreement, notice, receipt, order, or police/court document connected to the issue",
            "Payment records, messages, emails, photographs, and dated communications",
            "Identity and contact details of relevant parties and witnesses",
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
