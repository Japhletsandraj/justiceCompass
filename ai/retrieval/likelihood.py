from typing import Any, Dict, List

from .features import extract_features   # ← move to top, once

FAVOURABLE = {"allowed", "granted", "partly_allowed"}


def compute_likelihood_ratios(cases: List[Dict], feature_extractor) -> Dict[str, float]:
    """Naive-Bayes-style likelihood ratio per feature."""
    feature_sets = []
    for c in cases:
        text = f"{c.get('title','')} {c.get('summary','')}"
        feature_sets.append((extract_features(text), c["outcome"] in FAVOURABLE))

    wins = [f for f, w in feature_sets if w]
    losses = [f for f, w in feature_sets if not w]

    lrs: Dict[str, float] = {}
    all_features = list(feature_extractor("").keys())
    for feat in all_features:
        p_win = (sum(f[feat] for f in wins) + 1) / (len(wins) + 2)
        p_loss = (sum(f[feat] for f in losses) + 1) / (len(losses) + 2)
        lrs[feat] = p_win / max(p_loss, 1e-6)
    return lrs


def apply_likelihood_ratio(
    base_rate: float,
    user_features: Dict[str, bool],
    lrs: Dict[str, float],
) -> float:
    odds = base_rate / max(1 - base_rate, 1e-6)
    for feat, present in user_features.items():
        if present and feat in lrs:
            odds *= lrs[feat]
    return odds / (1 + odds)