# Implementation Details and Architectural Decisions

**Document**: Technical Architecture Overview  
**Date**: 2026-08-31  
**Audience**: Developers, System Architects, Future Maintainers

## Table of Contents

1. [System Architecture](#system-architecture)
2. [Component Design](#component-design)
3. [Confidence Scoring Design](#confidence-scoring-design)
4. [System Prompt Strategy](#system-prompt-strategy)
5. [LLM Integration](#llm-integration)
6. [Data Flow](#data-flow)
7. [Design Decisions](#design-decisions)
8. [Future Extensibility](#future-extensibility)

## System Architecture

### High-Level Overview

The RAG pipeline consists of five main layers:

```
┌────────────────────────────────────────────────┐
│         User Interface Layer                    │
│  (CLI, REST API, Python API, Web UI)            │
└────────────────┬─────────────────────────────┘
                 │
┌────────────────▼─────────────────────────────┐
│      Orchestration Layer                      │
│  (LegalRAGPipeline - query coordination)      │
└────────────────┬─────────────────────────────┘
                 │
    ┌────────────┴─────────────┬───────────────┐
    │                          │               │
┌───▼──────────┐  ┌───────────▼──┐  ┌────────▼──┐
│  Retrieval   │  │  Confidence  │  │    LLM    │
│   Layer      │  │   Scoring    │  │ Integration│
└───┬──────────┘  └───────────┬──┘  └────────┬──┘
    │                        │              │
    ├─────────────┬──────────┴──────────────┤
    │             │                        │
┌───▼──┐  ┌──────▼────┐  ┌─────────┐  ┌──▼──┐
│FAISS │  │   BM25    │  │Metadata │  │ LLM │
│Index │  │ Index     │  │Extractor│  │APIs │
└──────┘  └───────────┘  └─────────┘  └─────┘
    │
    └──────────────────────────────────┐
                                      │
                   ┌──────────────────▼──┐
                   │  Knowledge Base     │
                   │  (5,261 documents)  │
                   └─────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Key Methods |
|-----------|-----------------|------------|
| **HybridRetriever** | Dense + lexical search | `hybrid_search()`, `dense_search()`, `lexical_search()` |
| **ConfidenceScorer** | Multi-factor evaluation | `score_result()`, `filter_by_confidence()`, `get_aggregate_confidence()` |
| **LegalRAGPipeline** | End-to-end orchestration | `query()`, `format_response()`, `to_json()` |
| **RAG CLI** | Interactive interface | Argument parsing, input/output handling |
| **LLM Providers** | AI reasoning | OpenAI, Anthropic APIs |

## Component Design

### 1. HybridRetriever (Existing)

**File**: `retrieval/hybrid_retriever.py`  
**Status**: Not modified (working correctly)

**Architecture**:
- Loads FAISS indices (dense vectors)
- Loads BM25 indices (lexical terms)
- Implements alpha-weighted fusion

**Key Features**:
- Configurable alpha (0.0-1.0) for dense/lexical balance
- Per-collection indices (statutes, caselaw, crossreference)
- Metadata preservation
- Fast (~50-200ms per query)

### 2. ConfidenceScorer (NEW)

**File**: `retrieval/confidence_scorer.py`  
**Lines of Code**: ~500

**Key Classes**:

```python
@dataclass
class ConfidenceMetrics:
    """Output of confidence scoring"""
    document_id: str
    retrieval_score: float
    source_type_score: float
    recency_score: float
    directness_score: float
    specificity_score: float
    citation_frequency_score: float
    consensus_score: float
    overall_confidence: float
    confidence_label: str  # High/Medium/Low
    reasoning: str
```

**Scoring Methods**:

1. **_calculate_source_type_score()**
   - Statute: 0.95 (highest authority)
   - Constitutional: 0.95
   - Case Law: 0.85 (established precedent)
   - Cross-reference: 0.70 (supporting material)

2. **_calculate_recency_score()**
   - Extracts year from date field
   - Newest (current year): 0.95
   - Gradually decreases with age
   - 50+ years old: 0.30

3. **_calculate_directness_score()**
   - Based on retrieval score (base value)
   - Boosted by exact term matching
   - Enhanced for specific sections vs general concepts
   - Range: 0.1-1.0

4. **_calculate_specificity_score()**
   - Checks presence of: section_number, act_abbrev, jurisdiction
   - Checks text length (specific > general)
   - Specific provision: 1.0
   - General concept: 0.5

5. **_calculate_citation_frequency_score()**
   - Counts citation_keys in metadata
   - Landmark cases: 1.0
   - Frequently cited: 0.8-0.9
   - Rarely cited: 0.5-0.6

6. **_calculate_consensus_score()**
   - Groups results by source (act, case)
   - Multiple sources agreeing: 0.9-1.0
   - Single source: 0.5-0.6
   - Conflicting information: 0.3-0.4

7. **Overall Score Calculation**:
   ```python
   overall = (
       0.30 * retrieval_score +
       0.15 * source_type_score +
       0.10 * recency_score +
       0.20 * directness_score +
       0.10 * specificity_score +
       0.05 * citation_frequency_score +
       0.10 * consensus_score
   )
   ```

**Confidence Labels**:
- **High**: overall ≥ 0.80 (very reliable)
- **Medium**: 0.50 ≤ overall < 0.80 (reasonable confidence)
- **Low**: overall < 0.50 (uncertain, requires verification)

### 3. LegalRAGPipeline (NEW)

**File**: `retrieval/rag_pipeline.py`  
**Lines of Code**: ~600

**Key Classes**:

```python
@dataclass
class ContextItem:
    """Context fragment for LLM"""
    source: str
    text: str
    confidence: float
    source_type: str
    metadata: dict

@dataclass
class RAGResponse:
    """Final answer with metadata"""
    answer: str
    confidence_score: float
    confidence_label: str
    source_citations: List[str]
    context_items: List[ContextItem]
    retrieval_metrics: dict
    query: str
    model_used: str
```

**Main Methods**:

1. **__init__()**: Initialize components
   - Loads HybridRetriever
   - Initializes SentenceTransformer (BGE-M3)
   - Creates ConfidenceScorer
   - Sets up LLM client (OpenAI/Anthropic)

2. **query()**: Main entry point
   ```python
   def query(self, question, collection, top_k=5, alpha=0.6):
       # 1. Embed query
       embedding = self._embed_query(question)
       
       # 2. Retrieve results
       results = retriever.hybrid_search(embedding, question, collection, top_k, alpha)
       
       # 3. Score confidence
       scored_results, metrics = scorer.filter_by_confidence(results, question)
       
       # 4. Format context
       context = self._format_context(scored_results)
       
       # 5. Build prompt
       prompt = self._build_prompt(question, context)
       
       # 6. Call LLM
       answer = self._call_llm(prompt)
       
       # 7. Extract sources
       sources = self._extract_sources_from_answer(answer)
       
       # 8. Return structured response
       return RAGResponse(...)
   ```

3. **_format_context()**: Context preparation
   - Extracts source information from metadata
   - Formats as numbered references
   - Preserves citation information
   - Includes confidence levels

4. **_build_prompt()**: Dynamic prompt engineering
   ```python
   def _build_prompt(self, question, context):
       return f"""{SYSTEM_PROMPT_TEMPLATE}

## Retrieved Legal Context:
{context}

## User Question:
{question}

## Your Response:
[Provide answer with citations]
"""
   ```

5. **_call_llm()**: LLM API integration
   - Supports OpenAI API
   - Supports Anthropic API
   - Configurable model selection
   - Error handling and retries

6. **to_json()**: Structured export
   - Returns dict with all response data
   - Suitable for APIs and logging
   - Includes metadata and metrics

## Confidence Scoring Design

### Design Philosophy

**Problem**: How to evaluate quality of retrieved results?

**Solution**: Multi-factor evaluation combining:
- Retrieval quality (how well result matched query)
- Source authority (who says this - statute vs tweet)
- Recency (when was it written/updated)
- Directness (how specific vs general)
- Specificity (does it mention exact sections)
- Citation frequency (how often is it cited)
- Consensus (do multiple sources agree)

### Why Seven Factors?

| Factor | Why Important | Example |
|--------|---------------|---------|
| Retrieval | Relevance | "Theft" query should match theft section |
| Source Type | Authority | Constitution > Act > Case > Reference |
| Recency | Applicability | 2023 BNS > 1860 IPC (when applicable) |
| Directness | Specificity | IPC §379 > "Criminal Code" |
| Specificity | Exactness | Section number present > general discussion |
| Citation Freq | Importance | Frequently cited = more reliable |
| Consensus | Confirmation | Multiple sources agreeing = more certain |

### Weight Justification

```
Retrieval (30%)      - Most important: relevance is primary
Directness (20%)     - Second most: specific match matters
Source Type (15%)    - Third: who says it matters in law
Recency (10%)        - Important: law changes
Specificity (10%)    - Important: sections > general principles
Consensus (10%)      - Important: agreement across sources
Citation Freq (5%)   - Least important: may vary by domain
------
Total: 100%
```

### Threshold Strategy

- **High (≥0.80)**: Use with confidence, minimal verification needed
- **Medium (0.50-0.80)**: Use with caution, single source, may need verification
- **Low (<0.50)**: Do not use in production, too uncertain

**Filtering**: Results below `min_confidence` threshold are excluded from LLM context

## System Prompt Strategy

### File: `retrieval/system_prompt.md`

**Size**: 200+ lines  
**Purpose**: Inject legal domain expertise into every LLM call

**Sections**:

1. **Role Definition**
   - "You are a legal assistant"
   - "Focused on Indian law"
   - "Accurate and transparent"

2. **Core Principles**
   - Accuracy over speed
   - Transparency about limitations
   - Jurisdiction awareness
   - Ethical constraints

3. **Knowledge Base Structure**
   - What's available (statutes, cases, cross-refs)
   - What's not available (foreign law, speculation)
   - Collection descriptions

4. **Response Format**
   - 6-step structure: clarification, law, cases, analysis, confidence, next steps
   - Citation format specifications
   - Confidence scoring guidance

5. **Special Considerations**
   - Criminal law specifics
   - Constitutional law nuances
   - Amendment awareness
   - Jurisdiction variations

6. **Prohibited Actions**
   - No legal advice
   - No predictions
   - No false citations
   - No speculation

### Why System Prompt is Critical

**Without system prompt**:
- LLM may generate plausible-sounding false information
- May confidently cite non-existent sections
- May give legal advice (out of scope)
- May ignore jurisdiction differences

**With system prompt**:
- LLM maintains focus on facts
- Acknowledges limitations
- Avoids speculation
- Respects constraints

## LLM Integration

### Supported Providers

#### OpenAI
```python
from openai import OpenAI

client = OpenAI(api_key=api_key)
response = client.chat.completions.create(
    model="gpt-4-turbo-preview",
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ],
    temperature=0.3,  # Low temp for legal accuracy
    top_p=0.7,
)
```

**Supported Models**:
- gpt-4
- gpt-4-turbo-preview
- gpt-3.5-turbo

**Characteristics**:
- Highly capable, latest information
- Expensive ($0.01-0.03 per 1K tokens)
- Fast (~2-5s response time)
- Good context handling

#### Anthropic
```python
from anthropic import Anthropic

client = Anthropic(api_key=api_key)
response = client.messages.create(
    model="claude-3-haiku-20240307",
    system=system_prompt,
    messages=[
        {"role": "user", "content": user_message}
    ],
    temperature=0.3,
    max_tokens=2000,
)
```

**Supported Models**:
- claude-3-opus (best, expensive)
- claude-3-sonnet (balanced)
- claude-3-haiku (fast, cheap)

**Characteristics**:
- Very accurate, good reasoning
- Cheaper than GPT-4
- Medium speed (~3-8s)
- Excellent instruction following

### Configuration Strategy

```python
SYSTEM_PROMPT_TEMPLATE = """
[200+ lines of legal domain expertise]
"""

# Injected into every call
messages = [
    {"role": "system", "content": SYSTEM_PROMPT_TEMPLATE},
    {"role": "user", "content": f"{context}\n\n{question}"},
]

# Low temperature for consistency
temperature = 0.3

# Reasonable token limit
max_tokens = 2000
```

## Data Flow

### Complete Request-Response Cycle

```
1. USER INPUT
   "What is punishment for theft?"
   
2. QUERY EMBEDDING
   Input: Question text
   Model: BAAI/bge-m3 (1024-dim)
   Output: Normalized vector
   
3. HYBRID RETRIEVAL
   Input: Embedding, question text
   Process:
     - Dense search (FAISS) → scores
     - Lexical search (BM25) → scores
     - Fusion (alpha-weighted) → ranked results
   Output: Top-K results with scores
   
4. CONFIDENCE SCORING
   Input: Retrieved results, question
   Process:
     - Calculate 7 factors for each result
     - Compute weighted overall score
     - Generate confidence label & reasoning
   Output: Scored results with metrics
   
5. FILTERING
   Input: Scored results, min_confidence
   Process: Keep only results above threshold
   Output: High-confidence results
   
6. CONTEXT FORMATTING
   Input: Filtered results
   Process:
     - Extract metadata
     - Format as citations
     - Compile context block
   Output: Formatted context with source numbers
   
7. PROMPT ENGINEERING
   Input: System prompt, context, question
   Process: Combine into structured prompt
   Output: Complete prompt for LLM
   
8. LLM CALL
   Input: Prompt to LLM API
   Provider: OpenAI or Anthropic
   Temperature: 0.3 (low variance)
   Output: Natural language response
   
9. SOURCE EXTRACTION
   Input: LLM response
   Process: Parse citations (Act, Section, Year)
   Output: Extracted source citations
   
10. RESPONSE PACKAGING
    Input: Answer, confidence, sources, metrics
    Process: Format as RAGResponse object
    Output: Structured response to user
    
11. USER OUTPUT
    Display: Answer with confidence and sources
```

### Example Query Trace

**Query**: "What is punishment for theft?"

```
Stage 1 - Embedding
  Input: "What is punishment for theft?"
  Embedding: [0.123, -0.456, 0.789, ..., 0.012] (1024 dims)
  
Stage 2 - Retrieval
  Dense: IPC §379 (score: 0.87), IPC §392 (score: 0.73), CrPC §50 (score: 0.45)
  Lexical: IPC §379 (score: 0.91), IPC §392 (score: 0.68), CrPC §50 (score: 0.42)
  Hybrid (α=0.6): IPC §379 (0.89), IPC §392 (0.71), CrPC §50 (0.44)
  
Stage 3 - Confidence Scoring (IPC §379)
  Retrieval: 0.89 (top match)
  Source Type: 0.95 (statute)
  Recency: 0.30 (1860, very old)
  Directness: 0.92 (exact term match)
  Specificity: 1.0 (has section number)
  Citation Freq: 0.92 (frequently cited)
  Consensus: 0.80 (same result from dense & lexical)
  Overall: 0.30×0.89 + 0.15×0.95 + 0.10×0.30 + 0.20×0.92 + 0.10×1.0 + 0.05×0.92 + 0.10×0.80
         = 0.267 + 0.143 + 0.030 + 0.184 + 0.100 + 0.046 + 0.080
         = 0.850 (High Confidence)
  
Stage 4 - Context Formatting
  [1] IPC 1860, Section 379: "Whoever commits theft shall be punished with 
      imprisonment of either description for a term which may extend to three years, 
      or with fine which may extend to two hundred rupees, or with both."
      (Confidence: High - 0.850)
  
  [2] IPC 1860, Section 392: "Whoever commits robbery shall be punished with 
      imprisonment of either description for a term which may extend to ten years, 
      and shall also be liable to fine."
      (Confidence: Medium - 0.710)

Stage 5 - Prompt Engineering
  [System Prompt: 200+ lines of legal guidance]
  
  ## Retrieved Legal Context:
  [1] IPC 1860, Section 379...
  [2] IPC 1860, Section 392...
  
  ## User Question:
  What is punishment for theft?
  
Stage 6 - LLM Response
  "According to IPC Section 379, theft is punished with imprisonment 
   of either description for a term up to 3 years, or fine up to 
   Rs. 200, or both. The specific punishment depends on the nature 
   and value of stolen property."
   
Stage 7 - Source Extraction
  Sources: ["IPC 1860 Section 379", "IPC 1860 Section 392"]
  
Stage 8 - Final Response
  Answer: "According to IPC Section 379, theft is punished with..."
  Confidence: High (0.850)
  Sources: IPC 1860 §379, IPC 1860 §392
  Context items: [2 items with full text]
```

## Design Decisions

### Decision 1: Seven Confidence Factors vs Single Score

**Rejected**: Using only retrieval score
**Chosen**: Seven independent factors

**Rationale**:
- Single score ignores source authority
- Doesn't account for law changes (recency)
- Misses consensus validation
- Can't provide reasoning

**Trade-off**: More complexity, but much better quality signal

---

### Decision 2: Alpha-Weighted Hybrid Fusion vs Reranking

**Rejected**: Use dense OR lexical (not both)
**Rejected**: Train learned reranker
**Chosen**: Configurable alpha-weighted fusion

**Rationale**:
- Simple, interpretable
- No training data required
- Flexible for different query types
- Fast execution

**Trade-off**: May not be optimal for all queries, but good general solution

---

### Decision 3: System Prompt Injection vs Few-Shot Examples

**Rejected**: Few-shot examples (limited by token budget)
**Chosen**: Comprehensive system prompt

**Rationale**:
- More efficient use of context
- Can encode more guidance (200+ lines)
- Consistent across all queries
- Can be updated independently

**Trade-off**: Requires careful prompt engineering

---

### Decision 4: Inline Filtering vs Post-Generation Filtering

**Rejected**: Let LLM receive all results, filter in generation
**Chosen**: Filter before LLM (by confidence)

**Rationale**:
- Reduces noise in LLM context
- Lower token usage
- Faster execution
- More predictable quality

**Trade-off**: May miss some relevant results

---

### Decision 5: Multiple LLM Providers vs Single Provider

**Rejected**: Lock into OpenAI only
**Chosen**: Abstraction layer (OpenAI, Anthropic, extensible)

**Rationale**:
- Price flexibility
- Reduce vendor lock-in
- Easy experimentation
- Fallback availability

**Trade-off**: More code complexity

---

### Decision 6: Confidence Labels vs Raw Scores

**Rejected**: Only show numeric scores
**Chosen**: Labels (High/Medium/Low) + numeric scores

**Rationale**:
- More interpretable for users
- Aligns with legal reasoning
- Easier to set thresholds
- Can explain easily

**Trade-off**: Lose fine-grained precision

## Future Extensibility

### Adding New Confidence Factors

```python
# In confidence_scorer.py, add new method:
def _calculate_domain_relevance_score(self, record, query):
    """Factor 8: Domain-specific relevance"""
    if "criminal" in query.lower() and record.get("domain") == "criminal":
        return 1.0
    return 0.5

# Update weights:
weights = {
    "retrieval": 0.25,  # reduced from 0.30
    "source_type": 0.15,
    "recency": 0.10,
    "directness": 0.20,
    "specificity": 0.10,
    "citation_frequency": 0.05,
    "consensus": 0.10,
    "domain_relevance": 0.05,  # NEW
}
```

### Adding New LLM Providers

```python
# In rag_pipeline.py, add:
def _init_llm(self):
    if self.llm_provider == "ollama":
        return OllamaClient(model=self.llm_model)
    elif self.llm_provider == "huggingface":
        return HuggingFaceClient(model=self.llm_model)
    # ... existing providers
```

### Adding Collection-Specific Configurations

```python
# Create collection configs:
COLLECTION_CONFIGS = {
    "statutes": {
        "alpha": 0.6,
        "min_confidence": 0.50,
        "top_k": 5,
    },
    "caselaw": {
        "alpha": 0.4,  # More lexical for case names
        "min_confidence": 0.40,
        "top_k": 3,
    },
}

# Use in query:
config = COLLECTION_CONFIGS.get(collection, {})
response = rag.query(question, collection, **config)
```

### Adding Citation Verification

```python
# New component: CitationVerifier
class CitationVerifier:
    def verify(self, citation, knowledge_base):
        """Check if citation actually exists"""
        # Parse citation
        # Check knowledge base
        # Return verification result
        
# Use in pipeline:
verified_sources = [
    citation for citation in response.source_citations
    if verifier.verify(citation, kb)
]
```

---

## Performance Considerations

### Caching Strategy

```python
# Cache embeddings
@lru_cache(maxsize=1000)
def embed_query(question):
    return model.encode(question)

# Cache retrieval results
query_cache = {}
cache_key = hash((question, collection, top_k, alpha))
```

### Batch Processing

```python
# Process multiple queries at once
def batch_query(questions):
    embeddings = [embed_query(q) for q in questions]
    results = retriever.batch_search(embeddings)
    scored = scorer.score_batch(results)
    return [RAGResponse(...) for _ in scored]
```

### Async Operations

```python
# Non-blocking LLM calls
async def query_async(self, question):
    embedding = await self._embed_query(question)
    results = await retriever.search_async(embedding)
    return await self._call_llm_async(prompt)
```

## Monitoring and Observability

### Metrics to Track

1. **Retrieval Metrics**
   - Average retrieval score
   - Distribution of confidence scores
   - Collection usage breakdown

2. **Pipeline Metrics**
   - End-to-end latency
   - Confidence label distribution
   - Source citation frequency

3. **LLM Metrics**
   - Token usage
   - API latency
   - Error rates

4. **Quality Metrics**
   - User satisfaction scores
   - Citation accuracy
   - False positive rate

### Logging

```python
# Structured logging
logger.info("query", {
    "question": question,
    "collection": collection,
    "retrieval_count": len(results),
    "confidence_label": response.confidence_label,
    "latency_ms": elapsed,
    "model_used": model,
})
```

## Testing Strategy

### Unit Tests

```python
# Test confidence scorer
def test_confidence_recency_scoring():
    new_doc = {"published": "2024"}
    old_doc = {"published": "1860"}
    assert scorer.recency_score(new_doc) > scorer.recency_score(old_doc)

# Test retrieval
def test_hybrid_retrieval():
    query = "theft punishment"
    results = retriever.hybrid_search(embedding, query, "statutes")
    assert len(results) > 0
    assert results[0]["score"] >= results[1]["score"]
```

### Integration Tests

```python
# Test full pipeline
def test_end_to_end_rag():
    response = rag.query("What is theft?", collection="statutes")
    assert response.answer
    assert response.confidence_score >= 0.0
    assert len(response.source_citations) > 0
```

### Regression Tests

```python
# Define expected results for known queries
REGRESSION_TESTS = {
    "punishment for theft": {
        "expected_sources": ["IPC 379", "IPC 392"],
        "min_confidence": 0.60,
    },
}
```

---

**Document End**

This architecture is designed to be:
- **Maintainable**: Clear separation of concerns
- **Extensible**: Easy to add factors, providers, collections
- **Observable**: Comprehensive logging and metrics
- **Performant**: Caching and batch processing support
- **Reliable**: Multi-level testing and verification
