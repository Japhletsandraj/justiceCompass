# JusticeCompass Evaluation Protocol

## Evaluation Design

We evaluate the proposed legal retrieval and answer-generation system using a held-out benchmark that is not used for prompt tuning, retrieval threshold calibration, or model selection. The evaluation is designed to separately assess four aspects of the system: (1) retrieval quality, (2) answer quality and grounding, (3) historical outcome estimation, and (4) operational reliability. This separation is important in a legal setting, where source relevance, answer correctness, and outcome prediction are distinct tasks with different failure modes.

The evaluation dataset consists of legal questions spanning multiple legal domains and jurisdictions. Each question is paired with relevant legal authorities, required factual elements, and, where applicable, expected procedural next steps. For historical outcome estimation, each case or outcome record includes a reviewed label such as allowed, dismissed, rejected, granted, or settled. Where possible, we use temporal splits so that training and selection are performed on earlier cases while evaluation is performed on later cases, better reflecting real-world deployment conditions.

We do not report retrieval confidence as a legal-success probability. Retrieval confidence measures source relevance and quality, whereas outcome estimation is a separate statistical task and must be reported as a historical pattern rather than a guarantee about an individual case. The system also abstains when the available comparable data are insufficient, returning `insufficient_data` instead of fabricating a probability.

---

## Retrieval Evaluation

Retrieval quality is measured using standard ranked-information retrieval metrics over the top-k results.

- Precision@K: proportion of the top-k documents that are relevant.
- Recall@K: proportion of all known relevant documents retrieved in the top-k results.
- Hit Rate@K: percentage of questions with at least one relevant document in the top-k results.
- MRR (Mean Reciprocal Rank): average reciprocal rank of the first relevant document.
- nDCG@K: ranking-quality metric that accounts for graded relevance labels, where a document may be scored as irrelevant, related, or directly applicable.

These metrics provide a balanced assessment of both retrieval usefulness and ranking quality. In a legal retrieval system, it is not sufficient to retrieve any relevant document; the most authoritative and directly applicable sources must also be ranked near the top.

### Retrieval Metrics Summary

| Metric | Description |
|---|---|
| Precision@K | Fraction of retrieved top-k documents that are relevant |
| Recall@K | Fraction of all relevant documents that appear in the top-k results |
| Hit Rate@K | Percentage of questions with at least one relevant result in top-k |
| MRR | Reciprocal rank of the first relevant result |
| nDCG@K | Ranking quality when graded relevance is available |

---

## Answer Quality and Grounding Evaluation

Answer quality is assessed using expert review and source-grounding checks. The generated response is evaluated not only for correctness, but also for whether its claims are supported by the retrieved legal context and whether the answer is usable for a real legal user.

We evaluate the following dimensions:

- Citation precision: proportion of citations in the answer that are supported by the retrieved source text.
- Citation recall: proportion of required authoritative sources that are cited.
- Citation completeness: proportion of material legal claims that have a supporting source.
- Groundedness / faithfulness: proportion of factual and legal claims that can be verified from the retrieved context.
- Answer relevance: whether the answer addresses the user’s question without irrelevant or unsupported discussion.
- Actionability: whether the response provides usable next steps, documents to collect, likely forum, missing facts, or deadline warnings where supported.
- Legal safety: whether the answer avoids fabricated citations, unsupported guarantees, unauthorized legal advice, and unsupported predictions.
- Structured-output validity: proportion of responses that parse successfully into the required schema without manual repair.

Expert reviewers score relevance and actionability on a 1–5 scale, where 1 indicates unsafe or incorrect output and 5 indicates accurate, grounded, and complete assistance for the supplied facts. This is particularly important in legal systems, where well-formed but unsupported reasoning can be misleading even when it appears fluent.

---

## Historical Outcome Estimation Evaluation

Historical outcome estimation is evaluated independently from retrieval and answer generation. We do not combine outcome prediction with retrieval confidence into a single user-facing score, because legal outcome estimation is a separate empirical task with different uncertainty characteristics.

For each legal category, we evaluate performance using metrics appropriate to the output type and the class distribution. Standard metrics include:

- Accuracy: fraction of predictions that match the reviewed outcome label.
- Precision, Recall, and F1: computed per outcome class, especially for imbalanced classes such as allowed or rejected outcomes.
- Macro-F1 and micro-F1: macro-F1 is particularly useful when class imbalance is present.
- ROC-AUC or PR-AUC: used when the model produces a continuous score; PR-AUC is often more informative for rare favorable outcomes.
- Brier score: mean squared error between predicted probability and observed binary outcome.
- Calibration error: comparison between predicted probability bins and observed favorable rates, reported using Expected Calibration Error (ECE) and a reliability diagram.
- Coverage / abstention rate: percentage of questions for which the model provides an estimate instead of returning `insufficient_data`.

We also report subgroup and stability checks by jurisdiction, domain, case type, year or time period, outcome class, and data completeness. Because the available case corpus is not uniform across legal domains, results are not collapsed into a single aggregate legal-success score. Instead, we report performance by legal category and jurisdiction where appropriate.

This is especially important because a model should not display a percentage to users until the score has been verified on a held-out evaluation set and checked for calibration.

---

## Operational Evaluation

Operational metrics assess system usability and deployment readiness. These include:

- End-to-end latency: p50, p95, and p99 latency in milliseconds.
- Retrieval latency: p50 and p95 latency for source retrieval.
- LLM latency: p50 and p95 latency for generation.
- Error rate: failed requests divided by total requests.
- Timeout rate.
- Cache hit rate.
- Indian Kanoon API calls per assessment.
- Average API cost per live assessment.
- Number of retrieved documents per request.
- Token usage per LLM request.

These metrics are important because a legal system may be accurate but unusable if it is slow, expensive, or unreliable in production settings.

---

## Paper-Ready Results Wording

A suitable description for the manuscript is as follows:

> JusticeCompass was evaluated using a held-out set of legal questions spanning multiple legal domains and jurisdictions. Retrieval performance was measured using Precision@K, Recall@K, Hit Rate@K, MRR, and nDCG@K. Generated responses were reviewed for citation precision, citation completeness, groundedness, answer relevance, actionability, legal safety, and structured-output validity. Historical outcome estimation was evaluated separately using accuracy, macro-F1, Brier score, calibration error, and coverage. Because the available case corpus is not uniform across legal domains, results were reported by case type and jurisdiction rather than as a single aggregate legal-success score. The system abstained when the comparable outcome sample was insufficient.

This wording is appropriate for an IEEE research paper because it emphasizes separation between retrieval, reasoning, outcome estimation, and safety without overstating the evidence.

---

## Reporting Standards for the Final Paper

The final paper should not claim measured values unless the evaluation has actually been executed on a held-out set. Each reported result table should include the following metadata:

- number of evaluation questions,
- number of reviewers,
- reviewer agreement,
- corpus date range,
- jurisdictions included,
- legal domains covered,
- model name,
- prompt version,
- retrieval K value,
- confidence threshold,
- and any abstention rule.

This ensures transparency and allows readers to interpret the results in context.

---

## Recommended Evaluation Table Structure

| Component | Evaluation Unit | Metrics |
|---|---|---|
| Retrieval | Question-level retrieval ranking | Precision@K, Recall@K, Hit Rate@K, MRR, nDCG@K |
| Answer generation | Expert-reviewed responses | Citation precision, citation recall, groundedness, relevance, actionability, legal safety |
| Historical outcome estimation | Case-level outcomes | Accuracy, macro-F1, PR-AUC / ROC-AUC, Brier score, ECE, coverage |
| System reliability | Request-level pipeline | Latency, error rate, timeout rate, API cost, token usage |

This compact structure is preferable to a large single evaluation matrix in an IEEE manuscript, while still preserving methodological rigor.

---

## Final Note

The evaluation framework described here should be adopted as a research-quality protocol, but the exact reported values must be generated from the held-out benchmark before publication. This ensures that the paper remains technically correct, ethically cautious, and aligned with legal AI evaluation standards.
