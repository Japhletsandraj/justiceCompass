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

## Recommended architecture: FAISS + BM25 Hybrid Retrieval

Based on your JusticeCompass architecture diagram (Fig. 1), the vector DB implementation uses:

1. **Dense Semantic Retrieval (FAISS)**: Fast approximate nearest neighbor search on normalized embeddings
2. **Lexical Retrieval (BM25)**: Exact legal reference and citation matching
3. **Hybrid Ranking**: Score fusion combining dense and lexical results

This hybrid approach is critical for legal search because:
- Dense retrieval captures semantic intent ("What is punishment for murder?")
- BM25 retrieval captures exact references ("IPC section 302", "bail conditions")
- Legal users often search by citation or specific legal concepts that require exact matches

## Required objective

The goal is to build searchable vector and lexical indices, with each point containing:
- `id`
- `text`
- `source_collection` (statutes / caselaw / crossreference)
- `metadata` (act, section, title, citation, date, source, jurisdiction, etc.)
- `vector` (the 1024-d embedding for FAISS)

Additionally, create a BM25 index for lexical retrieval alongside FAISS.

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

For each row, keep the original JSON record and normalize it into payload fields.

Minimum fields:
- `id`
- `text` (raw legal text for BM25 indexing)
- `collection` (statutes / caselaw / crossreference)
- `source`
- `act_abbrev`
- `section_number`
- `section_title`
- `court`
- `date`
- `citation_key`
- `jurisdiction`
- `metadata` (additional structured fields)

The exact payload schema should match the real records in the JSONL files. **Keep the original text field because it is both the retrievable content AND the source for BM25 indexing.**

### 4) Create FAISS indices for dense retrieval

Install FAISS and set up separate indices for each collection:

```bash
pip install faiss-cpu
# or for GPU:
pip install faiss-gpu
```

Python code to build FAISS indices:

```python
import faiss
import json
import numpy as np

base = "knowledge_base"
faiss_dir = "knowledge_base/indices/faiss"

for name in ["statutes", "caselaw", "crossreference"]:
    # Load vectors
    vecs = np.load(f"{base}/vectors/{name}.npy", mmap_mode="r").astype('float32')
    
    # Create FAISS index
    # Use IndexFlatIP for normalized vectors (dot product = cosine similarity)
    index = faiss.IndexFlatIP(1024)
    index.add(vecs)
    
    # Save index and ID mapping
    faiss.write_index(index, f"{faiss_dir}/{name}.faiss")
    
    # Save ID mapping
    ids = json.load(open(f"{base}/vectors/{name}.ids.json"))
    json.dump(ids, open(f"{faiss_dir}/{name}.ids.json", "w"))
    
    print(f"Built FAISS index for {name}: {index.ntotal} vectors")
```

**Important**: Use `IndexFlatIP` (Inner Product / dot product) for normalized vectors, which is mathematically equivalent to cosine similarity.

### 5) Create BM25 indices for lexical retrieval

Install BM25 and build text indices:

```bash
pip install rank-bm25
```

Python code to build BM25 indices:

```python
import json
from rank_bm25 import BM25Okapi
import pickle

base = "knowledge_base"
bm25_dir = "knowledge_base/indices/bm25"

for name in ["statutes", "caselaw", "crossreference"]:
    # Load JSONL records
    rows = [json.loads(line) for line in open(f"{base}/vector_ready/{name}.jsonl", encoding="utf-8") if line.strip()]
    
    # Extract text and tokenize
    # For legal documents, preserve citations and section numbers
    corpus = [row.get("text", "") for row in rows]
    tokenized_corpus = [text.split() for text in corpus]
    
    # Build BM25 index
    bm25 = BM25Okapi(tokenized_corpus)
    
    # Save BM25 index and ID mapping
    with open(f"{bm25_dir}/{name}.bm25", "wb") as f:
        pickle.dump(bm25, f)
    
    # Save record IDs for result mapping
    ids = json.load(open(f"{base}/vectors/{name}.ids.json"))
    json.dump(ids, open(f"{bm25_dir}/{name}.ids.json", "w"))
    
    print(f"Built BM25 index for {name}: {len(tokenized_corpus)} documents")
```

### 6) Build the hybrid retrieval layer

After index creation, implement a retrieval orchestrator that combines FAISS and BM25:

```python
import faiss
import json
import numpy as np
from rank_bm25 import BM25Okapi
import pickle

class HybridRetriever:
    def __init__(self, faiss_dir, bm25_dir, vectors_dir, ready_dir):
        self.collections = ["statutes", "caselaw", "crossreference"]
        self.faiss_indices = {}
        self.bm25_indices = {}
        self.id_maps = {}
        self.records = {}
        
        # Load all indices
        for name in self.collections:
            # Load FAISS
            self.faiss_indices[name] = faiss.read_index(f"{faiss_dir}/{name}.faiss")
            self.id_maps[name] = json.load(open(f"{faiss_dir}/{name}.ids.json"))
            
            # Load BM25
            with open(f"{bm25_dir}/{name}.bm25", "rb") as f:
                self.bm25_indices[name] = pickle.load(f)
            
            # Load original records
            self.records[name] = [
                json.loads(line) for line in open(f"{ready_dir}/{name}.jsonl", encoding="utf-8") 
                if line.strip()
            ]
    
    def dense_search(self, query_embedding, collection, k=10):
        """FAISS semantic retrieval"""
        index = self.faiss_indices[collection]
        distances, indices = index.search(np.array([query_embedding]).astype('float32'), k)
        
        results = []
        for i, idx in enumerate(indices[0]):
            if idx != -1:  # -1 means invalid index
                results.append({
                    "id": self.id_maps[collection][idx],
                    "score": float(distances[0][i]),
                    "method": "dense",
                    "record": self.records[collection][idx]
                })
        return results
    
    def lexical_search(self, query_text, collection, k=10):
        """BM25 lexical retrieval"""
        bm25 = self.bm25_indices[collection]
        tokenized_query = query_text.split()
        scores = bm25.get_scores(tokenized_query)
        
        # Get top-k indices
        top_indices = np.argsort(scores)[::-1][:k]
        
        results = []
        for idx in top_indices:
            results.append({
                "id": self.id_maps[collection][idx],
                "score": float(scores[idx]),
                "method": "lexical",
                "record": self.records[collection][idx]
            })
        return results
    
    def hybrid_search(self, query_embedding, query_text, collection, k=10, alpha=0.6):
        """Hybrid retrieval with score fusion
        
        alpha: weight for dense retrieval (1-alpha for lexical)
               default 0.6 = 60% dense, 40% lexical
        """
        # Get results from both methods
        dense_results = self.dense_search(query_embedding, collection, k=k)
        lexical_results = self.lexical_search(query_text, collection, k=k)
        
        # Normalize scores to [0, 1]
        def normalize_scores(results):
            if not results:
                return results
            scores = [r["score"] for r in results]
            min_score = min(scores)
            max_score = max(scores)
            for r in results:
                if max_score > min_score:
                    r["score"] = (r["score"] - min_score) / (max_score - min_score)
                else:
                    r["score"] = 0.5
            return results
        
        dense_results = normalize_scores(dense_results)
        lexical_results = normalize_scores(lexical_results)
        
        # Merge results by ID with score fusion
        merged = {}
        for r in dense_results:
            merged[r["id"]] = {
                "record": r["record"],
                "dense_score": r["score"],
                "lexical_score": 0.0
            }
        
        for r in lexical_results:
            if r["id"] in merged:
                merged[r["id"]]["lexical_score"] = r["score"]
            else:
                merged[r["id"]] = {
                    "record": r["record"],
                    "dense_score": 0.0,
                    "lexical_score": r["score"]
                }
        
        # Calculate fused score
        fused_results = []
        for doc_id, data in merged.items():
            fused_score = alpha * data["dense_score"] + (1 - alpha) * data["lexical_score"]
            fused_results.append({
                "id": doc_id,
                "fused_score": fused_score,
                "dense_score": data["dense_score"],
                "lexical_score": data["lexical_score"],
                "record": data["record"]
            })
        
        # Sort by fused score
        fused_results.sort(key=lambda x: x["fused_score"], reverse=True)
        return fused_results[:k]
    
    def filter_by_metadata(self, results, filters):
        """Apply metadata filtering (jurisdiction, date, act, etc.)"""
        filtered = []
        for r in results:
            record = r["record"]
            match = True
            
            if "jurisdiction" in filters and record.get("jurisdiction") != filters["jurisdiction"]:
                match = False
            if "act" in filters and record.get("act_abbrev") != filters["act"]:
                match = False
            if "date_from" in filters and record.get("date") < filters["date_from"]:
                match = False
            if "date_to" in filters and record.get("date") > filters["date_to"]:
                match = False
            
            if match:
                filtered.append(r)
        
        return filtered
```

### 7) Validate the database build

Before moving to app usage, validate with real legal queries:

```python
# Example queries
queries = [
    {
        "text": "What is the punishment under IPC section 302?",
        "collection": "statutes",
        "filters": {"act": "IPC"}
    },
    {
        "text": "Explain the bail conditions in criminal law cases",
        "collection": "caselaw",
        "filters": {}
    },
    {
        "text": "Find relevant provisions on rent control in Tamil Nadu",
        "collection": "statutes",
        "filters": {"jurisdiction": "TN"}
    },
    {
        "text": "What does the Constitution say about equality?",
        "collection": "statutes",
        "filters": {"act": "Constitution"}
    }
]

retriever = HybridRetriever(faiss_dir, bm25_dir, vectors_dir, ready_dir)

for query in queries:
    # Generate embedding for query
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer('BAAI/bge-m3')
    query_embedding = model.encode(query["text"], normalize_embeddings=True)
    
    # Hybrid search
    results = retriever.hybrid_search(
        query_embedding, 
        query["text"], 
        query["collection"],
        k=5,
        alpha=0.6
    )
    
    # Apply metadata filters if any
    if query["filters"]:
        results = retriever.filter_by_metadata(results, query["filters"])
    
    print(f"\nQuery: {query['text']}")
    print(f"Results (top-{len(results)}):")
    for i, result in enumerate(results):
        print(f"  {i+1}. [Score: {result['fused_score']:.3f}] {result['record'].get('section_title', 'N/A')}")
        print(f"     Collection: {result['record'].get('collection')}, Citation: {result['record'].get('citation_key')}")
```

Validation checklist:
- [ ] FAISS indices load correctly for all three collections
- [ ] BM25 indices load correctly for all three collections
- [ ] Dense search returns semantically relevant results
- [ ] Lexical search returns citation and section matches
- [ ] Hybrid search balances both approaches (adjust alpha if needed)
- [ ] Metadata filtering works (jurisdiction, act, date ranges)
- [ ] Top results are legally accurate and relevant
- [ ] No empty or malformed vectors in results
- [ ] Response time is acceptable (should be <100ms per query)

## Important implementation notes

### Do not overwrite the source data

The canonical inputs are the JSONL files under `knowledge_base/vector_ready`. Do not regenerate chunk data unless you are intentionally rebuilding the whole corpus.

### Use metadata from JSONL, not from filenames

The original records contain the real structured metadata. The `.npy` files are only vectors; they are not the authoritative source for content and provenance.

### Keep the collection separation

Maintain separate FAISS and BM25 indices for each collection:
- `statutes` (Constitution & Acts)
- `caselaw` (Court Judgments)
- `crossreference` (Rules & Regulations)

This keeps retrieval, filtering, and ranking much easier and more explainable. Users can also search within specific collections or across all collections.

### Use normalized vectors with FAISS

Because embeddings were L2-normalized during generation, use `IndexFlatIP` (Inner Product) for FAISS, which is mathematically equivalent to cosine similarity for normalized vectors. This is the fastest and most accurate approach.

### Tune hybrid scoring parameters

The `alpha` parameter in `hybrid_search()` controls the balance:
- `alpha=1.0`: only dense retrieval
- `alpha=0.5`: equal weight to dense and lexical
- `alpha=0.0`: only lexical retrieval (BM25)

Start with `alpha=0.6` (60% dense, 40% lexical) for legal search. Adjust based on validation results:
- If too many semantic but legally incorrect results → lower alpha
- If missing citations and exact references → raise alpha

### Recommended BM25 tuning

For legal documents, BM25 parameters typically work well as defaults:
- k1 = 1.5 (saturation parameter, default)
- b = 0.75 (length normalization, default)

For highly cited documents, consider increasing k1 slightly to reward term frequency.

## Suggested AI execution plan

An AI agent or automation script should do the following:

1. Verify vector files and ID alignment
2. Read each JSONL file to create payload metadata
3. Load `.npy` matrices and attach them to each record in order
4. Build FAISS indices with `IndexFlatIP` for each collection
5. Build BM25 indices for lexical retrieval for each collection
6. Implement hybrid retrieval orchestrator with score fusion
7. Apply metadata filtering (jurisdiction, act, date, citation)
8. Validate query results using the legal benchmark queries
9. Tune alpha parameter and BM25 settings based on validation
10. Export retrieval API for integration into the LLM orchestration layer (Step 5 in architecture)

## Minimal success criteria

The vector DB build is considered successful only when all of the following are true:
- all three FAISS indices are created and load correctly
- all three BM25 indices are created and load correctly
- every point has a valid vector and payload
- all IDs align with the original chunk records
- dense retrieval returns semantically similar passages
- lexical retrieval returns exact citation and section matches
- hybrid search effectively combines both methods
- metadata filtering works correctly
- retrieval answers return legal citations or sections correctly
- response time per query is <100ms
- validation queries return legally accurate and relevant results

## Storage structure

Organize indices as follows:

```
knowledge_base/
├── indices/
│   ├── faiss/
│   │   ├── statutes.faiss
│   │   ├── statutes.ids.json
│   │   ├── caselaw.faiss
│   │   ├── caselaw.ids.json
│   │   ├── crossreference.faiss
│   │   └── crossreference.ids.json
│   ├── bm25/
│   │   ├── statutes.bm25
│   │   ├── statutes.ids.json
│   │   ├── caselaw.bm25
│   │   ├── caselaw.ids.json
│   │   ├── crossreference.bm25
│   │   └── crossreference.ids.json
│   └── retriever.py  # HybridRetriever class
├── vector_ready/
│   ├── statutes.jsonl
│   ├── caselaw.jsonl
│   └── crossreference.jsonl
└── vectors/
    ├── statutes.npy
    ├── statutes.ids.json
    ├── caselaw.npy
    ├── caselaw.ids.json
    ├── crossreference.npy
    └── crossreference.ids.json
```

## Recommended next command sequence

From the repo root:

```bash
# Activate environment
.\.venv\Scripts\activate

# Install vector DB and BM25 clients
pip install faiss-cpu rank-bm25

# Build FAISS indices
python scripts/build_faiss_indices.py

# Build BM25 indices
python scripts/build_bm25_indices.py

# Validate retrieval
python scripts/validate_retrieval.py
```

## Final state summary

This repository is already in the right state for the vector database build:
- chunks were created
- metadata was prepared
- dense embeddings were generated
- vectors are aligned with IDs
- the project is ready for index construction and hybrid retrieval setup

The next job is not data preprocessing anymore. The next job is:
1. **FAISS index construction** for fast semantic retrieval
2. **BM25 index construction** for accurate lexical/citation retrieval
3. **Hybrid retrieval orchestration** with score fusion and metadata filtering
4. **Integration into LLM orchestration** (Step 5 in JusticeCompass architecture) for context construction and prompt engineering

This completes the "Offline Indexing Pipeline" (bottom portion of architecture diagram) and enables the "Hybrid Retrieval Engine" (Step 2 in architecture) for online query processing.
