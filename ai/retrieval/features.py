# features.py
import re
from typing import Dict, Any

FEATURE_PATTERNS = {
    "has_written_notice":     r"\b(notice|legal notice|demand letter|138 notice)\b",
    "has_fir":                r"\b(fir|first information report|police complaint)\b",
    "has_medical_report":     r"\b(medical report|mlc|injury report|post[- ]?mortem)\b",
    "has_written_agreement":  r"\b(agreement|contract|written|deed|mou)\b",
    "has_witnesses":          r"\b(witness|eyewitness|bystander|neighbour)\b",
    "has_documentary_proof":  r"\b(receipt|invoice|bank statement|whatsapp|email|sms)\b",
    "settlement_attempted":   r"\b(settlement|compromise|mediation|negotiat)\b",
    "delay_mentioned":        r"\b(delay|late|overdue|pending for)\b",
    "repeat_offense":         r"\b(second time|again|repeat|previous case)\b",
    "custody_involved":       r"\b(custody|detention|arrest(ed)?)\b",
    "minors_involved":        r"\b(minor|child|below 18|juvenile)\b",
    "domestic_context":       r"\b(husband|wife|in[- ]laws|dowry|matrimonial)\b",
    "commercial_context":     r"\b(company|firm|business|contractor|builder)\b",
    "government_party":       r"\b(state|government|municipal|authority|department)\b",
}


def extract_features(query: str) -> Dict[str, bool]:
    q = query.lower()
    return {name: bool(re.search(pat, q)) for name, pat in FEATURE_PATTERNS.items()}