4/8/2026
collected raw data.

5/8/2026
preprocessing and building knowledge base

result:
## Knowledge Base — Build Status

**Last built:** _(fill in date)_
**Pipeline scripts:** `pdf_extractor.py`, `gazette_extractor.py`, `constitution_adapter.py`, `caselaw_adapter.py`, `ipc_bns_mapping.py`, `quality_checks.py`, `kb_builder.py`

### Coverage Summary

| Domain | Statute docs | Sections | Case law |
| --- | --- | --- | --- |
| Constitutional law | 1 | 454 | 0 |
| Criminal law | 5 | 2,159 | 1,200 |
| Consumer protection | 2 | 142 | 0 |
| Family law | 3 | 130 | 0 |
| Tenancy/property | 10 | 397 | 0 |
| **Total** | **21** | **3,282** | **1,200** |

Plus **270** cross-reference entries (IPC/CrPC/Evidence Act → BNS/BNSS/BSA) and **4,746** embedding-ready records.

Section counts verified against real acts where checkable: BNS 358, BNSS 531, BSA 170, CPA 2019 107, DV Act 37, HMA 37.

---

### What's NOT Covered (by design, stated explicitly)

- **Case law exists only for criminal law**, and only bail decisions — no convictions, sentencing, appeals on merits, or trial procedure. No case law at all for constitutional, consumer, family, or tenancy domains yet.
- **Family law** covers only Hindu Marriage Act, Special Marriage Act, and DV Act 2005. Not included: Hindu Succession Act, Hindu Adoption & Maintenance Act, Indian Divorce Act, Muslim personal law, Guardians and Wards Act.
- **Tenancy** covers 4 states (Delhi, Maharashtra, West Bengal, Tamil Nadu) + the central Transfer of Property Act. Karnataka is a documented failure (see below).
- **Indian Evidence Act, 1872** is not in the corpus — only its successor, BSA. Evidence Act → BSA crossref entries can't be validated against primary source text as a result.
- Schedules, forms, and Statements of Objects and Reasons are excluded by design.

---

### Known Issues & Manual Review Items

**Hard failure:**
- **Karnataka Rent Act** — source PDF is 79% `(cid:N)` glyph codes with no ToUnicode map; not extractable without OCR or a different source copy. Tenancy coverage is effectively 4 states, not 5.

**Needs review (text intact, structure is a heuristic guess):**
- **Constitution**: 194 of 454 articles (43%) have heuristic title/text boundary splits — the source CSV runs heading and body together on one line. No text is lost.
- **IPC**: ~77 of 583 section titles (13%) mangled by marginal-note typography artifacts.
- **West Bengal**: ~68% of section titles similarly mangled; 7 of 31 sections have isolated undecodable glyphs (0.1–2% of section text).
- **6 sections have empty text** (4 IPC, 2 TPA) — confirmed genuine repealed stubs, excluded from embeddings.
- **Tamil-script text** is in a legacy non-Unicode font and is not recoverable. English text is unaffected.
- **15 duplicate case groups** (31 records) in case law — flagged with `possible_duplicate_of`, retained rather than deleted, since they may represent separate proceedings.

**Cross-reference table:**
- Status: `unverified_against_official_concordance` — compiled from domain knowledge, not sourced from an official government concordance.
- What *is* machine-verified: every source and target section number in the table exists in the extracted statute text (100% pass).
- Citation-weighted coverage: 94.7% (of citations appearing in the case-law corpus).
- **90 IPC sections cited in case law remain unmapped** in the crossref table — open item.

---

### Corrections Made During Build

- `bna_2023.pdf` was mislabeled — it is actually the **BSA** (Bharatiya Sakshya Adhiniyam, Act 47 of 2023). No source was missing; only the filename was wrong.
- Tamil Nadu source files were **whole gazette issues**, not single acts. `tnrrrlt_act_2017.pdf` contained Acts 36–47 of 2017 bundled together, with the actual tenancy statute being only Act 42. A gazette segmenter (`gazette_extractor.py`) was built to correctly isolate the relevant act. 5 of 6 original TN filenames did not describe their actual contents; corrections are recorded per-document in this KB's manifest.

---

### Data Integrity Notes

- No data was fabricated or backfilled to inflate apparent coverage.
- Where a source URL wasn't captured at acquisition time, provenance is recorded as `"URL not captured at acquisition"` rather than invented.
- Raw filenames were preserved and content-tagged rather than renamed, to keep an honest link back to original sources.