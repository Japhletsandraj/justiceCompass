# Indian Legal Knowledge Base

## Overview

This repository contains a legal knowledge base for Indian statutes, case law, and legal cross-references. It is designed to support retrieval, explanation, and later vector-search deployment for legal assistance workflows.

- **Last verified update:** 2026-08-16
- **Repo status:** data pipeline complete; embeddings generated and ready for vector DB ingestion
- **Core scripts:** `pdf_extractor.py`, `gazette_extractor.py`, `constitution_adapter.py`, `caselaw_adapter.py`, `ipc_bns_mapping.py`, `quality_checks.py`, `kb_builder.py`, `chunk_records.py`, `embed.py`

## Current Build Status

### Data coverage

| Domain | Statute documents | Sections | Case law |
| --- | --- | --- | --- |
| Constitutional law | 1 | 454 | 0 |
| Criminal law | 5 | 2,159 | 1,200 |
| Consumer protection | 2 | 142 | 0 |
| Family law | 3 | 130 | 0 |
| Tenancy/property | 10 | 397 | 0 |
| **Total** | **21** | **3,282** | **1,200** |

Plus:
- **270** cross-reference entries
- **3,793** statute chunks
- **1,198** case-law chunks
- **270** crossreference chunks

### Embedding readiness

The vector generation step is complete and verified.

Verified embeddings:
- `knowledge_base/vectors/statutes.npy` — 3,793 rows, shape `(3793, 1024)`, float32
- `knowledge_base/vectors/caselaw.npy` — 1,198 rows, shape `(1198, 1024)`, float32
- `knowledge_base/vectors/crossreference.npy` — 270 rows, shape `(270, 1024)`, float32

Matching ID files exist for each collection:
- `knowledge_base/vectors/statutes.ids.json`
- `knowledge_base/vectors/caselaw.ids.json`
- `knowledge_base/vectors/crossreference.ids.json`

Model used:
- `BAAI/bge-m3`
- dimension: 1024
- normalized embeddings enabled

This means the repository is ready for the next step: vector database ingestion and retrieval setup.

## Project Structure

```text
.
├── README.md
├── docs/
│   └── progress.md
├── .gitignore
├── .venv/
├── data/
│   ├── raw/
│   └── processed/
├── knowledge_base/
│   ├── README.md
│   ├── manifest.json
│   ├── statutes/
│   ├── caselaw/
│   ├── crossreference/
│   ├── vector_ready/
│   └── vectors/
├── scripts/
│   ├── pdf_extractor.py
│   ├── gazette_extractor.py
│   ├── constitution_adapter.py
│   ├── caselaw_adapter.py
│   ├── ipc_bns_mapping.py
│   ├── quality_checks.py
│   ├── kb_builder.py
│   ├── chunk_records.py
│   └── embed.py
└── ...
```

## Next Phase: Vector DB Build

The project is now past chunk generation and embedding. The next stage is to ingest the generated vectors into a vector store such as Qdrant and then layer in retrieval orchestration.

Recommended next steps:
1. ingest `knowledge_base/vectors/*.npy` into a vector database
2. map each vector to its native metadata from `knowledge_base/vector_ready/*.jsonl`
3. keep collections separate: `statutes`, `caselaw`, and `crossreference`
4. validate retrieval with legal queries before building a full app layer

## Known Limitations

- Case law is criminal-law-specific and mostly bail-focused.
- Family law and tenancy coverage remain limited by dataset scope.
- The cross-reference table is not an official concordance; it is machine-verified for section existence, not legal authority.
- Karnataka rent act extraction remains a documented failure because the source PDF is not text-readable.

## Data Integrity Notes

- No fabricated or backfilled data was added to inflate coverage.
- Provenance and source quality tracking are retained in the corpus metadata.
- Raw filenames were preserved and tagged rather than renamed to maintain source traceability.