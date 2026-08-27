# Vector Database Assets

This directory contains the offline retrieval assets for JusticeCompass.

## Layout

- `records/` - canonical chunked JSONL records and preprocessing report
- `embeddings/` - normalized BAAI/bge-m3 vectors, aligned IDs, and build metadata
- `indices/faiss/` - FAISS inner-product indices for dense retrieval
- `indices/bm25/` - BM25 indices and aligned IDs for lexical retrieval
- `retriever.py` - hybrid dense and lexical retrieval implementation
- `legacy_embeddings/` - older JSONL export retained for provenance and compatibility

Each collection uses the same name in `records/`, `embeddings/`, and both index directories:
`statutes`, `caselaw`, and `crossreference`.

The authoritative payload and metadata source is `records/*.jsonl`. Embedding rows and index ID maps must remain in the same order as those records.

## Build order

From the repository root:

```powershell
.\.venv\Scripts\python.exe scripts\chunk_records.py
.\.venv\Scripts\python.exe scripts\embed.py --run
.\.venv\Scripts\python.exe scripts\build_faiss_indices.py
.\.venv\Scripts\python.exe scripts\build_bm25_indices.py
.\.venv\Scripts\python.exe scripts\validate_retrieval.py
```

`embed.py --run` resumes interrupted collections using checkpoint files in `embeddings/`.
