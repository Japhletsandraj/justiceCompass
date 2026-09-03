# Quick Start Guide - JusticeCompass RAG Pipeline

## 30-Second Setup

```powershell
# 1. Activate environment
cd c:\Users\Noor\OneDrive\Desktop\jc
.\.venv\Scripts\Activate.ps1

# 2. Set API key (choose one)
$env:OPENAI_API_KEY = "sk-..."
# OR
$env:ANTHROPIC_API_KEY = "sk-ant-..."

# 3. Run RAG pipeline
.\.venv\Scripts\python.exe -m retrieval.rag_cli --collection statutes
```

## Common Commands

### Ask Legal Questions (with LLM)

```powershell
# OpenAI GPT-4 (recommended)
.\.venv\Scripts\python.exe -m retrieval.rag_cli --collection statutes --llm openai

# Anthropic Claude (faster/cheaper)
.\.venv\Scripts\python.exe -m retrieval.rag_cli --collection statutes --llm anthropic --model claude-3-haiku-20240307

# Custom model selection
.\.venv\Scripts\python.exe -m retrieval.rag_cli \
  --collection statutes \
  --llm openai \
  --model gpt-4-turbo-preview \
  --top-k 5 \
  --min-confidence 0.50 \
  --verbose
```

### Search Legal Documents (no LLM)

```powershell
# Fast retrieval without LLM
.\.venv\Scripts\python.exe -m retrieval.cli --collection statutes
```

### Different Collections

```powershell
# Statutes only (criminal, constitutional, family law, etc.)
.\.venv\Scripts\python.exe -m retrieval.rag_cli --collection statutes

# Court decisions on bail
.\.venv\Scripts\python.exe -m retrieval.rag_cli --collection caselaw

# IPC to BNS mappings
.\.venv\Scripts\python.exe -m retrieval.rag_cli --collection crossreference

# Search all collections
.\.venv\Scripts\python.exe -m retrieval.rag_cli --collection all
```

### Output Formats

```powershell
# Text output (default)
.\.venv\Scripts\python.exe -m retrieval.rag_cli --output text

# JSON output (for programmatic use)
.\.venv\Scripts\python.exe -m retrieval.rag_cli --output json
```

## Python API

```python
from retrieval.rag_pipeline import LegalRAGPipeline

# Initialize pipeline
rag = LegalRAGPipeline(
    llm_provider="openai",
    llm_model="gpt-4-turbo-preview",
    min_confidence=0.50,
)

# Ask a question
response = rag.query("What is punishment for theft?", collection="statutes")

# Display answer
print(response.answer)
print(f"Confidence: {response.confidence_label}")
print(f"Sources: {response.source_citations}")

# Export as JSON
import json
print(json.dumps(response.to_json(), indent=2))
```

## Parameter Guide

| Parameter | Default | Options | Purpose |
|-----------|---------|---------|---------|
| `--collection` | statutes | statutes, caselaw, crossreference, all | Which legal documents to search |
| `--llm` | openai | openai, anthropic | Which LLM provider to use |
| `--model` | gpt-4-turbo | Various | Which specific model to use |
| `--top-k` | 5 | 1-20 | Number of results to retrieve |
| `--alpha` | 0.6 | 0.0-1.0 | Dense/lexical balance (0=pure lexical, 1=pure dense) |
| `--min-confidence` | 0.50 | 0.0-1.0 | Minimum confidence threshold for results |
| `--output` | text | text, json | Output format |
| `--verbose` | False | - | Enable detailed logging |
| `--api-key` | env var | sk-... | Override API key |

## Example Questions

### Criminal Law
- "What is the punishment for theft?"
- "What sections of IPC deal with theft?"
- "What are bail grounds in serious crimes?"
- "Difference between robbery and dacoity"

### Constitutional Law
- "What are fundamental rights?"
- "What does Article 21 protect?"
- "What is judicial review?"

### Family Law
- "What are grounds for divorce under Hindu Marriage Act?"
- "What is legal age for marriage?"
- "What is child custody law?"

### Tenancy & Property
- "What are tenant rights under rent control?"
- "How to resolve landlord-tenant disputes?"
- "What is eviction process?"

## Troubleshooting

### Issue: API Key Not Found
```powershell
# Set environment variable
$env:OPENAI_API_KEY = "sk-your-key-here"

# Or pass directly
.\.venv\Scripts\python.exe -m retrieval.rag_cli --api-key "sk-..."
```

### Issue: Module Not Found
```powershell
# Reinstall dependencies
pip install -r requirements.txt

# Or specific packages
pip install openai anthropic
```

### Issue: Slow Performance
```powershell
# Use smaller model
.\.venv\Scripts\python.exe -m retrieval.rag_cli \
  --llm anthropic \
  --model claude-3-haiku-20240307

# Reduce results
.\.venv\Scripts\python.exe -m retrieval.rag_cli --top-k 3
```

### Issue: Confidence Scores Too Low
```powershell
# Lower confidence threshold
.\.venv\Scripts\python.exe -m retrieval.rag_cli --min-confidence 0.30
```

## Confidence Levels

- **High (≥0.80)**: Very reliable, multiple sources agree
- **Medium (0.50-0.80)**: Reasonable confidence, single source
- **Low (<0.50)**: Uncertain, weak retrieval match

## File Locations

- **System Prompt**: `retrieval/system_prompt.md`
- **Confidence Scorer**: `retrieval/confidence_scorer.py`
- **RAG Pipeline**: `retrieval/rag_pipeline.py`
- **CLI Interface**: `retrieval/rag_cli.py`
- **Documentation**: `retrieval/README.md`
- **Test Script**: `test_rag_pipeline.py`

## Getting Help

1. **Check documentation**: `retrieval/README.md`
2. **Review system prompt**: `retrieval/system_prompt.md`
3. **Run test script**: `python test_rag_pipeline.py`
4. **Enable verbose mode**: `--verbose` flag
5. **Check source retrieval**: Use `retrieval.cli` without LLM

## Next Steps

- [ ] Test with your own legal questions
- [ ] Calibrate confidence threshold for your use case
- [ ] Deploy as REST API for production use
- [ ] Add web UI for end-users
- [ ] Integrate with other tools

---

**Status**: ✅ Ready for Production  
**Last Updated**: 2026-08-31  
**Version**: 1.0
