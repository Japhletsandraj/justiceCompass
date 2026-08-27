# Indian Legal Knowledge Base

Generated 2026-08-05 by `scripts/kb_builder.py`. All counts below are computed from the files in this directory.

## What this contains

- **21 statute documents** / **3,282 sections** across 5 domains
- **1,200 case law records** (criminal law only)
- **270 crossreference entries** (IPC/CrPC/Evidence Act to BNS/BNSS/BSA)
- **4,746 embedding-ready records**

## Coverage by domain

| Domain | Statute docs | Sections | Case law | Jurisdictions |
|---|---:|---:|---:|---|
| constitutional_law | 1 | 454 | **none** | India (Union) |
| criminal_law | 5 | 2,159 | 1,200 | India (Union) |
| consumer_protection | 2 | 142 | **none** | India (Union) |
| family_law | 3 | 130 | **none** | India (Union) |
| tenancy_property | 10 | 397 | **none** | Delhi, India (Union), Maharashtra, Tamil Nadu, West Bengal |

### Case law coverage is criminal law only

This is the most important limitation of this knowledge base. Case law exists for **one of five domains**:

- **criminal_law** — has both statutes and case law (1,200 bail judgments).
- **constitutional_law, consumer_protection, family_law, tenancy_property** — **statutes only. There is no case law for these four domains.**

The case law that does exist is also narrow: it is entirely **bail decisions**, not criminal law judgments generally. It does not cover convictions, sentencing, appeals on merits, or trial procedure. Any claim of general criminal case law coverage would be wrong.

## Directory layout

```
knowledge_base/
  statutes/<domain>/<act>.json      one record per section
  caselaw/criminal_law/             bail judgments
  crossreference/                   IPC/CrPC/IEA -> BNS/BNSS/BSA
  vector_db/legacy_embeddings/*.jsonl  legacy {id, text, metadata} records
  manifest.json                     counts, per-document provenance
```

## Sources and licences

### Constitution of India dataset (Kaggle: rushikeshdarge/constitution-of-india)

- **URL**: https://www.kaggle.com/datasets/rushikeshdarge/constitution-of-india
- **Provenance note**: Identified from scripts/data_loader.py, which downloads this dataset via kagglehub.
- **Licence**: Licence not recorded at acquisition and not stated in the downloaded files. The underlying text is the Constitution of India, a Government of India enactment.
- **Licence verified**: **no**

### India Code (indiacode.nic.in), Government of India

- **URL**: _not recorded_
- **Provenance note**: Acquisition URLs were not captured in data/raw. Documents are indiacode.nic.in bare-act PDFs, identifiable from their own title blocks.
- **Licence**: Government of India legislative material. Section 52(1)(q) of the Copyright Act, 1957 permits reproduction of any enactment. No explicit licence file accompanied the source PDFs.
- **Licence verified**: **no**

### IndianBailJudgments-1200 (Sneha Deshmukh)

- **URL**: https://huggingface.co/datasets/SnehaDeshmukh/IndianBailJudgments-1200
- **Provenance note**: Identified from scripts/data_loader.py, which loads this dataset from the Hugging Face Hub.
- **Licence**: CC-BY-4.0. Requires attribution to the dataset author when redistributed or used.
- **Licence verified**: yes

### Tamil Nadu Government Gazette, Government of Tamil Nadu

- **URL**: _not recorded_
- **Provenance note**: Gazette issues (Extraordinary) as published by the Director of Stationery and Printing, Chennai. Acquisition URLs not captured in data/raw.
- **Licence**: State Government gazette material. Section 52(1)(q) of the Copyright Act, 1957 permits reproduction of any enactment. No explicit licence file accompanied the source PDFs.
- **Licence verified**: **no**

Only the IndianBailJudgments-1200 licence (CC-BY-4.0) is stated by the source itself. The statute licences are a reading of Indian copyright law, not a licence grant found in the files; the acquisition URLs for the statute PDFs were not recorded and have not been reconstructed.

**Attribution required**: case law records are CC-BY-4.0 and must be attributed to the IndianBailJudgments-1200 dataset author when redistributed.

## Crossreference caveat

- Verification status: `unverified_against_official_concordance`
- Compiled from domain knowledge and not checked against an official government concordance. Section numbers are machine-verified to exist in the extracted statute text; the correctness of each pairing is not.
- Citation-weighted coverage of IPC sections appearing in the case law: **94.7%**
- 90 IPC sections cited in the case law are **not yet mapped** and need manual completion.

## Known gaps and defects

**Documents that failed extraction and contribute nothing:**

- `tenancy_property/rent_control/Karnataka_Rent_Act_1999.pdf` (The Karnataka Rent Act, 1999) — PDF has no usable text layer: 79% of extracted content is (cid:N) glyph codes with no ToUnicode mapping. Needs OCR or a re-download of a text-bearing copy.

**Documents with partial encoding damage** (affected sections carry a `data_quality_flag`):

- `statutes/tenancy_property/rent_control__West_Bengal_Rent_Act.json` — 7 of 31 sections contain undecodable glyphs
- `statutes/tenancy_property/rent_control__tamilnadu__tnrrrlt_rules_2019.json` — 1 of 1 sections contain undecodable glyphs

**Documents whose filename does not describe their contents:**

- `statutes/criminal_law/bna_2023.json` — File is named bna_2023.pdf; document is the Bharatiya Sakshya Adhiniyam (BSA), Act 47 of 2023.
- `statutes/tenancy_property/rent_control__tamilnadu__notification_registration_extension_2019.json` — Filename says 'notification'; the document is Act 22 of 2019, an amending Act. The same gazette issue also carries Act 21 of 2019 (fishermen welfare), which is unrelated and not extracted.
- `statutes/tenancy_property/rent_control__tamilnadu__notification_rent_court_2019.json` — Filename says 'notification'; the document is the principal TNRRRLT Rules, 2019 (G.O. Ms. No. 36, 22 February 2019).
- `statutes/tenancy_property/rent_control__tamilnadu__tnrrrlt_act_2017.json` — Gazette issue containing Acts 36-47 of 2017; only Act 42 of 2017 (the rent statute) is extracted.
- `statutes/tenancy_property/rent_control__tamilnadu__tnrrrlt_amendment_act_2018.json` — Gazette issue containing Acts 35-40 of 2018; only Act 39 of 2018 (the rent amendment) is extracted.
- `statutes/tenancy_property/rent_control__tamilnadu__tnrrrlt_rules_2019.json` — Filename says 'rules'; the document is a one-page amendment to those Rules (G.O. Ms. No. 103, 11 July 2019).

**Case law duplicates**: 15 groups (31 records) share a title and date. Duplicates are flagged with possible_duplicate_of and retained, not deleted -- they may be separate proceedings sharing a cause title and date.

**Not covered:**

- Case law for constitutional, consumer, family and tenancy law — none.
- Family law beyond the three Acts here (no Hindu Succession Act, Hindu Adoption and Maintenance Act, Indian Divorce Act, Muslim Personal Law, Guardians and Wards Act).
- Rent control for states beyond those listed above; Karnataka was collected but could not be extracted.
- The Indian Evidence Act 1872 itself is **not** in this corpus, only its successor the BSA 2023. IEA→BSA source sections are therefore unverified against primary text.
- Schedules, forms and the Statement of Objects and Reasons are excluded; extraction stops at the end of the operative sections.
- Tamil-script text in the Tamil Nadu gazettes is set in a legacy non-Unicode font and is not recoverable. English text is unaffected.
