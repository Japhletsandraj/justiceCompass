"""Interactive CLI for the Legal RAG pipeline."""

from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from ai.retrieval.rag_pipeline import LegalRAGPipeline


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Legal Q&A system powered by RAG and Indian legal knowledge base."
    )
    parser.add_argument(
        "--collection",
        choices=["statutes", "caselaw", "crossreference", "all"],
        default="statutes",
        help="Knowledge base collection to search",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Number of retrieval results to include",
    )
    parser.add_argument(
        "--alpha",
        type=float,
        default=0.6,
        help="Dense score weight (0-1, where 1=pure dense, 0=pure lexical)",
    )
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=0.50,
        help="Minimum confidence threshold for including results (0-1)",
    )
    parser.add_argument(
        "--llm",
        choices=["openrouter", "openai", "anthropic"],
        default="openrouter",
        help="LLM provider to use",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Specific LLM model (e.g., gpt-4-turbo-preview, claude-3-haiku)",
    )
    parser.add_argument(
        "--output",
        choices=["text", "json"],
        default="text",
        help="Output format",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable detailed logging",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="API key for LLM provider (defaults to env var)",
    )

    args = parser.parse_args()

    # Validate arguments
    if not 0 <= args.alpha <= 1:
        parser.error("--alpha must be between 0 and 1")

    if not 0 <= args.min_confidence <= 1:
        parser.error("--min-confidence must be between 0 and 1")

    # Set default models
    if args.model is None:
        if args.llm == "openai":
            args.model = os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-4-340b-instruct:free")
        elif args.llm == "anthropic":
            args.model = "claude-3-haiku-20240307"

    # Initialize RAG pipeline
    print("Initializing RAG pipeline...")
    try:
        rag = LegalRAGPipeline(
            llm_provider=args.llm,
            llm_model=args.model,
            api_key=args.api_key,
            min_confidence=args.min_confidence,
            verbose=args.verbose,
        )
    except ImportError as e:
        print(f"Error: {e}")
        print(f"Install required packages: pip install openai anthropic")
        return 1
    except ValueError as e:
        print(f"Error: {e}")
        return 1

    print(f"RAG Pipeline ready!")
    print(f"  Provider: {args.llm}")
    print(f"  Model: {args.model}")
    print(f"  Collection: {args.collection}")
    print(f"  Min Confidence: {args.min_confidence:.2f}")
    print(f"\nType your legal question (or 'exit' to quit):\n")

    # Interactive loop
    while True:
        try:
            question = input("Question> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            return 0

        if question.lower() in {"exit", "quit"}:
            print("Goodbye!")
            return 0

        if not question:
            continue

        # Process query
        try:
            print("\n[Processing...]")
            response = rag.query(
                question,
                collection=args.collection,
                top_k=args.top_k,
                alpha=args.alpha,
            )

            # Format and display response
            if args.output == "json":
                print(rag.to_json(response))
            else:
                print(rag.format_response(response))

            print()

        except Exception as e:
            print(f"\nError processing query: {e}")
            if args.verbose:
                import traceback

                traceback.print_exc()
            print()


if __name__ == "__main__":
    raise SystemExit(main())
