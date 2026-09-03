# JusticeCompass AI Implementation

## Product boundary

JusticeCompass is a legal-information guide. It can identify a possible legal concern, explain source-backed law, suggest preparation steps, and refer the user to qualified help. It must not declare that a claim is legally valid, act as a lawyer, or guarantee a court result.

## Assessment flow

1. Collect the question, location, important dates, and optional case type.
2. Classify the likely legal domain.
3. Retrieve current primary sources and relevant decisions.
4. Report applicable law, uncertainty, missing facts, evidence to preserve, possible forums, and deadlines only when sourced.
5. Provide a historical outcome estimate only for a supported case type and only when the comparable sample is large enough.
6. Log the source versions and model version used for the response.

## Outcome estimates

The initial implementation supports bail records only. The value is an observed rate among comparable records, not an individual's chance of winning. It must show the denominator, matching filters, date range, jurisdiction, confidence interval, and limitations. It must return `insufficient_data` instead of estimating when the cohort is too small.

Do not use the retrieval confidence score as an outcome probability. Retrieval confidence measures source relevance and quality.

## Knowledge-base acceptance checklist

Every statute, rule, judgment, form, and resource should have:

- authoritative source URL and source type
- jurisdiction, court, legal domain, and language
- effective date, repeal date if applicable, and last verification date
- document version and ingestion timestamp
- stable document and section identifiers
- citation text separated from explanatory summaries
- provenance and licensing/usage permission

Archived law must be clearly marked and must not outrank current law when the question is current. Case outcomes require manual review of the extracted result and a link to the source judgment.

## API

Start the service with:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.api:app --reload
```

Send an assessment:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/assess `
  -ContentType "application/json" `
  -Body '{"question":"My landlord is threatening eviction without notice","jurisdiction":"Delhi"}'
```

For the supported historical bail estimate, add `"case_type":"bail"`. Optional filters include `region` and `cited_section`.

Before production, add authentication, rate limiting, audit logging, encrypted storage, deletion controls, abuse monitoring, and human review for high-risk matters such as arrest, violence, child safety, or imminent deadlines.
