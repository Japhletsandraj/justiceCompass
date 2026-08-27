# Retrieval System

This package provides local hybrid retrieval over the JusticeCompass legal corpus.

- Dense retrieval: FAISS `IndexFlatIP` over normalized BGE-M3 embeddings
- Lexical retrieval: BM25 over the canonical vector-ready records
- Ranking: configurable weighted score fusion

## Ask questions in the terminal

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m retrieval.cli --collection statutes
```

Available collections are `statutes`, `caselaw`, and `crossreference`.

Useful options:

```powershell
.\.venv\Scripts\python.exe -m retrieval.cli --collection caselaw --top-k 5 --alpha 0.6
```

Type a question at `Question>` and type `exit` to quit.

## Storage

The retrieval code is separate from the stored database assets:

```text
knowledge_base/vector_db/
  records/       canonical JSONL payloads
  embeddings/    .npy vectors and aligned IDs
  indices/
    faiss/       .index files and aligned IDs
    bm25/        serialized lexical indices and aligned IDs
retrieval/
  hybrid_retriever.py
  cli.py
```

Rebuild the local indices after changing records or embeddings:

```powershell
.\.venv\Scripts\python.exe scripts\build_faiss_indices.py
.\.venv\Scripts\python.exe scripts\build_bm25_indices.py
```
