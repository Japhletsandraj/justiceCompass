# eCourts Judgment Import

The eCourts Judgments and Orders portal currently requires a CAPTCHA for search. This workflow does not automate searches, solve CAPTCHAs, or assume an undocumented public API. Search and download judgments manually through the portal, subject to its current terms and access rules.

## Prepare the input

Place each downloaded, text-searchable judgment PDF in `data/raw/ecourts/`. Add a JSON sidecar with the same basename, for example `judgment-1.pdf` and `judgment-1.json`.

The sidecar must provide exact portal metadata for `title`, `case_type`, `court`, `court_level`, `region`, `date`, `source_url`, and a non-empty `domain_tags` array. For a family matter, use the matching subtype already used in the dataset, such as `divorce`, `maintenance`, `interim_maintenance`, `custody`, or `domestic_violence`, and tag it `family_law`. Add `citation`, `year`, `judges`, `cited_sections`, or `case_details` only when verified from the source.

An outcome is used in prediction only when the sidecar has both an explicitly reviewed disposition and `"outcome_verified": true`. Supported dispositions are Allowed, Granted, Partly Allowed, Dismissed, Rejected, Denied, Refused, and Withdrawn. If the disposition is unclear, omit it or set verification to false; it will be stored as Unknown and excluded from score calculations.

The importer extracts selectable PDF text. It does not invent summaries, citations, court metadata, or outcomes. Scanned PDFs without a text layer are rejected and must be OCR-processed and reviewed separately.

## Import

Run from the repository root:

```powershell
.venv\Scripts\python.exe scripts\import_ecourts_judgments.py
```

The script validates every PDF and sidecar before writing `data/processed/caselaw/ecourts_cases.json`; a failed record stops the batch without replacing the previous output. Existing records are merged by source URL. Restart the backend after importing because its case index is cached at startup.

Historical score calculations require `outcome_verified: true` only for eCourts-imported records. eCourts records without that field remain available for retrieval, but do not contribute to prediction rates until their outcomes are reviewed and marked verified. Bulk curated datasets (e.g. IndianBailJudgments-1200, Indian Kanoon) ship with pre-labeled outcomes and are trusted by default, since they are not manually reviewed sidecars.