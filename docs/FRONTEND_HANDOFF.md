# JusticeCompass Frontend Handoff

## Backend start

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.api:app --reload
```

API documentation is available at `http://127.0.0.1:8000/docs`.

## Main workflow

The first screen should be the assessment form, not a marketing page. Ask for:

- Question or situation description
- Country and state/city
- Important dates
- Optional legal category
- Optional case section or number

Submit with `POST /assess`:

```json
{
  "question": "My landlord is threatening to evict me without notice. What can I do?",
  "jurisdiction": "Delhi, India",
  "date_context": "Notice received 5 days ago",
  "case_type": "tenancy_property",
  "fetch_external_sources": false,
  "fetch_full_judgments": false,
  "include_rag_answer": true
}
```

Set `fetch_external_sources` to `true` only when the user explicitly requests live Indian Kanoon research. Set `fetch_full_judgments` to `true` only after confirmation because it uses metered document calls. `max_full_judgments` accepts 1 to 20 and defaults to 20.

## Response layout

Render these sections in this order:

1. **Concern assessment**: Explain the possible legal concern. Do not call it definitely valid.
2. **Can this be registered?**: Read `structured_answer.registrable_assessment`.
3. **Conditions and forum**: Read `registration_conditions` and `registration_forum`.
4. **Applicable law**: Show `applicable_law` with citations.
5. **Case references**: Show `case_references`, including case number, title, and outcome when present.
6. **Prediction score**: Show `historical_outcome_estimate.estimate` only when non-null. Always show its basis, sample size, bounds, and limitations.
7. **Next steps**: Show `structured_answer.next_steps`, followed by `immediate_steps` and `evidence_to_collect`.
8. **Missing information**: Ask the user for the listed facts.
9. **Sources**: Show `source_citations` and expandable `external_sources` links.
10. **Disclaimer**: Keep the legal-information disclaimer visible near the result.

## Required buttons and controls

- `Assess concern`: submits the form.
- `Add details`: expands dates, parties, location, documents, and requested remedy.
- `Search live judgments`: opt-in toggle; show a cost warning before enabling.
- `Fetch full judgments`: separate opt-in control; show the maximum document count and estimated cost.
- `View source`: opens the source URL in a new tab.
- `Copy summary`: copies the structured result without API keys or private notes.
- `Start new assessment`: clears the current result.
- `Contact legal aid`: opens the relevant resource link when available.

Do not label a historical rate as “your chance of winning.” Use “historical favorable-outcome rate among comparable judgments.”

## UI states

Implement loading, validation error, API error, no-source result, insufficient-data prediction, successful result, and live-source cost confirmation states. Disable submit while loading and preserve the user's question when an error occurs.

## API contract notes

- `GET /health` returns service status, configured provider/model, and boolean key status. It never returns secrets.
- `POST /assess` returns a `request_id` for support/debugging.
- `include_rag_answer: false` is useful for low-cost triage or API smoke tests.
- Prediction data is separate from retrieval confidence. Never convert `confidence_score` into a prediction percentage.
- Treat `external_sources[].source_url` as an external link and show Indian Kanoon attribution where live data is displayed.

## Frontend acceptance checks

- The form can submit a question and render a complete response.
- Empty or short questions show validation without a network request.
- The result clearly separates registration guidance, law, cases, prediction, and next steps.
- A null prediction is displayed as “Insufficient comparable outcome data,” not as zero percent.
- Live source fetching is visibly opt-in and shows case IDs and links.
- API failures are readable and do not erase the entered question.
- The layout works on mobile and desktop without hiding the primary action.
