"""Interactive terminal test for the complete local RAG-to-LLM flow."""

from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from ai.retrieval.rag_pipeline import LegalRAGPipeline
from ai.retrieval.indiankanoon_client import IndianKanoonClient
from ai.retrieval.prediction import estimate_historical_outcome


def main() -> int:
    parser = argparse.ArgumentParser(description="Test JusticeCompass retrieval and LLM generation.")
    parser.add_argument("--question", help="Run one question without opening the interactive prompt")
    parser.add_argument("--collection", choices=["statutes", "caselaw", "crossreference", "all"], default="all")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--min-confidence", type=float, default=0.50)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--live-kanoon", action="store_true", help="Fetch a small cached set of Indian Kanoon judgments")
    parser.add_argument("--max-full-judgments", type=int, default=20, choices=range(1, 21), help="Maximum full judgments to fetch")
    args = parser.parse_args()

    provider = os.getenv("LLM_PROVIDER", "openrouter")
    model = os.getenv("LLM_MODEL") or os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-4-340b-instruct:free")
    prompt_file = os.getenv("SYSTEM_PROMPT_FILE", "ai/retrieval/system_prompt.md")

    print("JusticeCompass RAG pipeline test")
    print(f"Provider: {provider}")
    print(f"Model: {model}")
    print(f"System prompt: {prompt_file}")
    print(f"Collection: {args.collection}")
    print("OpenRouter key: configured (value hidden)" if os.getenv("OPENROUTER_API_KEY") else "OpenRouter key: missing")

    try:
        rag = LegalRAGPipeline(
            llm_provider=provider,
            llm_model=model,
            min_confidence=args.min_confidence,
            verbose=args.verbose,
        )
    except Exception as exc:
        print(f"\nStartup failed: {exc}")
        return 1

    print("Ready. Type a question, or type 'exit' to stop.\n")
    question = args.question
    while True:
        if question is None:
            question = input("Question> ").strip()
        if question.lower() in {"exit", "quit"}:
            print("Goodbye!")
            return 0
        if not question:
            question = None
            continue

        try:
            print("\n[1/4] Embedding question and searching the knowledge base...")
            live_records = []
            additional_context = None
            if args.live_kanoon:
                live_records = IndianKanoonClient().search_judgments(question, max_documents=args.max_full_judgments)
                additional_context = "\n\n".join(
                    f"Case number: {record.get('document_id')}\nTitle: {record.get('title')}\nOutcome: {record.get('outcome') or 'Not confidently extracted'}\n{record.get('text', '')}"
                    for record in live_records
                )
                print(f"[Live Indian Kanoon] Fetched {len(live_records)} cached/full judgments")
            response = rag.query(
                question,
                collection=args.collection,
                top_k=args.top_k,
                additional_context=additional_context,
            )
            print(f"[2/4] Retrieved {len(response.context_items)} context sources")
            print("[3/4] Sent retrieved context through the configured system prompt to the LLM")
            print("[4/4] Response received\n")
            print(rag.format_response(response))
            if live_records:
                estimate = estimate_historical_outcome(live_records, min_cases=5)
                print("\nLIVE INDIAN KANOON SUMMARY")
                print(f"Case records: {', '.join(str(record.get('document_id')) for record in live_records)}")
                print(f"Historical prediction score: {estimate.estimate if estimate.estimate is not None else 'Unavailable'}")
                print(f"Prediction basis: {estimate.basis}")
        except Exception as exc:
            print(f"\nQuestion failed: {exc}")
            if args.verbose:
                import traceback
                traceback.print_exc()

        if args.question:
            return 0
        question = None
        print()


if __name__ == "__main__":
    raise SystemExit(main())
