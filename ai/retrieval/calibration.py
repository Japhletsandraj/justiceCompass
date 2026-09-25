# calibration.py
# Reference base rates from public sources (update as data changes).
# NCRB "Prison Statistics India" and NJDG give approximate trial-court grant rates.
REFERENCE_BASE_RATES = {
    "bail_regular_generic":         0.72,
    "bail_regular_murder":          0.45,
    "bail_regular_narcotics":       0.30,   # NDPS §37 rigour
    "bail_regular_sexual_offense":  0.25,
    "bail_anticipatory":            0.60,
    "cheque_bounce":                0.55,
    "builder_delay":                0.60,
    "divorce":                      0.50,
}


def bias_correction(dataset_rate: float, reference_rate: float,
                    shrinkage: float = 0.5) -> float:
    """
    Blend the dataset rate with the external reference to reduce
    selection bias. shrinkage ∈ [0,1] controls trust in the reference.
    """
    return (1 - shrinkage) * dataset_rate + shrinkage * reference_rate