"""Import manually downloaded eCourts judgment PDFs without guessed metadata."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pdfplumber

REPO = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_DIR = REPO / "data" / "raw" / "ecourts"
DEFAULT_OUTPUT = REPO / "data" / "processed" / "caselaw" / "ecourts_cases.json"

OUTCOME_LABELS = {
    "allowed": "Allowed",
    "granted": "Granted",
    "partly allowed": "Partly Allowed",
    "partly_allowed": "Partly Allowed",
    "dismissed": "Dismissed",
    "rejected": "Rejected",
    "denied": "Denied",
    "refused": "Refused",
    "withdrawn": "Withdrawn",
}
REQUIRED_METADATA = ("title", "case_type", "court", "court_level", "region", "date", "source_url")


def extract_pdf_text(pdf_path: Path) -> str:
    """Extract selectable text only; scanned pages are not OCR-guessed."""
    with pdfplumber.open(pdf_path) as pdf:
        return "\n\n".join(page.extract_text() or "" for page in pdf.pages).strip()


def _verified_outcome(metadata: dict[str, Any]) -> tuple[str, Any]:
    candidate = metadata.get("outcome")
    if metadata.get("outcome_verified") is not True:
        return "Unknown", candidate
    if not isinstance(candidate, str):
        raise ValueError("verified outcome must be a recognized string")
    normalized = " ".join(candidate.strip().lower().replace("_", " ").split())
    if normalized not in OUTCOME_LABELS:
        raise ValueError(f"unrecognized verified outcome: {candidate!r}")
    return OUTCOME_LABELS[normalized], None


def build_record(pdf_path: Path, metadata_path: Path) -> dict[str, Any]:
    with metadata_path.open("r", encoding="utf-8") as handle:
        metadata = json.load(handle)
    if not isinstance(metadata, dict):
        raise ValueError(f"{metadata_path.name} must contain a JSON object")

    missing = [key for key in REQUIRED_METADATA if not metadata.get(key)]
    if missing:
        raise ValueError(f"{metadata_path.name} is missing: {', '.join(missing)}")

    domain_tags = metadata.get("domain_tags")
    if not isinstance(domain_tags, list) or not domain_tags or not all(
        isinstance(tag, str) and tag.strip() for tag in domain_tags
    ):
        raise ValueError(f"{metadata_path.name} must include non-empty domain_tags")

    judgment_text = extract_pdf_text(pdf_path)
    if not judgment_text:
        raise ValueError(
            f"{pdf_path.name} contains no selectable text; OCR it separately "
            "and review the result before import"
        )

    outcome, outcome_candidate = _verified_outcome(metadata)
    case_details = metadata.get("case_details") or {}
    if not isinstance(case_details, dict):
        raise ValueError(f"{metadata_path.name} case_details must be a JSON object")
    case_details = dict(case_details)
    case_details["case_type"] = metadata["case_type"]

    return {
        "case_id": metadata.get("case_id"),
        "title": metadata["title"],
        "citation": metadata.get("citation"),
        "court": metadata["court"],
        "court_level": metadata["court_level"],
        "region": metadata["region"],
        "date": metadata["date"],
        "year": metadata.get("year"),
        "judges": metadata.get("judges", []),
        "domain_tags": [tag.strip() for tag in domain_tags],
        "summary": "",
        "outcome": outcome,
        "outcome_verified": metadata.get("outcome_verified") is True,
        "outcome_candidate": outcome_candidate,
        "outcome_detail": metadata.get("outcome_detail") if outcome != "Unknown" else None,
        "ratio_decidendi": "",
        "obiter_dicta": "",
        "cited_sections": metadata.get("cited_sections", []),
        "case_details": case_details,
        "judgment_text": judgment_text,
        "source_dataset": "eCourts",
        "source_url": metadata["source_url"],
        "source_record": pdf_path.name,
        "source_file": pdf_path.name,
        "extraction_method": "pdfplumber",
    }


def import_directory(input_dir: Path, output_path: Path) -> int:
    pdf_paths = sorted(input_dir.glob("*.pdf"))
    if not pdf_paths:
        raise ValueError(f"no PDF judgments found in {input_dir}")

    imported = []
    failures = []
    for pdf_path in pdf_paths:
        metadata_path = pdf_path.with_suffix(".json")
        if not metadata_path.is_file():
            failures.append(f"{pdf_path.name}: missing {metadata_path.name}")
            continue
        try:
            imported.append(build_record(pdf_path, metadata_path))
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            failures.append(f"{pdf_path.name}: {exc}")

    if failures:
        raise ValueError("Import stopped without writing output:\n" + "\n".join(failures))

    source_urls = [record["source_url"] for record in imported]
    if len(source_urls) != len(set(source_urls)):
        raise ValueError("duplicate source_url values found; resolve duplicates before import")

    existing: list[dict[str, Any]] = []
    if output_path.exists():
        with output_path.open("r", encoding="utf-8") as handle:
            existing = json.load(handle)
        if not isinstance(existing, list):
            raise ValueError(f"existing output must be a JSON array: {output_path}")

    by_url = {
        record.get("source_url"): record
        for record in existing
        if isinstance(record, dict) and record.get("source_url")
    }
    by_url.update({record["source_url"]: record for record in imported})

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_suffix(output_path.suffix + ".tmp")
    with temporary_path.open("w", encoding="utf-8") as handle:
        json.dump(list(by_url.values()), handle, ensure_ascii=False, indent=2)
    temporary_path.replace(output_path)
    return len(imported)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    try:
        count = import_directory(args.input_dir, args.output)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(f"Imported {count} eCourts PDFs into {args.output}")
    print("Only explicitly verified outcomes will contribute to prediction rates.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())