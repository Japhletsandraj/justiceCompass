"""Prediction engine for JusticeCompass.

Produces:
  - Historical outcome estimates from comparable cases
  - Model-based outcome predictions with confidence
  - A frontend-ready payload matching main.jsx expectations
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Sequence

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)


# ============================================================================
# PART 1: DATA CLASSES
# ============================================================================


@dataclass
class OutcomeEstimate:
    """Historical outcome estimate from comparable judgments."""

    outcome: str
    estimate: float | None
    lower_bound: float | None
    upper_bound: float | None
    comparable_cases: int
    basis: str
    limitations: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PredictionResult:
    """Full prediction output — fed directly to the frontend."""

    predicted_outcome: str
    predicted_label: str
    confidence: float
    confidence_label: str

    historical_rate: float | None
    historical_lower: float | None
    historical_upper: float | None
    comparable_cases: int
    basis: str

    limitations: list[str] = field(default_factory=list)
    class_probabilities: dict[str, float] = field(default_factory=dict)
    model_name: str = "historical-baseline"

    def to_frontend(self) -> dict[str, Any]:
        """Shape matching what main.jsx reads from
        `result.historical_outcome_estimate`."""
        return {
            "outcome": self.predicted_outcome,
            "estimate": self.historical_rate,
            "lower_bound": self.historical_lower,
            "upper_bound": self.historical_upper,
            "comparable_cases": self.comparable_cases,
            "basis": self.basis,
            "limitations": self.limitations,
            "predicted_label": self.predicted_label,
            "confidence": self.confidence,
            "confidence_label": self.confidence_label,
            "class_probabilities": self.class_probabilities,
            "model_name": self.model_name,
        }

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ============================================================================
# PART 2: CONSTANTS
# ============================================================================


FAVORABLE = {"allowed", "granted", "partly_allowed", "partly allowed", "successful"}
UNFAVORABLE = {"dismissed", "rejected", "denied", "refused", "withdrawn"}
BAIL_GRANTED_OUTCOMES = {"granted", "allowed"}
BAIL_REJECTED_OUTCOMES = {"rejected", "denied", "dismissed", "refused"}
BAIL_OUTCOMES = BAIL_GRANTED_OUTCOMES | BAIL_REJECTED_OUTCOMES

# Common outcome keywords found in Indian judgment text
_OUTCOME_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bpartly\s+allowed\b|\ballowed\s+in\s+part\b", re.I), "partly_allowed"),
    (re.compile(r"\bbail\s+(?:is\s+)?(?:granted|allowed)\b", re.I), "granted"),
    (re.compile(r"\bbail\s+(?:is\s+)?(?:rejected|denied|refused)\b", re.I), "rejected"),
    (re.compile(r"\b(?:appeal|petition|application|suit)\s+(?:is\s+)?(?:allowed|granted)\b", re.I), "allowed"),
    (re.compile(r"\b(?:appeal|petition|application|suit)\s+(?:is\s+)?(?:dismissed|rejected|denied)\b", re.I), "dismissed"),
    (re.compile(r"\bacquitted\b", re.I), "acquitted"),
    (re.compile(r"\bconvicted\b", re.I), "convicted"),
]


# ============================================================================
# PART 3: HELPERS
# ============================================================================


def _get_payload(record: dict[str, Any]) -> dict[str, Any]:
    """Return the payload dict of a record, falling back to the record itself."""
    return record.get("payload") or record.get("metadata") or record


def extract_outcome(record: dict[str, Any]) -> str | None:
    """Best-effort outcome extraction from a record.

    Checks the payload's outcome field first, then metadata aliases, then
    scans title + leading 500 characters of text for common outcome phrases.
    Returns a normalized label or None.
    """
    payload = _get_payload(record)

    # 1. Explicit outcome field
    outcome = payload.get("outcome")
    if outcome:
        return str(outcome).lower().strip()

    # 2. Metadata aliases
    for key in ("disposition", "result", "verdict", "decision", "case_outcome"):
        val = payload.get(key)
        if val:
            return str(val).lower().strip()

    # 3. Scan title + leading text
    haystack = " ".join([
        str(record.get("title", "")),
        str(payload.get("title", "")),
        str(record.get("text", ""))[:500],
        str(payload.get("text", ""))[:500],
    ])
    for pattern, label in _OUTCOME_PATTERNS:
        if pattern.search(haystack):
            return label

    return None


def _match_region(payload: dict[str, Any], region: str | None) -> bool:
    if not region:
        return True
    return str(payload.get("region", "")).lower() == region.lower()


def _match_section(payload: dict[str, Any], cited_section: str | None) -> bool:
    if not cited_section:
        return True
    sections = payload.get("cited_sections", [])
    values = {
        str(item.get("section", ""))
        for item in sections
        if isinstance(item, dict)
    }
    return cited_section in values


# ============================================================================
# PART 4: HISTORICAL ESTIMATION
# ============================================================================


def estimate_bail_outcome(
    records: Iterable[dict[str, Any]],
    *,
    region: str | None = None,
    cited_section: str | None = None,
    min_cases: int = 20,
) -> OutcomeEstimate:
    """Estimate bail grant rate from comparable cases."""
    comparable = []
    for record in records:
        payload = _get_payload(record)
        if payload.get("outcome_verified") is not True:
            continue
        outcome = extract_outcome(record)
        if outcome not in BAIL_OUTCOMES:
            continue
        if not _match_region(payload, region):
            continue
        if not _match_section(payload, cited_section):
            continue
        normalized_outcome = (
            "granted" if outcome in BAIL_GRANTED_OUTCOMES else "rejected"
        )
        comparable.append({**payload, "outcome": normalized_outcome})

    if len(comparable) < min_cases:
        return OutcomeEstimate(
            outcome="insufficient_data",
            estimate=None,
            lower_bound=None,
            upper_bound=None,
            comparable_cases=len(comparable),
            basis=(
                "No estimate is shown because the comparable-case sample "
                "is below the minimum threshold."
            ),
            limitations=[
                "Historical judgments are not a forecast of an individual case.",
                "Only manually verified outcomes are counted; the verified sample may be incomplete or non-representative.",
            ],
        )

    grants = sum(
        str(c.get("outcome", "")).lower() == "granted" for c in comparable
    )
    rate = grants / len(comparable)
    margin = 1.96 * ((rate * (1 - rate) / len(comparable)) ** 0.5)

    return OutcomeEstimate(
        outcome="historical_bail_grant_rate",
        estimate=round(rate, 4),
        lower_bound=round(max(0.0, rate - margin), 4),
        upper_bound=round(min(1.0, rate + margin), 4),
        comparable_cases=len(comparable),
        basis=(
            "Observed grant rate among matching bail records in the "
            "configured dataset."
        ),
        limitations=[
            "This is not a probability of winning or legal advice.",
            "Similarity is based only on supplied metadata and cannot "
            "capture every fact considered by a judge.",
        ],
    )


def estimate_historical_outcome(
    records: Iterable[dict[str, Any]],
    *,
    min_cases: int = 20,
) -> OutcomeEstimate:
    """Estimate favorable-outcome rate for any case category."""
    comparable = []
    for record in records:
        payload = _get_payload(record)
        if payload.get("outcome_verified") is not True:
            continue
        outcome = extract_outcome(record)
        if outcome in FAVORABLE or outcome in UNFAVORABLE:
            comparable.append(({**payload, "outcome": outcome}, outcome))

    if len(comparable) < min_cases:
        return OutcomeEstimate(
            outcome="insufficient_data",
            estimate=None,
            lower_bound=None,
            upper_bound=None,
            comparable_cases=len(comparable),
            basis=(
                "No estimate is shown because too few live judgments had "
                "an explicit recognized outcome."
            ),
            limitations=[
                "This is not a probability of winning or legal advice.",
                "Only manually verified outcomes are counted; the verified "
                "sample may be incomplete or non-representative.",
            ],
        )

    rate = (
        sum(outcome in FAVORABLE for _, outcome in comparable)
        / len(comparable)
    )
    margin = 1.96 * ((rate * (1 - rate) / len(comparable)) ** 0.5)

    return OutcomeEstimate(
        outcome="historical_favorable_rate",
        estimate=round(rate, 4),
        lower_bound=round(max(0.0, rate - margin), 4),
        upper_bound=round(min(1.0, rate + margin), 4),
        comparable_cases=len(comparable),
        basis=(
            "Observed favorable-outcome rate among live judgments with "
            "explicit recognized outcomes."
        ),
        limitations=[
            "This is not a probability of winning or legal advice.",
            "Similarity and manually verified outcome labels cannot capture "
            "every fact considered by a judge.",
        ],
    )


# ============================================================================
# PART 5: MODEL-BASED PREDICTION
# ============================================================================


class HistoricalBaselineModel:
    """Baseline predictor that uses the historical rate as its prediction."""

    def __init__(self, name: str = "historical-baseline"):
        self.name = name

    def predict(
        self,
        estimate: OutcomeEstimate,
        *,
        favorable_label: str = "favorable",
        unfavorable_label: str = "unfavorable",
    ) -> tuple[str, str, float, dict[str, float]]:
        if estimate.estimate is None:
            return ("insufficient_data", "Insufficient data", 0.0, {})

        rate = estimate.estimate
        if rate >= 0.5:
            outcome = "likely_favorable"
            label = "Favorable"
            confidence = rate
        else:
            outcome = "likely_unfavorable"
            label = "Unfavorable"
            confidence = 1.0 - rate

        return (
            outcome,
            label,
            round(confidence, 4),
            {
                favorable_label: round(rate, 4),
                unfavorable_label: round(1.0 - rate, 4),
            },
        )


# ============================================================================
# PART 6: TOP-LEVEL PREDICT FUNCTION
# ============================================================================


def predict_outcome(
    records: Iterable[dict[str, Any]],
    *,
    case_type: str | None = None,
    region: str | None = None,
    cited_section: str | None = None,
    min_cases: int = 5,
    model: HistoricalBaselineModel | None = None,
) -> PredictionResult:
    """End-to-end prediction for a single query."""
    records = list(records)
    model = model or HistoricalBaselineModel()

    if case_type == "bail":
        estimate = estimate_bail_outcome(
            records,
            region=region,
            cited_section=cited_section,
            min_cases=min_cases,
        )
    else:
        estimate = estimate_historical_outcome(records, min_cases=min_cases)

    outcome_key, label, confidence, class_probs = model.predict(estimate)

    conf_label = (
        "High" if confidence >= 0.80
        else "Medium" if confidence >= 0.50
        else "Low"
    )

    return PredictionResult(
        predicted_outcome=outcome_key,
        predicted_label=label,
        confidence=confidence,
        confidence_label=conf_label,
        historical_rate=estimate.estimate,
        historical_lower=estimate.lower_bound,
        historical_upper=estimate.upper_bound,
        comparable_cases=estimate.comparable_cases,
        basis=estimate.basis,
        limitations=estimate.limitations,
        class_probabilities=class_probs,
        model_name=model.name,
    )


# ============================================================================
# PART 7: EVALUATION (with micro / macro / weighted F1)
# ============================================================================

@dataclass
class PredictionScore:
    accuracy: float
    micro_f1: float          # ← NEW
    macro_f1: float
    weighted_f1: float
    micro_precision: float   # ← NEW
    micro_recall: float      # ← NEW
    macro_precision: float   # ← NEW
    macro_recall: float      # ← NEW
    precision_per_class: dict[str, float] = field(default_factory=dict)
    recall_per_class: dict[str, float] = field(default_factory=dict)
    f1_per_class: dict[str, float] = field(default_factory=dict)
    support_per_class: dict[str, int] = field(default_factory=dict)
    top_k_accuracy: dict[int, float] = field(default_factory=dict)
    mean_reciprocal_rank: float = 0.0
    confusion_matrix: list[list[int]] = field(default_factory=list)
    label_order: list[str] = field(default_factory=list)
    n_cases: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PredictionEvaluator:
    """Evaluate model predictions against ground truth.

    Reports micro / macro / weighted precision, recall, and F1 so the
    IEEE paper can cite all three aggregations.
    """

    def __init__(self, labels: Sequence[str] | None = None):
        self.labels = list(labels) if labels else None

    def evaluate(
        self,
        y_true: Sequence[str],
        y_pred: Sequence[str],
    ) -> PredictionScore:
        labels = self.labels or sorted(set(y_true) | set(y_pred))

        accuracy = float(accuracy_score(y_true, y_pred))

        # Micro averages (aggregate over all instances)
        micro_p = float(precision_score(y_true, y_pred, average="micro",
                                        zero_division=0))
        micro_r = float(recall_score(y_true, y_pred, average="micro",
                                     zero_division=0))
        micro_f = float(f1_score(y_true, y_pred, average="micro",
                                 zero_division=0))

        # Macro averages (mean over classes, unweighted)
        macro_p = float(precision_score(y_true, y_pred, average="macro",
                                        zero_division=0))
        macro_r = float(recall_score(y_true, y_pred, average="macro",
                                     zero_division=0))
        macro_f = float(f1_score(y_true, y_pred, average="macro",
                                 zero_division=0))

        # Weighted averages (support-weighted)
        weighted_f = float(f1_score(y_true, y_pred, average="weighted",
                                    zero_division=0))

        # Per-class breakdown
        prec = precision_score(y_true, y_pred, labels=labels,
                               average=None, zero_division=0)
        rec  = recall_score(y_true, y_pred, labels=labels,
                            average=None, zero_division=0)
        f1   = f1_score(y_true, y_pred, labels=labels,
                        average=None, zero_division=0)
        cm   = confusion_matrix(y_true, y_pred, labels=labels).tolist()

        return PredictionScore(
            accuracy=round(accuracy, 4),
            micro_f1=round(micro_f, 4),
            macro_f1=round(macro_f, 4),
            weighted_f1=round(weighted_f, 4),
            micro_precision=round(micro_p, 4),
            micro_recall=round(micro_r, 4),
            macro_precision=round(macro_p, 4),
            macro_recall=round(macro_r, 4),
            precision_per_class=dict(zip(labels, prec.tolist())),
            recall_per_class=dict(zip(labels, rec.tolist())),
            f1_per_class=dict(zip(labels, f1.tolist())),
            support_per_class={lab: list(y_true).count(lab) for lab in labels},
            top_k_accuracy={1: round(accuracy, 4)},
            confusion_matrix=cm,
            label_order=labels,
            n_cases=len(y_true),
        )

    def evaluate_ranked(
        self,
        y_true: Sequence[str],
        y_pred_ranked: Sequence[Sequence[str]],
        *,
        k_values: Sequence[int] = (1, 3, 5),
    ) -> PredictionScore:
        score = self.evaluate(y_true, [p[0] if p else "" for p in y_pred_ranked])
        top_k = {
            int(k): round(
                sum(t in p[:k] for t, p in zip(y_true, y_pred_ranked))
                / len(y_true), 4)
            for k in k_values
        }
        mrr = float(np.mean([
            1.0 / (p.index(t) + 1) if t in p else 0.0
            for t, p in zip(y_true, y_pred_ranked)
        ]))
        score.top_k_accuracy = top_k
        score.mean_reciprocal_rank = round(mrr, 4)
        return score

    def print_report(self, score: PredictionScore,
                     title: str = "PREDICTION EVALUATION") -> None:
        bar = "=" * 68
        print(bar)
        print(f"  {title}")
        print(bar)
        print(f"  Accuracy    : {score.accuracy:.4f}")
        print(f"  Micro-F1    : {score.micro_f1:.4f}   "
              f"(P={score.micro_precision:.4f} R={score.micro_recall:.4f})")
        print(f"  Macro-F1    : {score.macro_f1:.4f}   "
              f"(P={score.macro_precision:.4f} R={score.macro_recall:.4f})")
        print(f"  Weighted-F1 : {score.weighted_f1:.4f}")
        print(f"  N cases     : {score.n_cases}")
        if score.top_k_accuracy:
            for k, v in sorted(score.top_k_accuracy.items()):
                print(f"  Top-{k}       : {v:.4f}")
        if score.mean_reciprocal_rank:
            print(f"  MRR         : {score.mean_reciprocal_rank:.4f}")
        print("\n  Per-class:")
        for lab in score.label_order:
            print(
                f"    {lab:<24} P={score.precision_per_class[lab]:.3f} "
                f"R={score.recall_per_class[lab]:.3f} "
                f"F1={score.f1_per_class[lab]:.3f} "
                f"n={score.support_per_class[lab]}"
            )
        print(bar)

# ============================================================================
# SELF-TEST
# ============================================================================


if __name__ == "__main__":
    import json

    sample = (
        [{"payload": {"outcome": "granted", "region": "Delhi",
                      "cited_sections": [{"section": "302"}]}} for _ in range(30)]
        + [{"payload": {"outcome": "rejected", "region": "Delhi",
                        "cited_sections": [{"section": "302"}]}} for _ in range(20)]
    )

    result = predict_outcome(
        sample, case_type="bail", region="Delhi", cited_section="302"
    )
    print("\nFrontend payload:")
    print(json.dumps(result.to_frontend(), indent=2))