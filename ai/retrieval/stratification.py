# stratification.py
from collections import defaultdict
from itertools import product
from typing import Any, Dict, List, Tuple

# Dimensions that meaningfully shift outcomes within a case_type
STRATA_DIMS = {
    "bail_regular_narcotics":   ["court_level", "quantity_band"],
    "bail_regular_murder":      ["court_level", "bail_type"],
    "bail_regular_sexual_offense": ["court_level", "victim_minor"],
    "cheque_bounce":            ["notice_served", "reason_dishonour"],
    "builder_delay":            ["delay_years_band", "rera_registered"],
    "divorce":                  ["ground", "mutual_vs_contested"],
    "deposit_refund":           ["amount_band", "written_agreement"],
    "insurance_claim":          ["claim_type", "rejection_reason"],
    # ...
}


def stratum_key(case: Dict[str, Any], dims: List[str]) -> Tuple:
    """Return a hashable tuple of stratum values for a case."""
    values = []
    for dim in dims:
        v = case.get(dim)
        if v is None:
            v = case.get("case_details", {}).get(dim)
        values.append(_bucket(dim, v))
    return tuple(values)


def _bucket(dim: str, value: Any) -> str:
    """Convert a raw value into a stable bucket."""
    if value is None:
        return "unknown"
    if dim == "quantity_band":
        try:
            q = float(value)
        except (TypeError, ValueError):
            return "unknown"
        if q < 1:  return "small"
        if q < 20: return "intermediate"
        return "commercial"
    if dim == "delay_years_band":
        try:
            y = float(value)
        except (TypeError, ValueError):
            return "unknown"
        return "<1y" if y < 1 else "1-3y" if y < 3 else "3-5y" if y < 5 else "5y+"
    if dim == "amount_band":
        try:
            a = float(value)
        except (TypeError, ValueError):
            return "unknown"
        return "<50k" if a < 50_000 else "50k-5L" if a < 500_000 else "5L+"
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value).lower().strip()[:40]


def build_strata(cases: List[Dict[str, Any]]) -> Dict[str, Dict[Tuple, List[Dict]]]:
    """Return {case_type: {stratum_key: [cases]}}."""
    out = defaultdict(lambda: defaultdict(list))
    for c in cases:
        ct = c["case_type"]
        dims = STRATA_DIMS.get(ct)
        if not dims:
            out[ct][("all",)] = out[ct].get(("all",), []) + [c]
            continue
        out[ct][stratum_key(c, dims)].append(c)
    return {ct: dict(cells) for ct, cells in out.items()}