import json

import pytest

from scripts import import_ecourts_judgments as importer


def _write_case_files(tmp_path, *, outcome_verified=False):
    pdf_path = tmp_path / "judgment-1.pdf"
    pdf_path.write_bytes(b"placeholder")
    metadata = {
        "title": "Copy exact title from portal",
        "case_type": "divorce",
        "court": "Copy exact court from portal",
        "court_level": "High Court",
        "region": "Delhi",
        "date": "2025-01-15",
        "year": 2025,
        "domain_tags": ["family_law"],
        "source_url": "https://judgments.ecourts.gov.in/example-real-record",
        "outcome": "Allowed",
        "outcome_verified": outcome_verified,
    }
    pdf_path.with_suffix(".json").write_text(
        json.dumps(metadata), encoding="utf-8"
    )
    return pdf_path, pdf_path.with_suffix(".json")


def test_import_preserves_pdf_text_but_does_not_trust_unverified_outcome(
    tmp_path, monkeypatch
):
    pdf_path, metadata_path = _write_case_files(tmp_path)
    monkeypatch.setattr(
        importer, "extract_pdf_text", lambda _: "Text extracted from the judgment PDF."
    )

    record = importer.build_record(pdf_path, metadata_path)

    assert record["judgment_text"] == "Text extracted from the judgment PDF."
    assert record["outcome"] == "Unknown"
    assert record["outcome_verified"] is False
    assert record["outcome_candidate"] == "Allowed"
    assert record["summary"] == ""


def test_import_accepts_only_explicitly_verified_outcome(tmp_path, monkeypatch):
    pdf_path, metadata_path = _write_case_files(tmp_path, outcome_verified=True)
    monkeypatch.setattr(importer, "extract_pdf_text", lambda _: "Actual judgment text.")

    record = importer.build_record(pdf_path, metadata_path)

    assert record["outcome"] == "Allowed"
    assert record["outcome_verified"] is True
    assert record["source_dataset"] == "eCourts"


def test_import_refuses_pdf_without_selectable_text(tmp_path, monkeypatch):
    pdf_path, metadata_path = _write_case_files(tmp_path)
    monkeypatch.setattr(importer, "extract_pdf_text", lambda _: "")

    with pytest.raises(ValueError, match="no selectable text"):
        importer.build_record(pdf_path, metadata_path)