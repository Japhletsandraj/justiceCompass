# Vector DB Build Handoff

## Status: ready for the next phase

The project has passed the embedding readiness check.

Verified collections:
- statutes: 3,793 records -> `knowledge_base/vectors/statutes.npy` + `knowledge_base/vectors/statutes.ids.json`
- caselaw: 1,198 records -> `knowledge_base/vectors/caselaw.npy` + `knowledge_base/vectors/caselaw.ids.json`
- crossreference: 270 records -> `knowledge_base/vectors/crossreference.npy` + `knowledge_base/vectors/crossreference.ids.json`

All vectors are float32 arrays with shape `(n, 1024)`, aligned with their IDs, and ready for ingestion into a vector database.

## What the repo already contains

Relevant source and output folders:
- `knowledge_base/vector_ready/` -> chunked and cleaned records before embedding
- `knowledge_base/vectors/` -> dense embeddings and ID alignment files
- `scripts/embed.py` -> embedding generator
- `knowledge_base/README.md` -> repository and data description

The embedding model used is:
- BAAI/bge-m3
- dimension: 1024
- normalized embeddings: enabled

This is suitable for cosine-similarity retrieval in a vector database.

## Recommended next step

Build a vector database using Qdrant, because the embedding script and repository notes explicitly treat the vectors as normalized dense vectors that can be used with cosine or dot-product search. The lexical/BM25 half is already represented in the payload and chunk text; the next stage is ingestion and retrieval orchestration.

## Required objective

The goal is to ingest all generated vectors into a searchable vector store, with each point containing:
- `id`
- `text`
- `source_collection` (statutes / caselaw / crossreference)
- `metadata` (act, section, title, citation, date, source, jurisdiction, etc.)
- `vector` (the 1024-d embedding)

## Exact process to follow

### 1) Confirm the source input files

Each collection has a JSONL source file under:
- `knowledge_base/vector_ready/statutes.jsonl`
- `knowledge_base/vector_ready/caselaw.jsonl`
- `knowledge_base/vector_ready/crossreference.jsonl`

These are the canonical payload sources. The corresponding vector files are in:
- `knowledge_base/vectors/statutes.npy`
- `knowledge_base/vectors/caselaw.npy`
- `knowledge_base/vectors/crossreference.npy`

Important: use the JSONL records as the metadata source, not the `.npy` files alone.

### 2) Load IDs and vectors

Use Python to load the arrays and align them with the IDs.

```python
import json
import numpy as np

base = "knowledge_base"

for name in ["statutes", "caselaw", "crossreference"]:
    ids = json.load(open(f"{base}/vectors/{name}.ids.json", encoding="utf-8"))
    vecs = np.load(f"{base}/vectors/{name}.npy", mmap_mode="r")
    rows = [json.loads(line) for line in open(f"{base}/vector_ready/{name}.jsonl", encoding="utf-8") if line.strip()]
    print(name, len(ids), vecs.shape[0], len(rows))
```

Expected result:
- all three collections should have matching record counts
- vector count = JSONL count = ID count

### 3) Build a payload mapping

For each row, keep the original JSON record and normalize it into Qdrant payload fields.

Minimum fields:
- `id`
- `text`
- `collection`
- `source`
- `metadata`
- `act_abbrev`
- `section_number`
- `section_title`
- `court`
- `date`
- `citation_key`

The exact payload schema should match the real records in the JSONL files. Do not drop the original text field because it is the retrievable content.

### 4) Create Qdrant collections

Recommended collection names:
- `statutes`
- `caselaw`
- `crossreference`

Use vector size 1024 and cosine distance.

Example:

```python
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

client = QdrantClient(url="http://localhost:6333")

for collection in ["statutes", "caselaw", "crossreference"]:
    client.create_collection(
        collection_name=collection,
        vectors_config=VectorParams(size=1024, distance=Distance.COSINE),
    )
```

### 5) Upsert each collection

For each collection, upload points as:
- point_id = original ID string or stable integer representation
- vector = float32 numpy vector
- payload = original JSON payload

Example pattern:

```python
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct
import json
import numpy as np

client = QdrantClient(url="http://localhost:6333")

for name in ["statutes", "caselaw", "crossreference"]:
    ids = json.load(open(f"knowledge_base/vectors/{name}.ids.json", encoding="utf-8"))
    vecs = np.load(f"knowledge_base/vectors/{name}.npy", mmap_mode="r")
    rows = [json.loads(line) for line in open(f"knowledge_base/vector_ready/{name}.jsonl", encoding="utf-8") if line.strip()]

    points = []
    for i, row in enumerate(rows):
        points.append(
            PointStruct(
                id=ids[i],
                vector=vecs[i].tolist(),
                payload=row,
            )
        )

    client.upsert(collection_name=name, wait=True, points=points)
```

### 6) Build the retrieval layer

After ingestion, add the search orchestration layer:
- dense vector search
- lexical/BM25 search (if you want hybrid retrieval)
- metadata filtering by act, jurisdiction, date, citation, court, etc.

The repo is already designed for hybrid search: the JSONL records contain searchable text and metadata, and the embedding script explicitly references lexical retrieval and hybrid ranking.

Recommended hybrid retrieval pattern:
1. Query the vector index for dense recall
2. Query the lexical index for exact legal references and citation matches
3. Merge the results using score fusion
4. Deduplicate by document ID
5. Return top-k ranked passages

### 7) Validate the database build

Before moving to app usage, validate with real legal queries such as:
- "What is the punishment under IPC section 302?"
- "Explain the bail conditions in criminal law cases"
- "Find relevant provisions on rent control in Tamil Nadu"
- "What does the Constitution say about equality?"

Check that retrieval returns:
- the correct act/section
- a valid legal source
- strong metadata alignment
- no empty or malformed vectors

## Important implementation notes

### Do not overwrite the source data

The canonical inputs are the JSONL files under `knowledge_base/vector_ready`. Do not regenerate chunk data unless you are intentionally rebuilding the whole corpus.

### Use metadata from JSONL, not from filenames

The original records contain the real structured metadata. The `.npy` files are only vectors; they are not the authoritative source for content and provenance.

### Keep the collection separation

Do not merge everything into a single vector collection at this stage.

Separate collections:
- `statutes`
- `caselaw`
- `crossreference`

This keeps retrieval, filtering, and ranking much easier and more explainable.

### Use normalized vectors

Because embeddings were L2-normalized during generation, cosine similarity is the correct and simplest search strategy. If you use dot product, it behaves consistently with cosine in this normalized setup.

## Suggested AI execution plan

An AI agent or automation script should do the following:

1. Verify vector files and ID alignment
2. Read each JSONL file to create payload metadata
3. Load `.npy` matrices and attach them to each record in order
4. Create Qdrant collections with vector size 1024 and cosine distance
5. Upsert all points in batches
6. Validate query results using a small legal benchmark
7. Then implement hybrid retrieval with lexical + dense scoring

## Minimal success criteria

The vector DB build is considered successful only when all of the following are true:
- all three collections are present in the database
- every point has a valid vector and payload
- all IDs align with the original chunk records
- retrieval answers return legal citations or sections correctly
- hybrid search and metadata filtering work on a sample of real queries

## Recommended next command sequence

From the repo root:

```bash
# activate environment
.\.venv\Scripts\activate

# optional: install vector DB client if needed
pip install qdrant-client

# start local Qdrant (if using local Docker)
docker run -p 6333:6333 -p 6334:6334 qdrant/qdrant
```

Then load the vectors with Python as shown above.

## Final state summary

This repository is already in the right state for the vector database build:
- chunks were created
- metadata was prepared
- dense embeddings were generated
- vectors are aligned with IDs
- the project is ready for ingestion and retrieval setup

The next job is not data preprocessing anymore. The next job is vector DB ingestion and retrieval orchestration.
