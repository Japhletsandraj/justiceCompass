# predictor_v2.py
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple

from .stratification import STRATA_DIMS, build_strata, stratum_key
from .features import extract_features
from .likelihood import compute_likelihood_ratios, apply_likelihood_ratio
from .evidence import evidence_multiplier
from .calibration import REFERENCE_BASE_RATES, bias_correction

FAVOURABLE = {"allowed", "granted", "partly_allowed"}


@dataclass
class StratifiedEstimate:
    case_type: str
    stratum: Tuple
    base_rate_raw: float
    base_rate_calibrated: float
    likelihood_adjusted_rate: float
    evidence_adjusted_rate: float
    final_score: float
    comparable_cases: int
    feature_contributions: Dict[str, float]
    basis: str
    limitations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _cell_cases(index, case_type: str, features: Dict[str, bool]) -> List[Dict]:
    """Pick the most specific stratum cell that has enough cases."""
    dims = STRATA_DIMS.get(case_type, [])
    if not dims:
        return index.filter(case_type=case_type)

    # Build stratum from *user features* rather than from historical case
    user_stratum = tuple(
        _user_stratum_value(dim, features) for dim in dims
    )
    cell = index.filter(case_type=case_type, )
    matching = [c for c in cell
                if stratum_key(c, dims) == user_stratum]

    # Fallback: progressively relax dims
    if len(matching) < 10 and len(dims) > 1:
        for relax in range(1, len(dims)):
            partial = user_stratum[:len(dims) - relax]
            matching = [c for c in cell
                        if stratum_key(c, dims)[:len(dims) - relax] == partial]
            if len(matching) >= 10:
                break

    return matching or cell


def _user_stratum_value(dim: str, features: Dict[str, bool]) -> str:
    """Map a user's parsed features to a stratum dimension value."""
    mapping = {
        "quantity_band":       features.get("_qty_band", "unknown"),
        "victim_minor":        "yes" if features.get("minors_involved") else "no",
        "bail_type":           features.get("_bail_type", "regular"),
        "notice_served":       "yes" if features.get("has_written_notice") else "no",
        "reason_dishonour":    features.get("_dishonour_reason", "unknown"),
        "delay_years_band":    features.get("_delay_band", "unknown"),
        "rera_registered":     "yes" if features.get("_rera") else "no",
        "ground":              features.get("_divorce_ground", "unknown"),
        "mutual_vs_contested": features.get("_consent", "unknown"),
        "amount_band":         features.get("_amount_band", "unknown"),
        "written_agreement":   "yes" if features.get("has_written_agreement") else "no",
        "claim_type":          features.get("_claim_type", "unknown"),
        "rejection_reason":    features.get("_rejection_reason", "unknown"),
        "court_level":         "all",
    }
    return mapping.get(dim, "unknown")


def predict_score_v2(
    index,
    case_type: str,
    query: str,
    *,
    min_cases: int = 10,
) -> StratifiedEstimate:
    """Full stratified, feature-adjusted prediction."""

    # 1. Extract features from query
    user_features = extract_features(query)

    # 2. Pick comparable cell
    cell = _cell_cases(index, case_type, user_features)
    n = len(cell)

    if n == 0:
        return StratifiedEstimate(
            case_type=case_type, stratum=("all",),
            base_rate_raw=0.0, base_rate_calibrated=0.0,
            likelihood_adjusted_rate=0.0, evidence_adjusted_rate=0.0,
            final_score=0.0, comparable_cases=0,
            feature_contributions={},
            basis=f"No comparable cases found for {case_type}.",
            limitations=["Sample is empty."],
        )

    # 3. Base rate with Laplace smoothing
    wins = sum(c["outcome"] in FAVOURABLE for c in cell)
    raw_rate = (wins + 1) / (n + 2)

    # 4. Bias correction against external reference
    ref = REFERENCE_BASE_RATES.get(case_type, raw_rate)
    calibrated = bias_correction(raw_rate, ref, shrinkage=0.5 if n < 30 else 0.2)

    # 5. Likelihood ratios learned from the *same* case_type pool
    full_pool = index.filter(case_type=case_type)
    lrs = compute_likelihood_ratios(full_pool, extract_features)

    # 6. Apply likelihood ratio
    likelihood_adjusted = apply_likelihood_ratio(
        calibrated, user_features, lrs
    )

    # 7. Apply evidence-quality multiplier
    ev_mult = evidence_multiplier(user_features)
    # Convert probability to odds, apply multiplier, back
    odds = likelihood_adjusted / max(1 - likelihood_adjusted, 1e-6)
    odds *= ev_mult
    final_score = odds / (1 + odds)

    # 8. Feature contributions (for explainability panel in UI)
    contributions = {
        f: round(lrs.get(f, 1.0) if p else 1.0, 3)
        for f, p in user_features.items()
    }

    return StratifiedEstimate(
        case_type=case_type,
        stratum=("all",),
        base_rate_raw=round(raw_rate, 4),
        base_rate_calibrated=round(calibrated, 4),
        likelihood_adjusted_rate=round(likelihood_adjusted, 4),
        evidence_adjusted_rate=round(evidence_multiplier(user_features), 3),
        final_score=round(final_score, 4),
        comparable_cases=n,
        feature_contributions=contributions,
        basis=(
            f"Score conditioned on {n} comparable {case_type} cases, "
            f"adjusted for user-declared facts and evidence quality."
        ),
        limitations=[
            "This is a base-rate + likelihood-ratio estimate, not a legal opinion.",
            "Feature extraction from free text is approximate; verify with a lawyer.",
            "Historical judgments under-represent settled and uncontested matters.",
        ],
    )