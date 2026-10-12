"""Load and normalize every caselaw JSON under data/processed/caselaw/.

Produces a flat list of dicts with a uniform schema, so the prediction
engine can filter on case_type, region, court_level, year, sections.
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List


# ---------------------------------------------------------------------------
# Path resolution — walks up from this file to find data/processed/caselaw
# ---------------------------------------------------------------------------

def _find_caselaw_root() -> Path:
    """Locate data/processed/caselaw relative to the project root."""
    env = os.getenv("JUSTICECOMPASS_CASELAW_DIR")
    if env:
        return Path(env)

    here = Path(__file__).resolve()
    for parent in [here, *here.parents]:
        candidate = parent / "data" / "processed" / "caselaw"
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError(
        "Could not find data/processed/caselaw. "
        "Set JUSTICECOMPASS_CASELAW_DIR to override."
    )


CASELAW_ROOT = _find_caselaw_root()


# ---------------------------------------------------------------------------
# Per-file configuration
# ---------------------------------------------------------------------------

# Maps subfolder name -> (filename, default domain tag)
SOURCE_FILES: Dict[str, tuple[str, str]] = {
    "constitutional_law":  ("constitutional_cases.json",   "constitutional_law"),
    "consumer_protection": ("consumer_cases.json",          "consumer_protection"),
    "criminal_law":        ("criminal_cases.json",          "criminal_law"),
    "family_law":          ("family_cases.json",            "family_law"),
    "tenancy_property":    ("tenancy_property_cases.json",  "tenancy_property"),
}

# Bail dataset lives at the root, not in a subfolder
BAIL_FILE = "indianbail_1200.json"
BAIL_DOMAIN = "bail"
ECOURTS_FILE = "ecourts_cases.json"


# ---------------------------------------------------------------------------
# Outcome normalization
# ---------------------------------------------------------------------------

FAVORABLE_OUTCOMES = {"allowed", "granted", "partly_allowed", "partly allowed", "successful"}
UNFAVORABLE_OUTCOMES = {"dismissed", "rejected", "denied", "refused", "withdrawn", "quashed"}


def _normalize_outcome(raw: str | None) -> str:
    if not raw:
        return "unknown"
    r = raw.strip().lower()
    if r in ("allowed", "granted"):
        return "allowed"
    if r in ("partly allowed", "partly_allowed"):
        return "partly_allowed"
    if r in ("dismissed", "rejected", "denied", "refused"):
        return "dismissed"
    if r == "withdrawn":
        return "withdrawn"
    if r == "quashed":
        return "quashed"
    return r


# ---------------------------------------------------------------------------
# Case-type extraction
# ---------------------------------------------------------------------------

def _extract_case_type(case: Dict[str, Any]) -> str:
    details = case.get("case_details") or {}

    # Bail dataset: build a compound type from bail_type + crime_type
    if case.get("source_dataset") == "IndianBailJudgments-1200":
        bail_type = (details.get("bail_type") or "").strip().lower()
        crime_type = (details.get("crime_type") or "").strip().lower()
        crime_type = crime_type.replace(" ", "_")
        if bail_type and crime_type:
            return f"bail_{bail_type}_{crime_type}"
        if bail_type:
            return f"bail_{bail_type}"
        return "bail"

    # Standard datasets: prefer the granular case_type
    if details.get("case_type"):
        return str(details["case_type"]).strip().lower()

    return "unknown"


# ---------------------------------------------------------------------------
# Record normalization
# ---------------------------------------------------------------------------

def _normalize_record(case: Dict[str, Any], source_file: str,
                      default_domain: str) -> Dict[str, Any]:
    details = case.get("case_details") or {}
    judges = case.get("judges") or []
    sections = case.get("cited_sections") or []
    source_dataset = case.get(
        "source_dataset",
        "eCourts" if source_file == ECOURTS_FILE else "Indian Kanoon",
    )
    # Only manually imported eCourts records need an explicit review flag;
    # bulk curated datasets (e.g. IndianBailJudgments-1200, Indian Kanoon)
    # ship with pre-labeled outcomes and are trusted by default.
    outcome_verified = (
        case.get("outcome_verified") is True
        if source_dataset == "eCourts"
        else True
    )

    return {
        # Identity
        "case_id": case.get("case_id"),
        "title": case.get("title", ""),
        "citation": case.get("citation"),

        # Classification
        "case_type": _extract_case_type(case),
        "domain_tags": case.get("domain_tags") or [default_domain],
        "primary_domain": default_domain,

        # Court metadata
        "court": case.get("court"),
        "court_level": case.get("court_level"),
        "region": case.get("region"),
        "year": int(case.get("year") or 0),
        "date": case.get("date"),

        # Judges (normalized to just names)
        "judges": [
            j if isinstance(j, str) else (j or {}).get("name", "")
            for j in judges
        ],

        # Outcome
        "outcome_raw": case.get("outcome"),
        "outcome": _normalize_outcome(case.get("outcome")),
        "outcome_detail": case.get("outcome_detail"),
        "outcome_verified": outcome_verified,
        "outcome_candidate": case.get("outcome_candidate"),

        # Text
        "summary": case.get("summary", ""),
        "ratio_decidendi": case.get("ratio_decidendi", ""),
        "obiter_dicta": case.get("obiter_dicta", ""),
        "judgment_text": case.get("judgment_text", ""),

        # Legal provisions
        "cited_sections": sections,

        # Bail-specific
        "bail_type": details.get("bail_type"),
        "crime_type": details.get("crime_type"),
        "is_bail_cancellation": details.get("is_bail_cancellation", False),
        "parity_argument_used": details.get("parity_argument_used", False),

        # Provenance
        "source_file": source_file,
        "source_dataset": source_dataset,
        "source_url": case.get("source_url"),
        "source_record": case.get("source_record"),
    }


# ---------------------------------------------------------------------------
# Public loader
# ---------------------------------------------------------------------------

def load_cases(caselaw_root: Path | None = None) -> List[Dict[str, Any]]:
    """Load every case from every JSON file under caselaw/."""
    root = caselaw_root or CASELAW_ROOT
    records: List[Dict[str, Any]] = []

    # Subfolder files
    for folder, (filename, default_domain) in SOURCE_FILES.items():
        fp = root / folder / filename
        if not fp.exists():
            print(f"[caselaw] skipping missing: {fp}")
            continue
        with open(fp, "r", encoding="utf-8") as fh:
            try:
                batch = json.load(fh)
            except json.JSONDecodeError as e:
                print(f"[caselaw] JSON error in {fp}: {e}")
                continue
        for case in batch:
            records.append(_normalize_record(case, filename, default_domain))
        print(f"[caselaw] loaded {len(batch):>5} from {folder}/{filename}")

    # Bail file at root
    bail_fp = root / BAIL_FILE
    if bail_fp.exists():
        with open(bail_fp, "r", encoding="utf-8") as fh:
            try:
                batch = json.load(fh)
            except json.JSONDecodeError as e:
                print(f"[caselaw] JSON error in {bail_fp}: {e}")
                batch = []
        for case in batch:
            records.append(_normalize_record(case, BAIL_FILE, BAIL_DOMAIN))
        print(f"[caselaw] loaded {len(batch):>5} from {BAIL_FILE}")
    else:
        print(f"[caselaw] missing bail file: {bail_fp}")

    # Optional supplemental judgments exported from eCourts in the same
    # canonical case schema as the existing processed datasets.
    ecourts_fp = root / ECOURTS_FILE
    if ecourts_fp.exists():
        with open(ecourts_fp, "r", encoding="utf-8") as fh:
            try:
                batch = json.load(fh)
            except json.JSONDecodeError as e:
                print(f"[caselaw] JSON error in {ecourts_fp}: {e}")
                batch = []
        for case in batch:
            records.append(_normalize_record(case, ECOURTS_FILE, "ecourts"))
        print(f"[caselaw] loaded {len(batch):>5} from {ECOURTS_FILE}")
    else:
        print(f"[caselaw] optional eCourts file not found: {ecourts_fp}")

    print(f"[caselaw] TOTAL: {len(records)} cases loaded")
    return records


# ---------------------------------------------------------------------------
# In-memory index
# ---------------------------------------------------------------------------

class CaselawIndex:
    """Fast lookups by case_type, domain, court_level, year, section."""

    def __init__(self, cases: Iterable[Dict[str, Any]]):
        self.cases: List[Dict[str, Any]] = list(cases)
        self.by_case_type: Dict[str, List[Dict]] = defaultdict(list)
        self.by_domain: Dict[str, List[Dict]] = defaultdict(list)
        self.by_court_level: Dict[str, List[Dict]] = defaultdict(list)
        self.by_section: Dict[tuple, List[Dict]] = defaultdict(list)

        for c in self.cases:
            self.by_case_type[c["case_type"]].append(c)
            for d in c["domain_tags"]:
                self.by_domain[d].append(c)
            if c["court_level"]:
                self.by_court_level[c["court_level"]].append(c)
            for s in c["cited_sections"]:
                if isinstance(s, dict) and s.get("statute") and s.get("section"):
                    self.by_section[(s["statute"], s["section"])].append(c)

    def filter(
        self,
        *,
        case_type: str | None = None,
        domain: str | None = None,
        region: str | None = None,
        court_level: str | None = None,
        year_from: int | None = None,
        year_to: int | None = None,
        statute: str | None = None,
        section: str | None = None,
    ) -> List[Dict[str, Any]]:
        """Start from the narrowest index, then filter."""

        if case_type:
            pool = list(self.by_case_type.get(case_type, []))
        elif statute and section:
            pool = list(self.by_section.get((statute, section), []))
        elif domain:
            pool = list(self.by_domain.get(domain, []))
        elif court_level:
            pool = list(self.by_court_level.get(court_level, []))
        else:
            pool = list(self.cases)

        if domain and case_type:
            pool = [c for c in pool if domain in c["domain_tags"]]
        if region:
            pool = [c for c in pool
                    if (c["region"] or "").lower() == region.lower()]
        if court_level:
            pool = [c for c in pool if c["court_level"] == court_level]
        if year_from:
            pool = [c for c in pool if c["year"] >= year_from]
        if year_to:
            pool = [c for c in pool if c["year"] <= year_to]
        if statute and section:
            pool = [c for c in pool if any(
                isinstance(s, dict) and s.get("statute") == statute
                and str(s.get("section")) == str(section)
                for s in c["cited_sections"]
            )]
        return pool

    def all_case_types(self) -> Dict[str, int]:
        return {k: len(v) for k, v in
                sorted(self.by_case_type.items(),
                       key=lambda x: -len(x[1]))}


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    cases = load_cases()
    idx = CaselawIndex(cases)

    print("\nCase types (top 30):")
    for ct, n in list(idx.all_case_types().items())[:30]:
        print(f"  {ct:<40} {n}")

    print("\nSample filters:")
    for ct in ["cheque_bounce", "builder_delay", "divorce", "mandamus",
               "bail_Regular_Murder".lower(), "bail_regular_murder"]:
        hits = idx.filter(case_type=ct)
        print(f"  {ct:<30} → {len(hits)} cases")