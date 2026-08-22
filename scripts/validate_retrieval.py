from __future__ import annotations

import os
import sys

from sentence_transformers import SentenceTransformer

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from knowledge_base.indices.retriever import HybridRetriever


def main():
    model = SentenceTransformer("BAAI/bge-m3")
    retriever = HybridRetriever(ROOT)

    queries = [
        {
            "text": "What is the punishment for murder under the criminal law?",
            "collection": "statutes",
            "filters": {"act": "IPC"},
        },
        {
            "text": "Explain bail conditions in criminal cases",
            "collection": "caselaw",
            "filters": {},
        },
        {
            "text": "Find relevant provisions on rent control in Tamil Nadu",
            "collection": "statutes",
            "filters": {"act": "TNRRRLT"},
        },
        {
            "text": "What does the Constitution say about equality?",
            "collection": "statutes",
            "filters": {"act": "COI"},
        },
    ]

    for query in queries:
        embedding = model.encode(query["text"], normalize_embeddings=True)
        results = retriever.hybrid_search(embedding, query["text"], query["collection"], k=5, alpha=0.6)
        if query["filters"]:
            results = retriever.filter_by_metadata(results, query["filters"])
        print(f"\nQuery: {query['text']}")
        if not results:
            print("  No results returned")
            continue
        for i, result in enumerate(results[:3], 1):
            record = result["record"]
            payload = record.get("payload") or {}
            title = payload.get("section_title") or record.get("section_title") or record.get("title") or "N/A"
            act = payload.get("act_abbrev") or record.get("act_abbrev") or "N/A"
            citation = payload.get("citation_keys") or record.get("citation_key") or "N/A"
            print(f"  {i}. {act} | {title} | score={result['fused_score']:.3f} | citation={citation}")


if __name__ == "__main__":
    main()
