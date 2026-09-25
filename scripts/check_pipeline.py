"""One-shot check: load caselaw, run predictions, print micro-F1."""

from ai.retrieval.caselaw_loader import CaselawIndex, load_cases
from ai.retrieval.prediction import (
    PredictionEvaluator,
    predict_outcome,
    estimate_bail_outcome,
    estimate_historical_outcome,   # ← ADD THIS LINE
)

cases = load_cases()
idx = CaselawIndex(cases)

print("\n=== CASE TYPE BUCKETS ===")
for ct, n in list(idx.all_case_types().items())[:25]:
    print(f"  {ct:<42} {n}")

print("\n=== SAMPLE PREDICTIONS ===")
samples = [
    ("cheque_bounce",     None,   None),
    ("builder_delay",     None,   None),
    ("divorce",           None,   None),
    ("mandamus",          None,   None),
    ("bail_regular_murder", "Delhi", None),
]
for ct, region, sec in samples:
    pool = idx.filter(case_type=ct, region=region)
    if not pool:
        print(f"  [{ct}] 0 cases")
        continue
    if ct.startswith("bail"):
        est = estimate_bail_outcome(pool, region=region,
                                     cited_section=sec, min_cases=1)
    else:
        est = estimate_historical_outcome(pool, min_cases=1)
    print(f"  [{ct:<24}] n={est.comparable_cases:>4} "
          f"rate={est.estimate}")

# --- Micro-F1 demo: pretend to predict 'allowed' for all 'divorce' cases ---
divorce = idx.filter(case_type="divorce")
y_true = [c["outcome"] for c in divorce]
y_pred = ["allowed"] * len(y_true)

evaluator = PredictionEvaluator()
score = evaluator.evaluate(y_true, y_pred)
evaluator.print_report(score, title="DIVORCE (dummy predictor)")