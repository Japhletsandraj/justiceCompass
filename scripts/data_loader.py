
import kagglehub
from datasets import load_dataset
import os

# Create directory if it doesn't exist
os.makedirs("data/raw", exist_ok=True)

# Load the dataset directly from Hugging Face
ds = load_dataset("SnehaDeshmukh/IndianBailJudgments-1200")

# Convert the 'train' split to a pandas DataFrame and save to CSV
df = ds["train"].to_pandas()
df.to_csv("data/raw/indianbail_1200.csv", index=False)
# constitution of india dataset
path = kagglehub.dataset_download("rushikeshdarge/constitution-of-india")

print("Path to dataset files:", path)


# data_loader.py
import json
import os
from pathlib import Path
from typing import List, Dict, Any

# Map file → domain tag override (since some files use broad tags)
FILE_DOMAIN_MAP = {
    "constitutional_cases.json": "constitutional_law",
    "consumer_cases.json":       "consumer_protection",
    "criminal_cases.json":       "criminal_law",
    "family_cases.json":         "family_law",
    "tenancy_property_cases.json": "tenancy_property",
    "indianbail_1200.json":      "bail",
}

def _extract_case_type(case: Dict[str, Any]) -> str:
    """Extract the granular case_type from either case_details or bail metadata."""
    details = case.get("case_details", {}) or {}
    # Standard case_type field
    if details.get("case_type"):
        return details["case_type"].strip().lower()

    # Bail dataset: derive from bail_type + crime_type
    if case.get("source_dataset") == "IndianBailJudgments-1200":
        bail_type = details.get("bail_type", "").strip().lower()
        crime_type = details.get("crime_type", "").strip().lower()
        if bail_type and crime_type:
            return f"bail_{bail_type}_{crime_type}".replace(" ", "_")
        if bail_type:
            return f"bail_{bail_type}"

    return "unknown"


def _extract_outcome(case: Dict[str, Any]) -> str:
    """Normalize outcomes to a canonical set for win-rate computation."""
    raw = (case.get("outcome") or "").strip().lower()
    if raw in ("allowed", "granted"):
        return "allowed"
    if raw == "partly allowed":
        return "partly_allowed"
    if raw in ("rejected", "dismissed", "quashed"):  # careful: quashed differs
        return "dismissed"
    return "unknown"


def _is_bail_dataset(case: Dict[str, Any]) -> bool:
    return case.get("source_dataset") == "IndianBailJudgments-1200"


def normalize_case(case: Dict[str, Any], source_file: str) -> Dict[str, Any]:
    """Flatten a raw case into a uniform record."""
    details = case.get("case_details", {}) or {}

    # Bail datasets use 'crime_type'; others use 'case_type'
    case_type = _extract_case_type(case)

    # For bail cases, "Granted" == favourable to accused; for other cases
    # "Allowed" means relief to petitioner (varies). We keep raw + normalized.
    outcome_raw = case.get("outcome", "Unknown")
    outcome_norm = _extract_outcome(case)

    return {
        "case_id": case.get("case_id"),
        "title": case.get("title"),
        "court": case.get("court"),
        "court_level": case.get("court_level"),
        "region": case.get("region"),
        "year": case.get("year"),
        "date": case.get("date"),
        "domain_tags": case.get("domain_tags", []),
        "case_type": case_type,              # ← THE KEY FIELD
        "source_file": source_file,
        "outcome_raw": outcome_raw,
        "outcome_norm": outcome_norm,
        "is_bail": _is_bail_dataset(case),
        "bail_type": details.get("bail_type"),
        "crime_type": details.get("crime_type"),
        "cited_sections": case.get("cited_sections", []),
        "summary": case.get("summary", ""),
        "judges": case.get("judges", []),
        "raw": case,
    }


def load_all_cases(data_dir: str) -> List[Dict[str, Any]]:
    """Load and normalize every case from all JSON files in a directory."""
    all_cases = []
    data_path = Path(data_dir)

    for file_name, _ in FILE_DOMAIN_MAP.items():
        fp = data_path / file_name
        if not fp.exists():
            print(f"[warn] missing file: {fp}")
            continue
        with open(fp, "r", encoding="utf-8") as f:
            try:
                records = json.load(f)
            except json.JSONDecodeError as e:
                print(f"[error] failed to parse {fp}: {e}")
                continue

        for rec in records:
            all_cases.append(normalize_case(rec, file_name))

    print(f"[info] loaded {len(all_cases)} cases")
    return all_cases


if __name__ == "__main__":
    cases = load_all_cases("./")
    from collections import Counter
    print("\ncase_type distribution:")
    for ct, n in Counter(c["case_type"] for c in cases).most_common(20):
        print(f"  {ct}: {n}")