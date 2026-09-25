"""Explainable, stratified, feature-adjusted case-outcome scoring.

Produces a probability that is:

  base_rate (stratified, smoothed, bias-corrected)
    × Π likelihood_ratio(feature)
    × evidence_quality_multiplier
    → probability

Every multiplicative factor is returned, so the UI can render
a "why this score" panel.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .features import extract_features
from .likelihood import apply_likelihood_ratio, compute_likelihood_ratios
from .evidence import evidence_multiplier
from .calibration import REFERENCE_BASE_RATES, bias_correction

FAVOURABLE = {"allowed", "granted", "partly_allowed"}


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class ExplainableScore:
    case_type: str
    stratum: List[str]

    base_rate_raw: float
    base_rate_calibrated: float
    likelihood_adjusted_rate: float
    evidence_adjusted_rate: float
    final_score: float

    comparable_cases: int
    feature_contributions: Dict[str, float] = field(default_factory=dict)
    basis: str = ""
    limitations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pick_comparable_pool(
    index,
    case_type: str,
    *,
    region: Optional[str] = None,
    court_level: Optional[str] = None,
    year_from: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Return the pool of cases for this case_type, with optional filters.

    If the filtered pool is empty, progressively relax filters so the
    user never sees a hard zero when a broader pool exists.
    """
    # Attempt 1: fully filtered
    pool = index.filter(
        case_type=case_type,
        region=region,
        court_level=court_level,
        year_from=year_from,
    )
    if pool:
        return pool

    # Attempt 2: drop year
    pool = index.filter(case_type=case_type, region=region, court_level=court_level)
    if pool:
        return pool

    # Attempt 3: drop court_level
    pool = index.filter(case_type=case_type, region=region)
    if pool:
        return pool

    # Attempt 4: drop region
    pool = index.filter(case_type=case_type)
    return pool


def _raw_base_rate(cases: List[Dict[str, Any]]) -> float:
    """Laplace-smoothed favourable rate."""
    if not cases:
        return 0.0
    wins = sum(c["outcome"] in FAVOURABLE for c in cases)
    return (wins + 1) / (len(cases) + 2)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def predict_score_v2(
    index,
    case_type: str,
    query: str,
    *,
    region: Optional[str] = None,
    court_level: Optional[str] = None,
    year_from: Optional[int] = None,
    min_cases: int = 20,
) -> ExplainableScore:
    """Full stratified + likelihood-ratio + evidence-adjusted score."""

    user_features = extract_features(query)

    pool = _pick_comparable_pool(
        index, case_type,
        region=region, court_level=court_level, year_from=year_from,
    )
    n = len(pool)

    # ---- Empty pool ----
    if n == 0:
        return ExplainableScore(
            case_type=case_type,
            stratum=[],
            base_rate_raw=0.0,
            base_rate_calibrated=0.0,
            likelihood_adjusted_rate=0.0,
            evidence_adjusted_rate=1.0,
            final_score=0.0,
            comparable_cases=0,
            feature_contributions={},
            basis=f"No comparable cases found for case_type='{case_type}'.",
            limitations=[
                "This is not a probability of winning or legal advice.",
                "The comparable-case sample is empty for the selected filters.",
            ],
        )

    # ---- Layer 1: base rate ----
    raw = _raw_base_rate(pool)

    # ---- Layer 2: bias correction against external reference ----
    ref = REFERENCE_BASE_RATES.get(case_type, raw)
    shrinkage = 0.5 if n < 30 else 0.2 if n < 100 else 0.1
    calibrated = bias_correction(raw, ref, shrinkage=shrinkage)

    # ---- Layer 3: likelihood ratios learned from the *same* case_type ----
    # (learned from the *full* pool for this case_type, not the sub-filter)
    full_pool = index.filter(case_type=case_type)
    lrs = compute_likelihood_ratios(full_pool, extract_features)
    lr_adjusted = apply_likelihood_ratio(calibrated, user_features, lrs)

    # ---- Layer 4: evidence-quality multiplier ----
    ev_mult = evidence_multiplier(user_features)
    odds = lr_adjusted / max(1 - lr_adjusted, 1e-6)
    odds *= ev_mult
    final_score = odds / (1 + odds)

    # ---- Feature contributions for UI ----
    contributions = {
        feat: round(lrs.get(feat, 1.0), 3) if present else 1.0
        for feat, present in user_features.items()
    }

    # ---- Basis string ----
    if n >= min_cases:
        basis = (
            f"Base rate from {n} comparable '{case_type}' cases "
            f"({raw:.1%}), bias-corrected to {calibrated:.1%}, "
            f"then adjusted for user-declared facts and evidence quality."
        )
        limitations = [
            "This is a statistical estimate, not legal advice.",
            "Historical judgments under-represent settled and uncontested matters.",
            "Feature extraction from free text is approximate — verify with a lawyer.",
        ]
    else:
        basis = (
            f"Only {n} comparable '{case_type}' cases on file "
            f"(minimum {min_cases} recommended). Score is illustrative."
        )
        limitations = [
            "Sample size is below the reliable threshold; treat this as a weak signal.",
            "This is a statistical estimate, not legal advice.",
            "Feature extraction from free text is approximate — verify with a lawyer.",
        ]

    return ExplainableScore(
        case_type=case_type,
        stratum=[],
        base_rate_raw=round(raw, 4),
        base_rate_calibrated=round(calibrated, 4),
        likelihood_adjusted_rate=round(lr_adjusted, 4),
        evidence_adjusted_rate=round(ev_mult, 3),
        final_score=round(final_score, 4),
        comparable_cases=n,
        feature_contributions=contributions,
        basis=basis,
        limitations=limitations,
    )