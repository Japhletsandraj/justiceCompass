# Progress Log

## 2026-08-16 — Embedding and vector-readiness milestone

### Completed

- Data pipeline and knowledge-base construction progressed to the chunking and embedding stage.
- Vector-ready JSONL files were generated for all collections:
  - `knowledge_base/vector_db/records/statutes.jsonl`
  - `knowledge_base/vector_db/records/caselaw.jsonl`
  - `knowledge_base/vector_db/records/crossreference.jsonl`
- Dense embeddings were generated using `BAAI/bge-m3` with 1024-dimensional vectors.
- Validation confirmed all three collections have aligned `.npy` and `.ids.json` outputs.

### Verified output

- statutes: 3,793 rows, shape `(3793, 1024)`, float32
- caselaw: 1,198 rows, shape `(1198, 1024)`, float32
- crossreference: 270 rows, shape `(270, 1024)`, float32

### Repository status

- README normalized to the standard root name.
- Project notes moved to `docs/progress.md`.
- Virtual environment standardized to `.venv`.
- Python-generated cache and environment directories excluded via `.gitignore`.

### Current milestone

The project is ready for the next stage: vector database ingestion and retrieval orchestration.

The remaining work is not data preparation; it is database loading, retrieval testing, and hybrid search setup.

---

## Earlier build milestones

### 2026-08-05
- Initial corpus structure created for statutes, case law, and cross-reference sources.
- KB build logic established and coverage baselines recorded.

### 2026-08-16
- chunking and embedding pipeline finalized
- output validation passed for all collections
- vector DB handoff prepared

## 2026-08-22 — FAISS and BM25 retrieval milestone

### Completed

- Built a working FAISS index for the statute corpus.
- Built a working BM25 index for the statute corpus.
- Implemented a hybrid retrieval layer with dense + lexical ranking.
- Validated retrieval against live legal corpus data and confirmed ranked results.

### Verified outputs

- `knowledge_base/vector_db/indices/faiss/statutes.index`
- `knowledge_base/vector_db/indices/faiss/statutes.ids.json`
- `knowledge_base/vector_db/indices/bm25/statutes.bm25`
- `knowledge_base/vector_db/indices/bm25/statutes.ids.json`
- `retrieval/hybrid_retriever.py`

### Current milestone

The project has reached the retrieval-system handoff stage.

Next steps:
1. generate missing caselaw and crossreference vector collections
2. build all FAISS and BM25 indices for each collection
3. expose the unified hybrid retriever as a service entrypoint
4. connect retrieval results into the LLM prompt-building stage

## 2026-08-27 — Complete local vector database and retrieval system

### Completed

- Confirmed all embeddings are complete and aligned with their source records.
- Built FAISS `.index` files for statutes, caselaw, and crossreference.
- Built BM25 indices for all three collections.
- Moved retrieval code into the separate `retrieval/` package.
- Added an interactive terminal question interface: `python -m retrieval.cli`.
- Added metadata-aware hybrid retrieval with dense and lexical score fusion.

### Verified outputs

- `knowledge_base/vector_db/embeddings/`: 5,261 normalized 1024-dimensional float32 vectors.
- `knowledge_base/vector_db/indices/faiss/`: three `.index` files and aligned ID maps.
- `knowledge_base/vector_db/indices/bm25/`: three BM25 files and aligned ID maps.
- `retrieval/hybrid_retriever.py`: retrieval engine.
- `retrieval/cli.py`: terminal question interface.

### Run retrieval

```powershell
.\.venv\Scripts\python.exe -m retrieval.cli --collection statutes
```

Use `--collection caselaw` or `--collection crossreference` to search another collection.

## 2026-08-27 — Prediction preparation

### Completed

- Added the `prediction/` package for outcome-model preparation.
- Created `prediction/prepare_dataset.py` to convert case-law records into labeled examples.
- Prepared 1,198 bail-decision examples: 734 granted and 464 rejected.
- Added a chronological train/test split: 958 training examples and 240 test examples.
- Kept the outcome label separate from model input text and features to prevent target leakage.

### Scope limitation

The current data supports bail-outcome prediction only. It does not yet justify a general court-winning percentage. A future probability model needs a defined prediction event, broader representative labels, duplicate review, calibration testing, and uncertainty reporting.

## Important note

The repository is considered ready for a retrieval system handoff when the generated embeddings are searchable through real retrieval layers and tested with legal queries. At this stage, the dense and lexical retrieval foundation is working for the statute corpus, and the next phase is service integration and full-collection expansion.