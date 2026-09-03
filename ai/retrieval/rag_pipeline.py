"""RAG pipeline for legal Q&A using retrieved documents and LLM."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from typing import Any

from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

from ai.retrieval.confidence_scorer import ConfidenceMetrics, ConfidenceScorer
from ai.retrieval.hybrid_retriever import HybridRetriever

load_dotenv()


@dataclass
class ContextItem:
    """A single piece of context retrieved for the answer."""

    source: str  # e.g., "IPC Section 302" or "Case Name, Year"
    text: str
    confidence: float
    source_type: str  # statute, case_law, constitutional, etc.
    metadata: dict[str, Any]


@dataclass
class RAGResponse:
    """Complete response from the RAG pipeline."""

    answer: str
    confidence_score: float
    confidence_label: str  # High, Medium, Low
    source_citations: list[str]
    context_items: list[ContextItem]
    retrieval_metrics: list[ConfidenceMetrics]
    query: str
    model_used: str
    data_sufficiency: str  # "sufficient" or "insufficient"
    next_steps: list[str] | None = None  # Actionable guidance for user
    structured_answer: dict[str, Any] | None = None
    
    def __post_init__(self):
        """Set default next_steps if not provided."""
        if self.next_steps is None:
            self.next_steps = []


class LegalRAGPipeline:
    """RAG pipeline for legal Q&A with confidence scoring."""

    # System prompt template
    SYSTEM_PROMPT_TEMPLATE = """You are an expert legal assistant powered by JusticeCompass, a specialized AI system trained on Indian legal statutes, constitutional law, case law, and cross-reference materials.

Your role is to provide accurate, cited, and legally grounded answers to legal questions.

## Core Responsibilities
1. Answer only based on the provided context from legal sources
2. Cite all legal sources explicitly (statute, section, case, article)
3. Be transparent about limitations and when professional counsel is needed
4. Provide jurisdiction-specific guidance when relevant
5. Avoid rendering personal legal opinions

## Knowledge Base
- Statutes: Criminal (IPC, BNS, CrPC, BNSS), Constitutional, Consumer Protection, Family Law, Tenancy & Property
- Case Law: 1,200 Indian bail-related court decisions
- Cross-References: IPC-to-BNS mapping and statute correspondences

## Response Structure
1. **Question Analysis**: Clarify and restate the question
2. **Applicable Law**: Cite relevant statutes/constitutional provisions
3. **Case Law**: Reference relevant judicial precedents
4. **Analysis**: Apply law to the scenario
5. **Confidence Score**: High/Medium/Low based on source quality
6. **Next Steps**: Professional consultation recommendations if needed

## Citation Format
- Statutes: [Act Name] [Year], Section [Number]
- Cases: [Case Name], [Court] [Year]
- Constitution: Constitution of India, Article [Number]

## Important Guidelines
- DO NOT make up citations or legal principles
- DO cite the provided sources in your answer
- DO state when information is not in your knowledge base
- DO recommend professional legal counsel for case-specific advice
- DO maintain a formal but accessible tone
- DO flag any uncertainty or limitations clearly"""

    STRUCTURED_RESPONSE_INSTRUCTION = """
Return your answer as valid JSON only, with exactly these keys:
{
    "concern_assessment": "possible concern, not a legal validity guarantee",
    "registrable_assessment": "likely registrable, possibly registrable, or cannot determine from supplied facts",
    "registration_conditions": ["facts, legal elements, jurisdiction, documents, and limitation requirements supported by context"],
    "registration_forum": "court, tribunal, authority, or unknown based only on context",
    "analysis": "source-grounded explanation",
    "applicable_law": ["law and section citations from context only"],
    "case_references": [{"case_number": "case id or citation from context", "title": "case title", "outcome": "if stated"}],
    "prediction_score": null,
    "prediction_basis": "why a score is unavailable, or a verified historical estimate",
    "next_steps": ["practical source-grounded steps"],
    "missing_information": ["facts needed before legal review"],
    "disclaimer": "general legal information, not legal advice"
}
Use null for prediction_score unless a verified historical outcome estimate is explicitly provided in the context. Never invent case numbers, outcomes, citations, or probabilities.
"""

    def __init__(
        self,
        retriever: HybridRetriever | None = None,
        embedding_model: str = "BAAI/bge-m3",
        confidence_scorer: ConfidenceScorer | None = None,
        llm_provider: str | None = None,
        llm_model: str | None = None,
        api_key: str | None = None,
        min_confidence: float = 0.50,
        verbose: bool = False,
    ):
        """Initialize the RAG pipeline.

        Args:
            retriever: HybridRetriever instance (created if None)
            embedding_model: Model name for query embedding
            confidence_scorer: ConfidenceScorer instance (created if None)
            llm_provider: "openai", "anthropic", or "local" (claude-3-haiku/sonnet/opus, llama2, etc.)
            llm_model: Specific model name
            api_key: API key for LLM provider (reads from env if None)
            min_confidence: Minimum confidence threshold for including results
            verbose: Enable detailed logging
        """
        self.min_confidence = min_confidence
        self.verbose = verbose
        self.llm_provider = llm_provider or os.getenv("LLM_PROVIDER", "openrouter")
        self.llm_model = llm_model or os.getenv("LLM_MODEL") or os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-4-340b-instruct:free")
        prompt_file = os.getenv("SYSTEM_PROMPT_FILE")
        self.system_prompt = self.SYSTEM_PROMPT_TEMPLATE
        if prompt_file:
            root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            prompt_path = prompt_file if os.path.isabs(prompt_file) else os.path.join(root_dir, prompt_file)
            with open(prompt_path, "r", encoding="utf-8") as handle:
                self.system_prompt = handle.read()

        # Initialize retriever
        if retriever is None:
            root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            self.retriever = HybridRetriever(root_dir)
        else:
            self.retriever = retriever

        # Initialize embedding model
        self.embedding_model = SentenceTransformer(embedding_model)

        # Initialize confidence scorer
        self.confidence_scorer = confidence_scorer or ConfidenceScorer(verbose=verbose)

        # Initialize LLM
        self._init_llm(self.llm_provider, self.llm_model, api_key)

    def _init_llm(self, provider: str, model: str, api_key: str | None) -> None:
        """Initialize LLM client."""
        self.llm_provider = provider
        self.llm_model = model

        if provider in {"openai", "openrouter"}:
            try:
                import openai

                api_key = api_key or os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")
                if not api_key:
                    raise ValueError("OPENROUTER_API_KEY environment variable not set")
                base_url = os.getenv("OPENROUTER_BASE_URL") or os.getenv("OPENAI_BASE_URL")
                self.llm_client = openai.OpenAI(api_key=api_key, base_url=base_url)
            except ImportError:
                raise ImportError("openai package not installed. Install with: pip install openai")

        elif provider == "anthropic":
            try:
                import anthropic

                api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
                if not api_key:
                    raise ValueError("ANTHROPIC_API_KEY environment variable not set")
                self.llm_client = anthropic.Anthropic(api_key=api_key)
            except ImportError:
                raise ImportError("anthropic package not installed. Install with: pip install anthropic")

        elif provider == "local":
            # For local models, we'll use ollama or similar
            # This is a placeholder for local LLM support
            self.llm_client = None
            if self.verbose:
                print(f"Using local model: {model}")

        else:
            raise ValueError(f"Unknown LLM provider: {provider}")

    def _embed_query(self, query: str) -> list[float]:
        """Embed the user query."""
        embedding = self.embedding_model.encode(query, normalize_embeddings=True)
        return embedding.tolist()

    def _format_context(self, results: list[dict[str, Any]], metrics: list[ConfidenceMetrics]) -> tuple[str, list[ContextItem]]:
        """Format retrieved results into context for the LLM.

        Returns:
            Tuple of (formatted_context_str, context_items_list)
        """
        context_items = []
        context_lines = []

        for result, metric in zip(results, metrics):
            record = result["record"]
            payload = record.get("payload") or {}

            # Determine source name
            source_type = self.confidence_scorer._get_source_type(record)

            if source_type == "statute":
                act = payload.get("act_abbrev", "Act")
                section = payload.get("section_number", "")
                title = payload.get("section_title", "")
                source = f"{act} Section {section}" if section else act
                if title:
                    source = f"{source}: {title}"

            elif source_type == "case_law":
                case_name = payload.get("case_name", "Case")
                court = payload.get("court", "Court")
                year = payload.get("year", "")
                source = f"{case_name}, {court} {year}".strip()

            elif source_type == "constitutional":
                article = payload.get("article_number", "")
                source = f"Constitution of India, Article {article}" if article else "Constitution of India"

            else:
                source = payload.get("source", "Source")

            text = record.get("text", "")[:1000]  # Limit to 1000 chars

            context_item = ContextItem(
                source=source,
                text=text,
                confidence=metric.overall_confidence,
                source_type=source_type,
                metadata=payload,
            )
            context_items.append(context_item)

            # Format for context string
            confidence_label = metric.confidence_label
            context_lines.append(f"\n### Source {len(context_items)}: {source}")
            context_lines.append(f"Confidence: {confidence_label} ({metric.overall_confidence:.2f})")
            context_lines.append(f"Type: {source_type}")
            context_lines.append(f"\n{text}")

        context_str = "\n".join(context_lines) if context_lines else "(No relevant context found above confidence threshold)"

        return context_str, context_items

    def _build_prompt(self, query: str, context: str) -> str:
        """Build the prompt for the LLM."""
        prompt = f"""## Legal Question
{query}

## Retrieved Legal Context
{context}

## Your Task
Based ONLY on the provided legal context above, provide a comprehensive answer to the legal question. Follow these guidelines:

1. **Start with the Question**: Briefly restate and clarify the question
2. **Cite the Applicable Law**: Quote the relevant statute/constitutional sections
3. **Reference Case Law**: If case law is provided, cite key judgments
4. **Analyze**: Apply the law to the question scenario
5. **State Confidence**: Assess the quality of your answer based on source availability
6. **Recommendations**: Suggest professional consultation if needed

If the context does not contain sufficient information to answer the question, explicitly state this and recommend what type of legal expertise would be needed.

Remember: Only cite sources from the context above. Do not use external knowledge.

{self.STRUCTURED_RESPONSE_INSTRUCTION}"""

        return prompt

    def _call_llm(self, prompt: str) -> str:
        """Call the LLM and get a response."""
        if self.llm_provider in {"openai", "openrouter"}:
            response = self.llm_client.chat.completions.create(
                model=self.llm_model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=2000,
                top_p=0.9,
                temperature=float(os.getenv("OPENROUTER_TEMPERATURE", "0.3")),
            )
            return response.choices[0].message.content

        elif self.llm_provider == "anthropic":
            response = self.llm_client.messages.create(
                model=self.llm_model,
                max_tokens=2000,
                system=self.system_prompt,
                messages=[
                    {"role": "user", "content": prompt},
                ],
            )
            return response.content[0].text

        elif self.llm_provider == "local":
            # Placeholder for local LLM
            raise NotImplementedError("Local LLM support coming soon")

        else:
            raise ValueError(f"Unknown LLM provider: {self.llm_provider}")

    def _extract_sources_from_answer(self, answer: str, context_items: list[ContextItem]) -> list[str]:
        """Extract sources cited in the answer."""
        citations = []

        for item in context_items:
            # Check if source appears in answer
            if item.source.lower() in answer.lower():
                citations.append(item.source)

        # Remove duplicates while preserving order
        seen = set()
        unique_citations = []
        for citation in citations:
            if citation not in seen:
                seen.add(citation)
                unique_citations.append(citation)

        return unique_citations

    @staticmethod
    def _parse_structured_answer(answer: str) -> dict[str, Any] | None:
        """Parse JSON even when a model wraps it in a markdown code fence."""
        candidate = answer.strip()
        if candidate.startswith("```"):
            candidate = candidate.strip("`").removeprefix("json").strip()
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None

    def query(
        self,
        question: str,
        collection: str = "statutes",
        top_k: int = 5,
        alpha: float = 0.6,
        additional_context: str | None = None,
    ) -> RAGResponse:
        """Process a legal query through the RAG pipeline.

        Args:
            question: The legal question
            collection: Which collection to search ("statutes", "caselaw", "crossreference", or "all")
            top_k: Number of top results to retrieve per collection
            alpha: Dense vs lexical score weight (0.6 = 60% dense, 40% lexical)

        Returns:
            RAGResponse with answer, confidence, and citations
        """
        if self.verbose:
            print(f"\n[RAG Pipeline] Processing query: {question}")

        # Step 1: Embed the query
        if self.verbose:
            print("[RAG Pipeline] Embedding query...")
        query_embedding = self._embed_query(question)

        # Step 2: Retrieve from knowledge base
        if self.verbose:
            print(f"[RAG Pipeline] Retrieving from collection(s)...")

        all_results = []
        if collection == "all":
            for col in ["statutes", "caselaw", "crossreference"]:
                results = self.retriever.hybrid_search(
                    query_embedding, question, col, k=top_k, alpha=alpha
                )
                all_results.extend(results)
        else:
            all_results = self.retriever.hybrid_search(
                query_embedding, question, collection, k=top_k, alpha=alpha
            )

        # Step 3: Score confidence
        if self.verbose:
            print(f"[RAG Pipeline] Scoring confidence for {len(all_results)} results...")

        filtered_results, confidence_metrics = self.confidence_scorer.filter_by_confidence(
            all_results, question, min_confidence=self.min_confidence
        )

        if self.verbose:
            print(f"[RAG Pipeline] {len(filtered_results)} results passed confidence threshold")

        # Step 4: Format context
        if self.verbose:
            print("[RAG Pipeline] Formatting context...")
        context_str, context_items = self._format_context(filtered_results, confidence_metrics)
        if additional_context:
            context_str = f"{context_str}\n\n## Additional Live Legal Sources\n{additional_context}"

        # Step 5: Build prompt
        if self.verbose:
            print("[RAG Pipeline] Building LLM prompt...")
        prompt = self._build_prompt(question, context_str)

        # Step 6: Call LLM
        if self.verbose:
            print(f"[RAG Pipeline] Calling {self.llm_provider} LLM ({self.llm_model})...")
        answer = self._call_llm(prompt)

        structured_answer = self._parse_structured_answer(answer)
        if structured_answer:
            answer = structured_answer.get("analysis", answer)
            next_steps = structured_answer.get("next_steps")
        else:
            next_steps = []

        # Step 7: Calculate aggregate confidence
        aggregate_confidence = self.confidence_scorer.get_aggregate_confidence(confidence_metrics)

        if aggregate_confidence >= 0.80:
            confidence_label = "High"
        elif aggregate_confidence >= 0.50:
            confidence_label = "Medium"
        else:
            confidence_label = "Low"

        # Step 8: Extract citations
        source_citations = self._extract_sources_from_answer(answer, context_items)

        data_sufficiency = "sufficient" if context_items else "insufficient"

        if self.verbose:
            print(f"[RAG Pipeline] Complete. Confidence: {confidence_label} ({aggregate_confidence:.2f})")

        return RAGResponse(
            answer=answer,
            confidence_score=aggregate_confidence,
            confidence_label=confidence_label,
            source_citations=source_citations,
            context_items=context_items,
            retrieval_metrics=confidence_metrics,
            query=question,
            model_used=self.llm_model,
            data_sufficiency=data_sufficiency,
            next_steps=next_steps,
            structured_answer=structured_answer,
        )

    def format_response(self, response: RAGResponse) -> str:
        """Format response for display."""
        output = []
        output.append("=" * 80)
        output.append("LEGAL Q&A RESPONSE")
        output.append("=" * 80)

        output.append(f"\nQuestion: {response.query}\n")

        output.append("ANSWER")
        output.append("-" * 80)
        structured = response.structured_answer or {}
        output.append(structured.get("concern_assessment", "Concern assessment: not separately structured."))
        output.append("\nCan This Be Registered?")
        output.append(f"  {structured.get('registrable_assessment', 'Cannot determine from the supplied facts.')}")
        output.append("\nRegistration Conditions:")
        conditions = structured.get("registration_conditions", [])
        for condition in conditions or ["Confirm legal elements, jurisdiction, documents, and limitation period with a qualified lawyer."]:
            output.append(f"  - {condition}")
        output.append(f"\nRegistration Forum: {structured.get('registration_forum', 'Unknown from retrieved sources.')}")
        output.append("\nAnalysis:")
        output.append(structured.get("analysis", response.answer))

        output.append("\nApplicable Law:")
        for law in structured.get("applicable_law", []):
            output.append(f"  - {law}")

        output.append("\nCase References:")
        case_references = structured.get("case_references", [])
        if case_references:
            for case in case_references:
                output.append(f"  - {case.get('case_number', 'Case number not provided')}: {case.get('title', 'Untitled case')} ({case.get('outcome', 'Outcome not stated')})")
        else:
            output.append("  - No case references identified in the retrieved context.")

        output.append("\nPrediction Score:")
        output.append(f"  {structured.get('prediction_score', 'Unavailable')}" )
        output.append(f"  Basis: {structured.get('prediction_basis', 'No verified outcome model was supplied.')}" )

        output.append("\nNext Steps:")
        next_steps = structured.get("next_steps", response.next_steps)
        for step in next_steps or ["Consult a qualified lawyer or legal-aid service for case-specific advice."]:
            output.append(f"  - {step}")

        output.append("\n" + "-" * 80)
        output.append(f"Confidence: {response.confidence_label} ({response.confidence_score:.2f})\n")

        if response.source_citations:
            output.append("Primary Sources Cited:")
            for citation in response.source_citations:
                output.append(f"  • {citation}")

        output.append("\nRetrieved Context:")
        for i, item in enumerate(response.context_items, 1):
            output.append(f"\n  [{i}] {item.source}")
            output.append(f"      Confidence: {item.confidence:.2f}")
            output.append(f"      {item.text[:200]}...")

        output.append("\n" + "=" * 80)

        return "\n".join(output)

    def to_json(self, response: RAGResponse) -> str:
        """Convert response to JSON."""
        data = {
            "query": response.query,
            "answer": response.answer,
            "confidence_score": response.confidence_score,
            "confidence_label": response.confidence_label,
            "data_sufficiency": response.data_sufficiency,
            "next_steps": response.next_steps,
            "source_citations": response.source_citations,
            "model_used": response.model_used,
            "retrieval_metrics": [asdict(metric) for metric in response.retrieval_metrics],
            "context_items": [
                {
                    "source": item.source,
                    "confidence": item.confidence,
                    "source_type": item.source_type,
                    "text": item.text[:500],
                }
                for item in response.context_items
            ],
        }
        return json.dumps(data, indent=2)
