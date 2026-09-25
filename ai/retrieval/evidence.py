# evidence.py
from typing import Dict

# Domain-informed weights — tune with a legal expert
EVIDENCE_WEIGHTS = {
    "has_written_notice":    1.25,   # procedural prerequisite often decisive
    "has_fir":               1.15,
    "has_medical_report":    1.20,
    "has_written_agreement": 1.30,
    "has_witnesses":         1.15,
    "has_documentary_proof": 1.20,
    "settlement_attempted":  1.05,   # slight positive: shows good faith
    "delay_mentioned":       0.95,   # delay can hurt
    "repeat_offense":        0.85,
}


def evidence_multiplier(features: Dict[str, bool]) -> float:
    m = 1.0
    for feat, present in features.items():
        if present:
            m *= EVIDENCE_WEIGHTS.get(feat, 1.0)
    # Cap the multiplier to avoid runaway scores
    return max(0.5, min(m, 3.0))
