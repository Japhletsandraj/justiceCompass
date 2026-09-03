# JusticeCompass

## Current status

JusticeCompass has completed its core infrastructure: hybrid retrieval (FAISS + BM25) and a full Retrieval Augmented Generation (RAG) pipeline for legal Q&A. The system provides accurate, cited, and confidence-scored answers to legal questions using Indian statutes, constitutional law, and case law.

### Milestone reached

- ✅ Dense vectors generated and aligned to legal records (5,261+ documents, 1024-dim)
- ✅ FAISS index creation validated for all collections
- ✅ BM25 lexical indexing validated for all collections
- ✅ Hybrid retrieval orchestrator implemented (dense + lexical ranking)
- ✅ Multi-factor confidence scoring framework
- ✅ Comprehensive system prompt for legal Q&A
- ✅ LLM integration (OpenAI, Anthropic)
- ✅ Interactive RAG CLI and Python API
- ✅ Full documentation and examples

### Quick Start

#### RAG Pipeline (Recommended)

Get comprehensive legal answers with AI-powered reasoning:

```powershell
.\.venv\Scripts\python.exe ai\run_rag_test.py
```

#### Retrieval Only

Direct legal document search without LLM:

```powershell
.\.venv\Scripts\python.exe -m ai.retrieval.cli --collection statutes
```

### Repository layout

- `knowledge_base/` — corpus, metadata, vector-ready records, and generated indexes
- `scripts/` — extraction, embedding, and index-building scripts
- `docs/` — project notes and handoff documentation
- `data/` — raw and processed legal source files
- `ai/` — retrieval, confidence scoring, RAG pipeline, prediction, and terminal runner
- `backend/` — FastAPI service and HTTP endpoints
  - `hybrid_retriever.py` — dense + lexical search
  - `confidence_scorer.py` — 7-factor confidence evaluation
  - `rag_pipeline.py` — LLM integration and orchestration
  - `system_prompt.md` — legal Q&A guidelines
  - `cli.py` — retrieval-only CLI
  - `rag_cli.py` — RAG pipeline CLI

## Architecture

```
User Query
    ↓
Query Embedding (BGE-M3)
    ↓
Hybrid Retrieval (FAISS + BM25)
    ↓
Multi-Factor Confidence Scoring
    ↓
Confidence Filtering
    ↓
Context Formatting
    ↓
LLM (with System Prompt)
    ↓
Legal Answer + Citations + Confidence
```

## Features

### Retrieval
- **Hybrid Search**: Combines semantic (FAISS) and lexical (BM25) retrieval
- **Smart Ranking**: Configurable alpha parameter (60% semantic, 40% lexical by default)
- **Fast**: ~50-200ms per query

### Confidence Scoring
- **7-Factor Evaluation**:
  1. Retrieval score (hybrid ranking quality)
  2. Source type (statute > case law > reference)
  3. Recency (newer sources weighted higher)
  4. Directness (query-result relevance)
  5. Specificity (specific sections > general concepts)
  6. Citation frequency (frequently cited sources)
  7. Consensus (multiple sources agreeing)
- **Confidence Labels**: High / Medium / Low
- **Threshold Filtering**: Exclude low-confidence results

### Legal Q&A
- **LLM Integration**: OpenAI (GPT-4, etc.) and Anthropic (Claude) support
- **System Prompt**: 200+ lines of comprehensive legal guidelines
- **Structured Responses**: Answer, citations, confidence, reasoning
- **Citation Tracking**: Full source attribution

### Knowledge Base
- **Statutes**: Constitutional law, Criminal (IPC/BNS/CrPC/BNSS), Consumer Protection, Family Law, Tenancy & Property
- **Case Law**: 1,200 Indian bail-related court decisions
- **Cross-References**: IPC-to-BNS mapping with equivalence relations

## Installation

```powershell
# Clone and navigate
cd jc

# Create virtual environment (if not exists)
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Set API keys
$env:OPENAI_API_KEY = "sk-..."
# or
$env:ANTHROPIC_API_KEY = "sk-ant-..."
```

## Usage Examples

### RAG Pipeline - OpenAI

```powershell
.\.venv\Scripts\python.exe -m retrieval.rag_cli \
  --collection statutes \
  --llm openai \
  --model gpt-4-turbo-preview \
  --min-confidence 0.5
```

### RAG Pipeline - Anthropic Claude

```powershell
.\.venv\Scripts\python.exe -m retrieval.rag_cli \
  --collection statutes \
  --llm anthropic \
  --model claude-3-haiku-20240307
```

### Python API

```python
from retrieval.rag_pipeline import LegalRAGPipeline

# Initialize
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
)

# Display
print(f"Answer: {response.answer}")
print(f"Confidence: {response.confidence_label}")
print(f"Sources: {response.source_citations}")
```

### Direct Retrieval (No LLM)

```powershell
# Retrieval only
.\.venv\Scripts\python.exe -m retrieval.cli \
  --collection statutes \
  --top-k 5 \
  --alpha 0.6
```

## Example Queries

### Criminal Law
- "What is the punishment for theft under Indian law?"
- "What sections of IPC deal with criminal intimidation?"
- "What are the grounds for bail in serious crimes?"

### Constitutional Law
- "What are fundamental rights under the Constitution?"
- "What does Article 21 protect?"

### Family Law
- "What are the grounds for divorce under Hindu Marriage Act?"
- "What is the legal age for marriage in India?"

### Tenancy & Property
- "What are tenant rights under rent control laws?"
- "How are disputes between landlord and tenant resolved?"

## Verification

All components have been verified:

- ✅ Vector database: 5,261 documents with 1024-dim embeddings
- ✅ FAISS indices: All three collections indexed
- ✅ BM25 indices: All three collections indexed
- ✅ Hybrid retrieval: Dense + lexical ranking validated
- ✅ Confidence scoring: 7-factor evaluation working
- ✅ RAG pipeline: LLM integration tested
- ✅ System prompt: Comprehensive legal guidelines
- ✅ CLI interfaces: Both retrieval and RAG pipelines working

## Performance

- **Embedding**: ~100ms per query
- **Retrieval**: ~50-200ms per query
- **LLM**: 1-10s depending on model
- **Total**: ~2-15s end-to-end

## Project Notes

- See [docs/progress.md](docs/progress.md) for complete build log
- See [docs/vector-db-build-handoff.md](docs/vector-db-build-handoff.md) for retrieval architecture
- See [ai/retrieval/README.md](ai/retrieval/README.md) for detailed retrieval documentation
- See [ai/retrieval/system_prompt.md](ai/retrieval/system_prompt.md) for legal Q&A guidelines

## What Comes Next

The pipeline is production-ready. Future enhancements:

- [ ] REST API deployment (FastAPI/Flask)
- [ ] Web UI for interactive queries
- [ ] Local LLM support (Llama 2, Mistral)
- [ ] Multi-turn conversation support
- [ ] Document upload for analysis
- [ ] Citation verification
- [ ] Batch query processing
- [ ] Performance monitoring
- [ ] Enhanced retrieval (re-ranking, semantic clustering)

## Status Summary

The JusticeCompass RAG pipeline is **complete and ready for use**. It provides:

1. **Accurate Retrieval**: Hybrid search over 5,261 legal documents
2. **Confidence-Based Filtering**: Multi-factor evaluation of result quality
3. **LLM-Powered Answers**: AI-generated responses with citations
4. **Legal Compliance**: System prompt ensures accurate, ethical responses
5. **Flexible Deployment**: CLI, Python API, and easy extensibility