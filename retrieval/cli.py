from __future__ import annotations

import argparse
import os
import sys

from sentence_transformers import SentenceTransformer

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from retrieval.hybrid_retriever import HybridRetriever


COLLECTIONS = ("statutes", "caselaw", "crossreference")


def display_result(result: dict, position: int) -> None:
    record = result["record"]
    payload = record.get("payload") or {}
    title = payload.get("section_title") or payload.get("title") or ""
    act = payload.get("act_abbrev") or ""
    section = payload.get("section_number") or ""
    citation = payload.get("citation_keys") or []
    if not title:
        title = payload.get("court") or payload.get("source") or "Result"
    label = " ".join(str(part) for part in (act, section, title) if part)
    print(
        f"{position}. {label}\n"
        f"   score={result['fused_score']:.3f} "
        f"dense={result['dense_score']:.3f} lexical={result['lexical_score']:.3f}\n"
        f"   citation={citation}\n"
        f"   {record.get('text', '')[:500].replace(chr(10), ' ')}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Ask questions against the JusticeCompass hybrid retrieval system.")
    parser.add_argument("--collection", choices=COLLECTIONS, default="statutes")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--alpha", type=float, default=0.6, help="Dense score weight from 0 to 1")
    args = parser.parse_args()

    if not 0 <= args.alpha <= 1:
        parser.error("--alpha must be between 0 and 1")

    print("Loading embedding model and retrieval indices...")
    model = SentenceTransformer("BAAI/bge-m3")
    retriever = HybridRetriever(ROOT)
    print(f"Ready. Collection: {args.collection}. Type 'exit' to quit.\n")

    while True:
        try:
            question = input("Question> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if question.lower() in {"exit", "quit"}:
            return 0
        if not question:
            continue

        embedding = model.encode(question, normalize_embeddings=True)
        results = retriever.hybrid_search(
            embedding, question, args.collection, k=args.top_k, alpha=args.alpha
        )
        print(f"\nTop {len(results)} results")
        for position, result in enumerate(results, 1):
            display_result(result, position)
        print()


if __name__ == "__main__":
    raise SystemExit(main())
