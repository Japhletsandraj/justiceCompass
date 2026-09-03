"""Test script for RAG pipeline components (retrieval and confidence scoring)."""

from __future__ import annotations

import sys
import os

ROOT = os.getcwd()
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from ai.retrieval.hybrid_retriever import HybridRetriever
from ai.retrieval.confidence_scorer import ConfidenceScorer
from sentence_transformers import SentenceTransformer


def test_retrieval_and_confidence():
    """Test the retrieval system and confidence scoring."""
    print("=" * 80)
    print("RAG PIPELINE TEST: Retrieval and Confidence Scoring")
    print("=" * 80)

    # Initialize components
    print("\n[1/4] Initializing retrieval system...")
    retriever = HybridRetriever(ROOT)
    print(f"      ✓ Loaded {len(retriever.records['statutes'])} statute records")
    print(f"      ✓ Loaded {len(retriever.records['caselaw'])} case law records")
    print(f"      ✓ Loaded {len(retriever.records['crossreference'])} cross-reference records")

    print("\n[2/4] Initializing embedding model...")
    model = SentenceTransformer("BAAI/bge-m3")
    print("      ✓ BGE-M3 model loaded")

    print("\n[3/4] Initializing confidence scorer...")
    scorer = ConfidenceScorer(verbose=True)
    print("      ✓ Confidence scorer ready")

    # Test queries
    test_queries = [
        ("What is punishment for theft?", "statutes"),
        ("What are bail conditions?", "caselaw"),
        ("IPC to BNS mapping", "crossreference"),
    ]

    for query, collection in test_queries:
        print(f"\n[4/4] Testing retrieval: '{query}'")
        print(f"      Collection: {collection}")

        # Embed query
        embedding = model.encode(query, normalize_embeddings=True)

        # Retrieve results
        results = retriever.hybrid_search(embedding, query, collection, k=3, alpha=0.6)
        print(f"      ✓ Retrieved {len(results)} results")

        # Score confidence
        filtered_results, metrics = scorer.filter_by_confidence(results, query, min_confidence=0.0)
        print(f"      ✓ Scored {len(metrics)} results by confidence")

        # Display results
        print("\n      Top Results:")
        for i, (result, metric) in enumerate(zip(filtered_results, metrics), 1):
            record = result["record"]
            payload = record.get("payload", {})

            # Determine source
            if "section_title" in payload:
                source = f"{payload.get('act_abbrev', 'Act')} - {payload.get('section_number', '')}"
            elif "case_name" in payload:
                source = payload.get("case_name", "Case")
            else:
                source = payload.get("source", "Source")

            # Display
            print(f"\n      [{i}] {source}")
            print(f"          Confidence: {metric.confidence_label} ({metric.overall_confidence:.3f})")
            print(f"          Score Breakdown:")
            print(f"            - Retrieval: {metric.retrieval_score:.3f}")
            print(f"            - Source Type: {metric.source_type_score:.3f}")
            print(f"            - Recency: {metric.recency_score:.3f}")
            print(f"            - Directness: {metric.directness_score:.3f}")
            print(f"            - Specificity: {metric.specificity_score:.3f}")
            print(f"            - Citation Freq: {metric.citation_frequency_score:.3f}")
            print(f"            - Consensus: {metric.consensus_score:.3f}")
            print(f"          Reasoning: {metric.reasoning}")
            print(f"          Text: {record.get('text', '')[:150].replace(chr(10), ' ')}...")

        # Aggregate confidence
        aggregate = scorer.get_aggregate_confidence(metrics)
        print(f"\n      Aggregate Confidence: {aggregate:.3f}")

    print("\n" + "=" * 80)
    print("TEST COMPLETE - All components working!")
    print("=" * 80)
    print("\nNext steps:")
    print("  1. Set environment variable: $env:OPENAI_API_KEY = 'sk-...'")
    print("  2. Run RAG pipeline: .\\. venv\\Scripts\\python.exe -m retrieval.rag_cli")
    print("=" * 80)


if __name__ == "__main__":
    try:
        test_retrieval_and_confidence()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
