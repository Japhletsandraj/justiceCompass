# JusticeCompass — Legal Knowledge Base Pipeline

A data pipeline that builds a structured, schema-validated knowledge base of
Indian law across five domains, for use as retrieval substrate in an AI legal
assistant.

> **This repository is a data pipeline, not legal advice.** It produces a dataset.
> Nothing it outputs is a substitute for a qualified advocate, and nothing here
> creates a lawyer-client relationship.

## Domains

1. **Criminal law** — harassment, assault, sexual offences, cybercrime
2. **Consumer protection** — Consumer Protection Act 2019
3. **Family law / domestic violence** — marriage, divorce, maintenance, custody, PWDVA
4. **Tenancy & property** — eviction, state rent control, transfer of property
5. **Constitutional law** — fundamental rights, writs

## The deliverable

The dataset itself lives in **[`knowledge_base/`](knowledge_base/README.md)** — a
self-contained folder you can zip and hand to someone without any of this
pipeline's code. Read
**[`knowledge_base/README.md`](knowledge_base/README.md)** for the schema, sources,
licences and layout of the dataset.

`data/raw/` holds untouched scraper output. It is gitignored, intermediate, and
**not** part of the deliverable.

## Repo layout

```
justicecompass-kb/
├── build_kb.py                  # orchestrator CLI (dry-run by default)
├── config.yaml                  # sources, domains, rate limits, licence posture
├── requirements.txt
├── README.md                    # this file
├── src/
│   ├── scrapers/                # statute_scraper.py, caselaw_scraper.py
│   ├── schema/models.py         # Pydantic schema — the validation boundary
│   ├── crossref/                # IPC/CrPC/Evidence -> BNS/BNSS/BSA lookup table
│   ├── validation/              # dedup, broken links, encoding checks
│   ├── kb_writer/               # writes knowledge_base/, manifest.json, README.md
│   └── utils/                   # rate_limiter.py, logger.py
├── data/raw/                    # gitignored intermediates
├── logs/
└── knowledge_base/              # THE DELIVERABLE — committed
```

## Usage

```bash
pip install -r requirements.txt

python build_kb.py --all                  # dry run: prints the plan, executes nothing
python build_kb.py --run --all            # actually build
python build_kb.py --run --domain criminal_law
python build_kb.py --run --step statutes
python build_kb.py --run --resume         # continue an interrupted build
```

`build_kb.py` is **dry-run by default**. Without an explicit `--run` flag it
prints the planned steps and exits without making a single network request.

## Design decisions worth knowing

**Repealed law is archived, not deleted.** The IPC, CrPC and Evidence Act were
replaced by the BNS, BNSS and BSA on 1 July 2024, but decades of case law cite the
old section numbers. Repealed sections stay in the KB tagged `regime: archived`,
with a cross-reference table forward-pointing to the new numbering. Those mappings
are **not all 1:1** — sections were merged, split, reworded and dropped — so the
mapping table flags the relationship rather than implying clean substitution.

**Copyright posture is enforced in the schema, not left to the scrapers.**
Statutory text is stored in full (§52(1)(q), Copyright Act 1957). Judgments are
stored as citation + short summary only, hard-capped at 1200 characters, even
though §52(1)(q)(iv) would likely permit more for official court text. Publisher
headnotes and copy-edited reports are never ingested (*EBC v. D.B. Modak*). A
document that violates any of this fails validation and never reaches
`knowledge_base/`.

**No source is trusted because of where it is hosted.** Every source in
`config.yaml` carries a licence block with `verified_by_human`. Research datasets
on GitHub and HuggingFace are all `enabled: false` until someone reads the actual
terms and records what they found.

**Scrapers are polite by construction.** robots.txt is checked before every
request with no override flag, rate limits are per-host and configurable, and one
failing source is logged and skipped rather than killing the run.

---

# Build progress

## 2026-08-03, 16:31 IST — Stage 1, part 1 of 2

**Done — schema, config and repo skeleton.** Nothing has been executed against the
network; no scraper exists yet.

### Committed in this pass

| File | Status |
|---|---|
| `src/schema/models.py` | ✅ Complete — Pydantic v2 schema, validated |
| `config.yaml` | ✅ Complete — 22 sources, licence posture, rate limits |
| `knowledge_base/` skeleton | ✅ 16 folders + placeholder `README.md` / `manifest.json` |
| `.gitignore` | ✅ Updated — ignores `data/raw`, keeps `knowledge_base/` |
| `src/` package skeleton | ✅ `__init__.py` in place for all six subpackages |
| `readme.md` | ✅ This file |

**`src/schema/models.py`** — the two requested document types plus four supporting
models:

- `StatuteSection` — act name/short name/number, section number, title, text,
  illustrations/explanations/provisos, `domains[]`, `regime`
  (current/archived/unaffected), `statute_family` (ipc/crpc/evidence_act/bns/bnss/
  bsa/constitution/other), `jurisdiction` + `state`, effective dates, forward and
  backward regime links, `provenance`, `license`
- `CaseDocument` — title, neutral + reporter citations, `court_level`, court name,
  bench, judges, date, `domains[]`, `summary` (capped at 1200 chars), `outcome`,
  `ratio_decidendi` / `obiter_dicta` as **empty placeholders** with a
  `classification_status` flag, `statutes_cited[]`, `provenance`, `license`
- `CrossReferenceEntry`, `Chunk`, `DomainMetadata`, `BuildManifest` — supporting
  models the KB folder structure requires

Ten guard rails were tested and all reject bad data: archived section without a
named successor; statute text under a licence that forbids full-text storage;
state law missing its state slug; case with no citation of any kind; summary over
the cap; full judgment text under a restricted licence; ratio/obiter populated
while classification is still `pending`; unverified licence claiming full-text
rights; `one_to_one` mapping with two targets; `no_equivalent` mapping with a
target. All five models round-trip through `.jsonl` without loss.

**`config.yaml`** — 15 statute sources (India Code: BNS/BNSS/BSA, archived IPC/
CrPC/Evidence Act, IT Act, CPA 2019, HMA, SMA, Muslim personal law statutes,
PWDVA, TPA, Model Tenancy Act, Constitution), 8 state rent control Acts (4 enabled
for phase 1, 4 deferred), 3 official case-law sources (eSCR, eCourts High Courts,
NCDRC), and 4 bulk research datasets.

> ⚠️ **All 4 research datasets — NyayaAnumana, ILDC, IndicLegalQA,
> IndianBailJudgments — are `enabled: false` with `usage: unverified`.** No
> network calls were made while writing the config, so no licence text has been
> read. Each entry records what to check and why, and the licence gate refuses to
> fetch them until both flags are flipped deliberately. **This is the main thing
> to review before Stage 2.**
>
> Deep URLs are likewise marked `url_verified: false` — scrapers resolve them by
> search at runtime rather than relying on guessed handle IDs.

`indiankanoon.org`, `scconline.com`, `manupatra.com` and `casemine.com` are in
`copyright_policy.blocked_hosts` with reasons recorded.

### Still to do in Stage 1

| Item | Status |
|---|---|
| `src/scrapers/statute_scraper.py` | ⬜ Not started |
| `src/scrapers/caselaw_scraper.py` | ⬜ Not started |
| `src/crossref/ipc_bns_mapping.py` | ⬜ Not started |
| `src/validation/quality_checks.py` | ⬜ Not started |
| `src/kb_writer/kb_builder.py` | ⬜ Not started |
| `src/utils/rate_limiter.py`, `logger.py` | ⬜ Not started |
| `build_kb.py` | ⬜ Not started |
| `requirements.txt` | ⬜ Not started |

### Stage 2 — not started

Executing `build_kb.py --run --all` to populate `knowledge_base/`. Blocked until
Stage 1 is complete, reviewed and pushed, and triggered explicitly.
