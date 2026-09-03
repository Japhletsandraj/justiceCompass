"""Confidence scoring for RAG retrieval results."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass
class ConfidenceMetrics:
    """Detailed confidence metrics for a retrieved document."""

    document_id: str
    retrieval_score: float  # 0-1 from hybrid retriever
    source_type_score: float  # 0-1 based on source relevance
    recency_score: float  # 0-1 based on publication/amendment date
    directness_score: float  # 0-1 based on relevance to query
    specificity_score: float  # 0-1 based on specificity of provision
    citation_frequency_score: float  # 0-1 based on how often cited
    consensus_score: float  # 0-1 if multiple sources agree
    overall_confidence: float  # weighted composite score
    confidence_label: str  # "High" / "Medium" / "Low"
    reasoning: str  # explanation of confidence score


class ConfidenceScorer:
    """Score confidence of retrieval results for legal Q&A."""

    # Weights for different confidence factors
    WEIGHTS = {
        "retrieval": 0.30,  # Raw retrieval score weight
        "source_type": 0.15,  # Type of source (statute vs case)
        "recency": 0.10,  # How recent is the source
        "directness": 0.20,  # How directly does it answer the query
        "specificity": 0.10,  # How specific is the provision
        "citation_frequency": 0.05,  # How often is it cited
        "consensus": 0.10,  # Do multiple sources agree
    }

    # Source type scores (higher = more authoritative for direct answers)
    SOURCE_SCORES = {
        "statute": 0.95,  # Statutes are most authoritative
        "constitutional": 0.95,  # Constitution is primary source
        "case_law": 0.85,  # Case law interprets statutes
        "cross_reference": 0.70,  # Cross-references are supporting
    }

    # Recency factors (year-based scoring)
    RECENCY_BENCHMARK = 2023  # Reference year for recency

    def __init__(self, verbose: bool = False):
        """Initialize the confidence scorer.

        Args:
            verbose: If True, provide detailed reasoning for each score.
        """
        self.verbose = verbose

    @staticmethod
    def _get_source_type(record: dict[str, Any]) -> str:
        """Determine the source type of a record."""
        payload = record.get("payload") or {}

        # Check for constitutional content
        if "constitution" in record.get("text", "").lower()[:100]:
            return "constitutional"

        # Check for statute/act
        if payload.get("record_type") == "statute" or "act" in payload.get("source", "").lower():
            return "statute"

        # Check for cross-reference
        if payload.get("record_type") == "crossreference":
            return "cross_reference"

        # Default to case law
        if payload.get("record_type") == "case" or "court" in payload.get("source", "").lower():
            return "case_law"

        return "case_law"

    @staticmethod
    def _extract_year(date_value: Any) -> int | None:
        """Extract year from various date formats."""
        if isinstance(date_value, int):
            return date_value if 1800 <= date_value <= 2100 else None

        if isinstance(date_value, str):
            # Try to extract year from string
            import re

            match = re.search(r"\b(18|19|20)\d{2}\b", date_value)
            if match:
                return int(match.group(0))

        return None

    def _calculate_source_type_score(self, record: dict[str, Any]) -> float:
        """Calculate source type confidence score."""
        source_type = self._get_source_type(record)
        return self.SOURCE_SCORES.get(source_type, 0.7)

    def _calculate_recency_score(self, record: dict[str, Any]) -> float:
        """Calculate recency confidence score.

        Newer statutes and amendments are more relevant (score 0.9-1.0).
        Older but still-valid statutes get medium scores (0.6-0.9).
        Very old archived statutes get lower scores (0.3-0.6).
        """
        payload = record.get("payload") or {}

        # Check for recency indicators
        source_type = self._get_source_type(record)

        # Try to extract year
        year = None
        for date_field in ["date", "year", "amendment_date", "commencement_date"]:
            year = self._extract_year(payload.get(date_field))
            if year:
                break

        if year is None:
            # If no date found, use text heuristics
            text = record.get("text", "")
            year = self._extract_year(text[:200])

        if year is None:
            # Default scores by source type
            if source_type == "constitutional":
                return 0.8  # Constitution is timeless but amended
            elif source_type == "statute":
                return 0.7  # Unknown age statute
            else:
                return 0.6  # Assume older case law

        # Calculate recency penalty
        age = self.RECENCY_BENCHMARK - year

        if age < 0:
            # Future date (shouldn't happen, but handle it)
            return 0.5
        elif age <= 1:
            # Very recent (last year) - highest score
            return 0.95
        elif age <= 5:
            # Recent (last 5 years)
            return 0.90
        elif age <= 10:
            # Moderately recent (5-10 years)
            return 0.80
        elif age <= 20:
            # Older but valid (10-20 years)
            return 0.70
        elif age <= 50:
            # Historic but potentially relevant (20-50 years)
            return 0.50
        else:
            # Very old (might be archived)
            return 0.30

    def _calculate_directness_score(
        self,
        record: dict[str, Any],
        query_text: str,
        retrieval_score: float,
    ) -> float:
        """Calculate directness score based on query-result relevance.

        High retrieval scores already indicate directness, but we add
        semantic checks for legal specificity.
        """
        payload = record.get("payload") or {}
        text = record.get("text", "")[:500].lower()
        query_lower = query_text.lower()

        # Start with retrieval score as base
        directness = retrieval_score

        # Boost if exact terms are found
        query_terms = query_lower.split()
        matching_terms = sum(1 for term in query_terms if len(term) > 3 and term in text)
        term_boost = min(0.15, matching_terms * 0.05)
        directness = min(1.0, directness + term_boost)

        # Boost for section-specific matches
        if "section" in query_lower:
            section_num = None
            import re

            match = re.search(r"section\s*(\d+)", query_lower)
            if match:
                section_num = match.group(1)
                if section_num in text:
                    directness = min(1.0, directness + 0.10)

        # Boost if it's a direct statutory provision
        if payload.get("record_type") == "statute":
            directness = min(1.0, directness + 0.05)

        return directness

    def _calculate_specificity_score(self, record: dict[str, Any]) -> float:
        """Calculate specificity score.

        Specific provisions (with section numbers) score higher than
        general concepts.
        """
        payload = record.get("payload") or {}

        score = 0.5  # Base score for any legal provision

        # Boost for specific sections
        if payload.get("section_number"):
            score += 0.25

        # Boost for acts/statutes
        if payload.get("act_abbrev"):
            score += 0.15

        # Boost for jurisdiction-specific
        if payload.get("jurisdiction"):
            score += 0.10

        # Slightly penalize very broad categories
        if len(record.get("text", "")) > 5000:
            score -= 0.05

        return min(1.0, score)

    def _calculate_citation_frequency_score(self, record: dict[str, Any]) -> float:
        """Calculate citation frequency score.

        Often-cited provisions are more likely to be authoritative.
        This is a simplified heuristic based on available metadata.
        """
        payload = record.get("payload") or {}

        score = 0.5  # Default neutral score

        # Check for citation keys or references
        citations = payload.get("citation_keys", [])
        if isinstance(citations, list):
            score += min(0.3, len(citations) * 0.05)
        elif isinstance(citations, str) and citations:
            citation_count = len(citations.split(";"))
            score += min(0.3, citation_count * 0.05)

        # Landmark cases or frequently referenced statutes
        if payload.get("is_landmark_case"):
            score += 0.15

        # Check if it appears in multiple collections
        # (This would require cross-collection analysis)

        return min(1.0, score)

    def _calculate_consensus_score(self, all_results: list[dict[str, Any]]) -> dict[str, float]:
        """Calculate consensus scores for a set of results.

        Returns a dict mapping document IDs to consensus scores.
        If multiple results support similar conclusions, boost confidence.
        """
        consensus_scores = {result["id"]: 0.5 for result in all_results}

        # Group by key legal concepts
        concept_groups: dict[str, list[str]] = {}

        for result in all_results:
            payload = result["record"].get("payload") or {}

            # Group by act/statute
            act = payload.get("act_abbrev")
            if act:
                if act not in concept_groups:
                    concept_groups[act] = []
                concept_groups[act].append(result["id"])

        # Boost scores for items in larger groups
        for group_ids in concept_groups.values():
            if len(group_ids) > 1:
                boost = min(0.3, len(group_ids) * 0.10)
                for doc_id in group_ids:
                    consensus_scores[doc_id] = min(1.0, consensus_scores[doc_id] + boost)

        return consensus_scores

    def score_result(
        self,
        result: dict[str, Any],
        query_text: str,
        all_results: list[dict[str, Any]] | None = None,
    ) -> ConfidenceMetrics:
        """Score a single retrieval result.

        Args:
            result: Result dict from hybrid_retriever with keys:
                    id, fused_score, dense_score, lexical_score, record
            query_text: Original user query
            all_results: All results (for consensus calculation)

        Returns:
            ConfidenceMetrics with detailed scoring breakdown
        """
        record = result.get("record", {})
        retrieval_score = result.get("fused_score", 0.0)

        # Calculate individual scores
        source_type_score = self._calculate_source_type_score(record)
        recency_score = self._calculate_recency_score(record)
        directness_score = self._calculate_directness_score(record, query_text, retrieval_score)
        specificity_score = self._calculate_specificity_score(record)
        citation_frequency_score = self._calculate_citation_frequency_score(record)

        # Calculate consensus
        consensus_score = 0.5
        if all_results:
            consensus_scores = self._calculate_consensus_score(all_results)
            consensus_score = consensus_scores.get(result["id"], 0.5)

        # Calculate weighted overall confidence
        overall_confidence = (
            self.WEIGHTS["retrieval"] * retrieval_score
            + self.WEIGHTS["source_type"] * source_type_score
            + self.WEIGHTS["recency"] * recency_score
            + self.WEIGHTS["directness"] * directness_score
            + self.WEIGHTS["specificity"] * specificity_score
            + self.WEIGHTS["citation_frequency"] * citation_frequency_score
            + self.WEIGHTS["consensus"] * consensus_score
        )

        # Determine confidence label
        if overall_confidence >= 0.80:
            confidence_label = "High"
        elif overall_confidence >= 0.50:
            confidence_label = "Medium"
        else:
            confidence_label = "Low"

        # Generate reasoning
        reasoning = self._generate_reasoning(
            confidence_label,
            retrieval_score,
            source_type_score,
            recency_score,
            directness_score,
            specificity_score,
            citation_frequency_score,
            consensus_score,
            record,
        )

        return ConfidenceMetrics(
            document_id=result["id"],
            retrieval_score=float(retrieval_score),
            source_type_score=float(source_type_score),
            recency_score=float(recency_score),
            directness_score=float(directness_score),
            specificity_score=float(specificity_score),
            citation_frequency_score=float(citation_frequency_score),
            consensus_score=float(consensus_score),
            overall_confidence=float(overall_confidence),
            confidence_label=confidence_label,
            reasoning=reasoning,
        )

    def _generate_reasoning(
        self,
        confidence_label: str,
        retrieval_score: float,
        source_type_score: float,
        recency_score: float,
        directness_score: float,
        specificity_score: float,
        citation_frequency_score: float,
        consensus_score: float,
        record: dict[str, Any],
    ) -> str:
        """Generate human-readable reasoning for confidence score."""
        payload = record.get("payload") or {}
        source_type = self._get_source_type(record)

        reasons = []

        # Retrieval score
        if retrieval_score >= 0.75:
            reasons.append("strong search result match")
        elif retrieval_score >= 0.50:
            reasons.append("moderate search result relevance")
        else:
            reasons.append("weak search result match")

        # Source type
        if source_type == "statute":
            reasons.append("authoritative statutory source")
        elif source_type == "constitutional":
            reasons.append("primary constitutional source")
        elif source_type == "case_law":
            reasons.append("judicial precedent and interpretation")
        else:
            reasons.append(f"{source_type} reference")

        # Recency
        if recency_score >= 0.90:
            reasons.append("very recent/current")
        elif recency_score >= 0.75:
            reasons.append("recently updated")
        elif recency_score >= 0.50:
            reasons.append("established and valid")
        else:
            reasons.append("older reference")

        # Specificity
        if specificity_score >= 0.75:
            reasons.append("specific legal provision")
        else:
            reasons.append("general legal principle")

        # Citation frequency
        if citation_frequency_score >= 0.70:
            reasons.append("frequently cited")
        elif citation_frequency_score >= 0.50:
            reasons.append("standard reference")

        # Consensus
        if consensus_score >= 0.75:
            reasons.append("multiple corroborating sources")

        return f"{confidence_label} confidence: {'; '.join(reasons)}"

    def filter_by_confidence(
        self,
        results: list[dict[str, Any]],
        query_text: str,
        min_confidence: float = 0.50,
    ) -> tuple[list[dict[str, Any]], list[ConfidenceMetrics]]:
        """Filter results by minimum confidence threshold.

        Args:
            results: List of results from hybrid_retriever
            query_text: Original user query
            min_confidence: Minimum confidence score (0-1) to include result

        Returns:
            Tuple of (filtered_results, confidence_metrics)
        """
        confidence_metrics_list = []

        for result in results:
            metrics = self.score_result(result, query_text, all_results=results)
            confidence_metrics_list.append(metrics)

        # Filter by threshold
        filtered_results = [
            result
            for result, metrics in zip(results, confidence_metrics_list)
            if metrics.overall_confidence >= min_confidence
        ]
        filtered_metrics = [
            metrics for metrics in confidence_metrics_list if metrics.overall_confidence >= min_confidence
        ]

        return filtered_results, filtered_metrics

    def get_aggregate_confidence(self, confidence_metrics_list: list[ConfidenceMetrics]) -> float:
        """Calculate aggregate confidence across multiple results.

        Returns a single confidence score representing overall answer confidence.
        """
        if not confidence_metrics_list:
            return 0.0

        # Weight by individual confidence (higher confidence carries more weight)
        total_weight = sum(m.overall_confidence for m in confidence_metrics_list)
        if total_weight == 0:
            return 0.0

        # Weighted average of confidence scores
        weighted_sum = sum(m.overall_confidence ** 2 for m in confidence_metrics_list)

        return min(1.0, weighted_sum / total_weight)
