# Terminal RAG Test

This test accepts a question, retrieves matching local legal records, sends those records to the configured LLM through the system prompt, and prints the answer, citations, and confidence.

## Configure `.env`

Add or update these settings. Keep API key values private:

```env
LLM_PROVIDER=openrouter
LLM_MODEL=nvidia/nemotron-4-340b-instruct:free
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_TEMPERATURE=0.3
SYSTEM_PROMPT_FILE=retrieval/system_prompt.md
```

The pipeline uses `OPENROUTER_API_KEY` and does not require an OpenAI account or OpenAI billing.

## Run interactively

```powershell
.\.venv\Scripts\python.exe ai\run_rag_test.py
```

You will see:

```text
Question> What is the punishment for theft under Indian law?
```

Type a question and press Enter. Type `exit` to stop.

## Run one question

```powershell
.\.venv\Scripts\python.exe ai\run_rag_test.py --question "What is the punishment for theft under Indian law?"
```

## Useful options

```powershell
.\.venv\Scripts\python.exe ai\run_rag_test.py --collection all --top-k 5 --verbose
```

The output identifies four stages: embedding and retrieval, number of sources, LLM/system-prompt generation, and the final response. The answer must use only retrieved context and should show source citations. A confidence score is source/retrieval confidence, not a probability of winning a case.

This command uses the local knowledge base and does not call Indian Kanoon unless `--live-kanoon` is supplied. Live mode fetches up to 20 judgments by default. A historical score still requires at least 5 judgments with clearly extracted final outcomes.
