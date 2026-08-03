# JusticeCompass Knowledge Base

> **STATUS: EMPTY SKELETON (Stage 1).** No scraper has been run. Every `.jsonl`
> file described below is planned, not present. This README is regenerated
> automatically by `src/kb_writer/kb_builder.py` on each build — do not hand-edit
> it once Stage 2 has run.

**KB version:** 0.1.0 · **Schema version:** 1.0.0 · **Build date:** *(not yet built)*

---

## What this is

A structured, self-contained dataset of Indian law across five domains, built as
retrieval substrate for an AI legal assistant. This folder is designed to be
zipped and handed to someone on its own — you do not need the scraper code in
`src/` to read or use it.

| Domain | Scope |
|---|---|
| `criminal_law` | Harassment, assault, sexual offences, cybercrime; BNS/BNSS/BSA + archived IPC/CrPC/Evidence Act |
| `consumer_protection` | Consumer Protection Act 2019, defective goods, deficient services, redressal forums |
| `family_law` | Marriage, divorce, maintenance, custody, domestic violence |
| `tenancy_property` | Eviction, rent control (state-wise), transfer of property |
| `constitutional_law` | Fundamental rights, writs, directive principles |

## Layout

```
knowledge_base/
├── README.md                  # this file (auto-generated)
├── manifest.json              # build date, KB version, per-domain counts
├── statutes/<domain>/         # *.jsonl + metadata.json
├── caselaw/<domain>/          # cases.jsonl + metadata.json
├── crossreference/            # ipc_to_bns_mapping.jsonl
└── embeddings_ready/          # chunks.jsonl — load this into the vector DB
```

Every domain folder is independently browsable: it carries its own
`metadata.json` recording source name, source URL, licence status, last-updated
date and document count.

## Format

All documents are **JSON Lines** (`.jsonl`) — one JSON object per line, UTF-8, no
custom parsing required:

```python
import pandas as pd
df = pd.read_json("statutes/criminal_law/bns_sections.jsonl", lines=True)
```

### Document types

**`statute_section`** — one section of an Act, or one Article of the Constitution.
Key fields: `act_name`, `act_short_name`, `section_number`, `section_title`,
`text`, `domains[]`, `regime`, `statute_family`, `jurisdiction`/`state`,
`effective_from`/`effective_until`, `corresponding_new_sections[]`,
`provenance.source_url`, `license`.

**`case`** — one judgment, stored as **citation + short summary only**.
Key fields: `title`, `neutral_citation`, `reporter_citations[]`, `court_level`,
`court_name`, `date_decided`, `domains[]`, `summary` (≤1200 chars), `outcome`,
`ratio_decidendi`, `obiter_dicta`, `statutes_cited[]`, `provenance.source_url`,
`license`.

> `ratio_decidendi` and `obiter_dicta` ship **empty by design**. They are filled
> by a separate downstream classification step, never scraped. Check
> `classification_status` (`pending` / `complete`) before relying on them.

The authoritative field-by-field definition is `src/schema/models.py` in the
pipeline repo.

### The old/new criminal regime

The IPC, CrPC and Evidence Act were replaced by the BNS, BNSS and BSA with effect
from **1 July 2024**. The repealed sections are **retained, not deleted** — decades
of case law cite the old numbering, so a lookup for "IPC 498A" must still resolve.

Filter on `regime`:

- `current` — law in force today
- `archived` — repealed, retained for historical case-law lookup
- `unaffected` — outside the 2023 criminal overhaul

`crossreference/ipc_to_bns_mapping.jsonl` maps old to new. **Read the
`relationship` field before substituting** — mappings are not all 1:1
(`one_to_one`, `merged`, `split`, `substantively_changed`, `no_equivalent`,
`new_provision`). The convenience flag `is_one_to_one` is true only for a clean
renumbering.

## Sources and licences

*(This table is regenerated per build from the sources actually used. It is empty
until Stage 2 runs.)*

| Source | Documents | Licence | Verified |
|---|---|---|---|
| — | — | — | — |

Licence posture for this dataset:

- **Statutory text** is stored in full. §52(1)(q) of the Copyright Act, 1957
  permits reproduction of any Act of a legislature.
- **Judgments** are stored as citation + short summary only. §52(1)(q)(iv) would
  likely permit more for official court text, but this dataset deliberately stays
  stricter.
- **Publisher headnotes, editorial summaries and copy-edited reports are never
  ingested** (*Eastern Book Company v. D.B. Modak*, (2008) 1 SCC 1).
- Bulk research datasets are excluded until their licences are individually
  verified. See `config.yaml` in the pipeline repo.

## How to regenerate

From the pipeline repo root:

```bash
pip install -r requirements.txt
python build_kb.py --all            # dry run — prints the plan, executes nothing
python build_kb.py --run --all      # actually build
python build_kb.py --run --domain criminal_law
python build_kb.py --run --resume   # continue an interrupted build
```

---

## Disclaimer

This is a **data pipeline output for an AI legal assistant, not legal advice**.
Statutory text and case summaries here may be incomplete, out of date, or
incorrectly extracted. Nothing in this dataset creates a lawyer-client
relationship. Verify against the official source URL recorded on every document
before relying on it, and consult a qualified advocate for any actual legal
matter.
