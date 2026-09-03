# Retrieval System and RAG Pipeline

This package provides local hybrid retrieval over the JusticeCompass legal corpus, integrated with a Retrieval Augmented Generation (RAG) pipeline for legal Q&A.

## Quick Start

### Hybrid Retrieval Only

Ask questions directly against the retrieval indices:

```powershell
.\.venv\Scripts\python.exe -m retrieval.cli --collection statutes --top-k 5
```

Available collections: `statutes`, `caselaw`, `crossreference`

### Full RAG Pipeline (LLM-powered answers)

Get comprehensive legal answers with citations:

```powershell
.\.venv\Scripts\python.exe -m retrieval.rag_cli --collection statutes --llm openai --model gpt-4-turbo-preview
```

Or with Anthropic Claude:

```powershell
.\.venv\Scripts\python.exe -m retrieval.rag_cli --collection statutes --llm anthropic --model claude-3-haiku-20240307
```

## Architecture

### Dense Retrieval (FAISS)
- IndexFlatIP with normalized BGE-M3 embeddings (1024-dim)
- Cosine similarity search over 5,261+ legal documents
- ~5ms latency per query

### Lexical Retrieval (BM25)
- Term frequency + inverse document frequency scoring
- Exact reference and citation matching
- Handles legal terminology and section numbers

### Hybrid Ranking
- Configurable score fusion: `fused = alpha * dense + (1-alpha) * lexical`
- Default: alpha=0.6 (60% dense, 40% lexical)
- Normalized scores for fair comparison

### Confidence Scoring
- Multi-factor confidence evaluation:
  - Retrieval score (hybrid ranking)
  - Source type (statute > case law > references)
  - Recency (newer sources weighted higher)
  - Directness (query-result relevance)
  - Specificity (specific sections > general principles)
  - Citation frequency (frequently cited > obscure)
  - Consensus (multiple sources supporting same conclusion)
- Aggregate confidence: High (≥0.80) / Medium (0.50-0.80) / Low (<0.50)

### LLM Integration
- Support for OpenAI (GPT-4, etc.)
- Support for Anthropic Claude (Haiku, Sonnet, Opus)
- System prompt includes legal knowledge base structure
- Context-aware prompt engineering with source citations
- Temperature=0.3 for legal accuracy

## Installation

Install dependencies:

```powershell
pip install -r requirements.txt
```

## Configuration

### LLM API Keys

Set environment variables for your LLM provider:

```powershell
# OpenAI
$env:OPENAI_API_KEY = "sk-..."

# Anthropic
$env:ANTHROPIC_API_KEY = "sk-ant-..."
```

Or pass directly:

```powershell
.\.venv\Scripts\python.exe -m retrieval.rag_cli --api-key "sk-..."
```

## Usage

### Retrieval-Only CLI

```bash
.\.venv\Scripts\python.exe -m retrieval.cli \
  --collection statutes \
  --top-k 5 \
  --alpha 0.6
```

Options:
- `--collection`: statutes, caselaw, crossreference
- `--top-k`: Number of results to return
- `--alpha`: Dense weight (0-1)

### RAG Pipeline CLI

```bash
.\.venv\Scripts\python.exe -m retrieval.rag_cli \
  --collection statutes \
  --llm openai \
  --model gpt-4-turbo-preview \
  --top-k 5 \
  --alpha 0.6 \
  --min-confidence 0.5 \
  --output text
```

Options:
- `--collection`: statutes, caselaw, crossreference, all
- `--llm`: openai, anthropic
- `--model`: LLM model name
- `--top-k`: Retrieval results per collection
- `--alpha`: Dense vs lexical weight
- `--min-confidence`: Confidence threshold (0-1)
- `--output`: text or json
- `--verbose`: Detailed logging

### Python API

```python
from retrieval.rag_pipeline import LegalRAGPipeline

# Initialize pipeline
rag = LegalRAGPipeline(
    llm_provider="openai",
    llm_model="gpt-4-turbo-preview",
    min_confidence=0.50,
)

# Query
response = rag.query(
    question="What is the punishment for theft under IPC?",
    collection="statutes",
    top_k=5,
    alpha=0.6,
)

# Access response
print(response.answer)
print(response.confidence_label)
print(response.source_citations)

# Format for display
print(rag.format_response(response))

# Export as JSON
import json
data = json.loads(rag.to_json(response))
```

## System Prompt

The RAG pipeline uses a comprehensive system prompt defined in `system_prompt.md`. It covers:

- Role and responsibility of the legal assistant
- Core principles (accuracy, transparency, limitations)
- Knowledge base structure
- Response guidelines
- Confidence scoring methodology
- Special considerations (criminal law, constitutional, jurisdiction-specific)
- Tone and style requirements
- Prohibited actions

## Confidence Scoring

The confidence scorer evaluates each retrieval result on multiple factors:

```python
from retrieval.confidence_scorer import ConfidenceScorer

scorer = ConfidenceScorer()

# Score individual results
metrics = scorer.score_result(result, query_text)
print(metrics.confidence_label)  # "High", "Medium", "Low"
print(metrics.overall_confidence)  # 0.0 - 1.0

# Filter by confidence
filtered_results, metrics = scorer.filter_by_confidence(
    all_results, 
    query_text, 
    min_confidence=0.50
)

# Aggregate confidence across multiple results
aggregate = scorer.get_aggregate_confidence(metrics)
```

## Storage

```
knowledge_base/vector_db/
  records/       canonical JSONL payloads
  embeddings/    .npy vectors and aligned IDs
  indices/
    faiss/       .index files and aligned ID maps
    bm25/        serialized lexical indices and ID maps
retrieval/
  hybrid_retriever.py     hybrid search engine
  confidence_scorer.py    confidence evaluation
  rag_pipeline.py         RAG orchestration
  system_prompt.md        LLM system prompt
  cli.py                  retrieval-only CLI
  rag_cli.py              RAG pipeline CLI
```

## Rebuild Indices

After updating records or embeddings:

```powershell
.\.venv\Scripts\python.exe scripts\build_faiss_indices.py
.\.venv\Scripts\python.exe scripts\build_bm25_indices.py
```

## Testing

Test the retrieval system:

```powershell
.\.venv\Scripts\python.exe scripts\validate_retrieval.py
```

Test the RAG pipeline:

```powershell
# You should see the query, answer, confidence, and citations
.\.venv\Scripts\python.exe -m retrieval.rag_cli --verbose
```

## Example Queries

### Statutes
"What is the punishment for theft under Indian law?"
"What sections of IPC deal with criminal intimidation?"
"What are the grounds for bail under criminal procedure?"

### Case Law
"What are the key factors courts consider for bail?"
"What is the difference between anticipatory bail and regular bail?"

### Cross-Reference
"How does IPC section 302 map to BNS 2023?"
"What replaced the old Criminal Procedure Code?"

## Performance

- **Retrieval**: ~50-200ms per query (depends on collection size)
- **Embedding**: ~100ms per query
- **LLM**: 1-10s depending on model and response length
- **Total**: ~2-15s end-to-end

## Troubleshooting

### API Key Issues

```
Error: OPENAI_API_KEY environment variable not set
```

Set your API key:

```powershell
$env:OPENAI_API_KEY = "sk-..."
```

### Import Errors

```
Error: openai package not installed
```

Install LLM dependencies:

```
pip install openai anthropic
```

### Index Loading Errors

Ensure indices are built:

```powershell
.\.venv\Scripts\python.exe scripts\build_faiss_indices.py
.\.venv\Scripts\python.exe scripts\build_bm25_indices.py
```

## Limitations

- **No Live Web Search**: Uses only indexed legal documents
- **No Case Prediction**: Does not predict case outcomes
- **India-Focused**: Primarily Indian legal statutes and case law
- **Not Legal Advice**: Provides information, not personalized legal counsel
- **Knowledge Cutoff**: Based on indexed data (may not include very recent judgments)

## Future Enhancements

- [ ] Local LLM support (Llama 2, Mistral, etc.)
- [ ] Multi-turn conversation with context
- [ ] Document upload for analysis
- [ ] Citation verification and source validation
- [ ] Comparative analysis (IPC vs BNS, etc.)
- [ ] Batch query processing
- [ ] API server deployment
- [ ] Web UI for queries
