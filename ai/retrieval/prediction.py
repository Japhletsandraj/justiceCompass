"""Conservative historical outcome estimates from comparable judgments."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable


@dataclass
class OutcomeEstimate:
    outcome: str
    estimate: float | None
    lower_bound: float | None
    upper_bound: float | None
    comparable_cases: int
    basis: str
    limitations: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def estimate_bail_outcome(
    records: Iterable[dict[str, Any]],
    *,
    region: str | None = None,
    cited_section: str | None = None,
    min_cases: int = 20,
) -> OutcomeEstimate:
    """Estimate a historical bail grant rate; return None when evidence is weak."""
    comparable = []
    for record in records:
        payload = record.get("payload") or record
        if str(payload.get("outcome", "")).lower() not in {"granted", "rejected", "denied"}:
            continue
        if region and str(payload.get("region", "")).lower() != region.lower():
            continue
        sections = payload.get("cited_sections", [])
        section_values = {str(item.get("section", "")) for item in sections if isinstance(item, dict)}
        if cited_section and cited_section not in section_values:
            continue
        comparable.append(payload)

    if len(comparable) < min_cases:
        return OutcomeEstimate(
            outcome="insufficient_data",
            estimate=None,
            lower_bound=None,
            upper_bound=None,
            comparable_cases=len(comparable),
            basis="No estimate is shown because the comparable-case sample is below the minimum threshold.",
            limitations=["Historical judgments are not a forecast of an individual case.", "The dataset may be incomplete or non-representative."],
        )

    grants = sum(str(case.get("outcome", "")).lower() == "granted" for case in comparable)
    rate = grants / len(comparable)
    margin = 1.96 * ((rate * (1 - rate) / len(comparable)) ** 0.5)
    return OutcomeEstimate(
        outcome="historical_bail_grant_rate",
        estimate=round(rate, 4),
        lower_bound=round(max(0.0, rate - margin), 4),
        upper_bound=round(min(1.0, rate + margin), 4),
        comparable_cases=len(comparable),
        basis="Observed grant rate among matching bail records in the configured dataset.",
        limitations=["This is not a probability of winning or legal advice.", "Similarity is based only on supplied metadata and cannot capture every fact considered by a judge."],
    )


def estimate_historical_outcome(
    records: Iterable[dict[str, Any]],
    *,
    min_cases: int = 20,
) -> OutcomeEstimate:
    """Estimate favorable outcome frequency for any supported case category."""
    favorable = {"allowed", "granted", "partly_allowed", "partly allowed", "successful"}
    unfavorable = {"dismissed", "rejected", "denied", "refused", "withdrawn"}
    comparable = []
    for record in records:
        payload = record.get("payload") or record
        outcome = str(payload.get("outcome", "")).lower().strip()
        if outcome in favorable or outcome in unfavorable:
            comparable.append((payload, outcome))

    if len(comparable) < min_cases:
        return OutcomeEstimate(
            outcome="insufficient_data",
            estimate=None,
            lower_bound=None,
            upper_bound=None,
            comparable_cases=len(comparable),
            basis="No estimate is shown because too few live judgments had an explicit recognized outcome.",
            limitations=["This is not a probability of winning or legal advice.", "Search results may be incomplete and outcome extraction requires review."],
        )

    rate = sum(outcome in favorable for _, outcome in comparable) / len(comparable)
    margin = 1.96 * ((rate * (1 - rate) / len(comparable)) ** 0.5)
    return OutcomeEstimate(
        outcome="historical_favorable_rate",
        estimate=round(rate, 4),
        lower_bound=round(max(0.0, rate - margin), 4),
        upper_bound=round(min(1.0, rate + margin), 4),
        comparable_cases=len(comparable),
        basis="Observed favorable-outcome rate among live judgments with explicit recognized outcomes.",
        limitations=["This is not a probability of winning or legal advice.", "Similarity and outcome labels cannot capture every fact considered by a judge."],
    )
