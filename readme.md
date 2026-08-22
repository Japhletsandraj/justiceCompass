# JusticeCompass

## Current status

JusticeCompass has moved from raw corpus preparation into the retrieval/indexing phase. The project includes a legal corpus for statutes, case law, and cross-reference data, with generated embeddings and a working hybrid search foundation using FAISS and BM25.

### Milestone reached

- Dense vectors were generated and aligned to the legal records in the corpus.
- FAISS index creation was validated for the statute collection.
- BM25 lexical indexing was validated for the statute collection.
- A hybrid retrieval orchestrator was implemented for dense + lexical search.

### Repository layout

- `knowledge_base/` — corpus, metadata, vector-ready records, and generated indexes
- `scripts/` — extraction, embedding, and index-building scripts
- `docs/` — project notes and handoff documentation
- `data/` — raw and processed legal source files

### What comes next

The next phase is the retrieval system itself.

1. complete the remaining caselaw and crossreference vector generation
2. build FAISS indexes for all collections
3. build BM25 indexes for all collections
4. expose a shared hybrid retriever as a service/API layer
5. integrate retrieval output into the legal Q&A orchestration flow

This is the handoff from offline indexing into online retrieval for JusticeCompass.

## Verification summary

The current validated build is: statute corpus + FAISS + BM25 + hybrid retrieval prototype.

The project is ready for the next operational step: retrieval-system integration and result benchmarking.

## Relevant project notes

- See [docs/progress.md](docs/progress.md) for the build log and milestone tracking.
- See [docs/vector-db-build-handoff.md](docs/vector-db-build-handoff.md) for the retrieval architecture and handoff details.
- The current verified index assets are stored under `knowledge_base/indices/`.