"""
Assemble knowledge_base/ from validated data/processed/ output.

Layout produced:

    knowledge_base/
      statutes/<domain>/<document>.json
      caselaw/criminal_law/indianbail_1200.json
      crossreference/ipc_bns_mapping.json
    vector_db/legacy_embeddings/{statutes,caselaw,crossreference}.jsonl
      manifest.json
      README.md

Counts, per-source attribution and license text in the manifest and README are
computed from the files actually written -- nothing is hardcoded, and coverage
is not rounded up. Documents that failed extraction are recorded as failures
rather than omitted, so the manifest describes the real state of the corpus.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
from collections import Counter, defaultdict
from datetime import date

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROCESSED = os.path.join(REPO, "data", "processed")
KB = os.path.join(REPO, "knowledge_base")

DOMAINS = [
    "constitutional_law", "criminal_law", "consumer_protection",
    "family_law", "tenancy_property",
]

# Per-source provenance. Acquisition URLs were not recorded for the statute
# PDFs, and inventing them would be false provenance -- so the URL field is
# null and the note says how the file was obtained instead.
SOURCES = {
    "indiacode": {
        "name": "India Code (indiacode.nic.in), Government of India",
        "url": None,
        "url_note": "Acquisition URLs were not captured in data/raw. Documents "
                    "are indiacode.nic.in bare-act PDFs, identifiable from "
                    "their own title blocks.",
        "license": "Government of India legislative material. Section 52(1)(q) "
                   "of the Copyright Act, 1957 permits reproduction of any "
                   "enactment. No explicit licence file accompanied the source "
                   "PDFs.",
        "license_verified": False,
    },
    "tn_gazette": {
        "name": "Tamil Nadu Government Gazette, Government of Tamil Nadu",
        "url": None,
        "url_note": "Gazette issues (Extraordinary) as published by the "
                    "Director of Stationery and Printing, Chennai. Acquisition "
                    "URLs not captured in data/raw.",
        "license": "State Government gazette material. Section 52(1)(q) of the "
                   "Copyright Act, 1957 permits reproduction of any enactment. "
                   "No explicit licence file accompanied the source PDFs.",
        "license_verified": False,
    },
    "constitution_csv": {
        "name": "Constitution of India dataset (Kaggle: "
                "rushikeshdarge/constitution-of-india)",
        "url": "https://www.kaggle.com/datasets/rushikeshdarge/constitution-of-india",
        "url_note": "Identified from scripts/data_loader.py, which downloads "
                    "this dataset via kagglehub.",
        "license": "Licence not recorded at acquisition and not stated in the "
                   "downloaded files. The underlying text is the Constitution "
                   "of India, a Government of India enactment.",
        "license_verified": False,
    },
    "indianbail": {
        "name": "IndianBailJudgments-1200 (Sneha Deshmukh)",
        "url": "https://huggingface.co/datasets/SnehaDeshmukh/IndianBailJudgments-1200",
        "url_note": "Identified from scripts/data_loader.py, which loads this "
                    "dataset from the Hugging Face Hub.",
        "license": "CC-BY-4.0. Requires attribution to the dataset author when "
                   "redistributed or used.",
        "license_verified": True,
    },
}

FILE_SOURCE = {
    "constitutional_law__constitution.json": "constitution_csv",
}


def source_for(fname: str, records: list[dict]) -> str:
    if fname in FILE_SOURCE:
        return FILE_SOURCE[fname]
    src = (records[0].get("source_file") or "") if records else ""
    return "tn_gazette" if "tamilnadu" in src else "indiacode"


def load(path: str):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def write(path: str, obj) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)


def write_jsonl(path: str, rows) -> int:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    n = 0
    with open(path, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
            n += 1
    return n


CID_RE = re.compile(r"\(cid:\d+\)")


def build() -> dict:
    if os.path.isdir(KB):
        shutil.rmtree(KB)

    quality = {}
    qpath = os.path.join(PROCESSED, "_quality_report.json")
    if os.path.exists(qpath):
        quality = load(qpath)

    extraction = []
    epath = os.path.join(PROCESSED, "statutes", "_extraction_report.json")
    if os.path.exists(epath):
        extraction = load(epath)

    manifest_docs: list[dict] = []
    domain_counts: Counter = Counter()
    domain_docs: Counter = Counter()
    jurisdictions: dict[str, set] = defaultdict(set)
    regime_counts: Counter = Counter()
    embed_statutes: list[dict] = []
    sources_used: set[str] = set()

    src_dir = os.path.join(PROCESSED, "statutes")
    for fname in sorted(os.listdir(src_dir)):
        if not fname.endswith(".json") or fname.startswith("_"):
            continue
        records = load(os.path.join(src_dir, fname))
        if not records:
            continue
        domain = (records[0].get("domain_tags") or ["unknown"])[0]
        source_key = source_for(fname, records)
        sources_used.add(source_key)

        cid_hits = sum(1 for r in records if CID_RE.search(r.get("section_text") or ""))
        for r in records:
            r["source"] = SOURCES[source_key]["name"]
            r["license"] = SOURCES[source_key]["license"]
            if CID_RE.search(r.get("section_text") or ""):
                r["data_quality_flag"] = (
                    "contains unmapped PDF glyph codes; a small number of "
                    "characters could not be decoded from the source PDF"
                )

        out_name = fname.split("__", 1)[1] if "__" in fname else fname
        write(os.path.join(KB, "statutes", domain, out_name), records)

        domain_counts[domain] += len(records)
        domain_docs[domain] += 1
        for r in records:
            if r.get("jurisdiction"):
                jurisdictions[domain].add(r["jurisdiction"])
            regime_counts[r.get("regime_tag") or "unspecified"] += 1

        manifest_docs.append({
            "file": f"statutes/{domain}/{out_name}",
            "act_name": records[0].get("act_name"),
            "domain": domain,
            "jurisdiction": records[0].get("jurisdiction"),
            "regime_tag": records[0].get("regime_tag"),
            "document_type": records[0].get("document_type"),
            "sections": len(records),
            "source": SOURCES[source_key]["name"],
            "source_url": SOURCES[source_key]["url"],
            "license": SOURCES[source_key]["license"],
            "sections_with_encoding_damage": cid_hits,
            "content_note": records[0].get("content_note"),
        })

        for r in records:
            text = (r.get("section_text") or "").strip()
            if not text:
                continue
            label = r.get("section_label") or f"Section {r.get('section_number')}"
            heading = " > ".join(
                x for x in [r.get("part"), r.get("chapter_heading"),
                            r.get("chapter_subheading")] if x
            )
            embed_statutes.append({
                "id": "stat:" + hashlib.sha1(
                    f"{r.get('doc_id')}|{r.get('section_number')}".encode()
                ).hexdigest()[:16],
                "text": f"{r.get('act_name')} — {label}. "
                        f"{r.get('section_title') or ''}\n{text}".strip(),
                "metadata": {
                    "act_name": r.get("act_name"),
                    "section_number": r.get("section_number"),
                    "section_title": r.get("section_title"),
                    "heading_path": heading or None,
                    "domain_tags": r.get("domain_tags"),
                    "jurisdiction": r.get("jurisdiction"),
                    "regime_tag": r.get("regime_tag"),
                    "document_type": r.get("document_type"),
                    "record_type": "statute_section",
                    "source": r.get("source"),
                    "license": r.get("license"),
                    "source_file": r.get("source_file"),
                },
            })

    # ---- caselaw --------------------------------------------------------
    cases = load(os.path.join(PROCESSED, "caselaw", "indianbail_1200.json"))
    sources_used.add("indianbail")

    dup_groups: dict[tuple, list[str]] = defaultdict(list)
    for c in cases:
        dup_groups[(c["title"].lower().strip(), c["date"])].append(c["case_id"])
    dups = {k: v for k, v in dup_groups.items() if len(v) > 1}
    dup_ids = {cid for ids in dups.values() for cid in ids}
    for c in cases:
        if c["case_id"] in dup_ids:
            key = (c["title"].lower().strip(), c["date"])
            others = [i for i in dup_groups[key] if i != c["case_id"]]
            c["possible_duplicate_of"] = others
    write(os.path.join(KB, "caselaw", "criminal_law", "indianbail_1200.json"), cases)

    embed_cases = [{
        "id": f"case:{c['case_id']}",
        "text": f"{c['title']} ({c['court']}, {c['date']}). "
                f"Outcome: {c['outcome']}.\n{c['summary']}".strip(),
        "metadata": {
            "case_id": c["case_id"],
            "title": c["title"],
            "court": c["court"],
            "court_level": c["court_level"],
            "date": c["date"],
            "year": c["year"],
            "outcome": c["outcome"],
            "domain_tags": c["domain_tags"],
            "cited_sections": [
                f"{s['statute']} s.{s['section']}"
                for s in c["cited_sections"] if s.get("section")
            ],
            "record_type": "case",
            "source": SOURCES["indianbail"]["name"],
            "source_url": c["source_url"],
            "license": c["license"],
        },
    } for c in cases]

    # ---- crossreference -------------------------------------------------
    xref = load(os.path.join(PROCESSED, "crossreference", "ipc_bns_mapping.json"))
    write(os.path.join(KB, "crossreference", "ipc_bns_mapping.json"), xref)

    embed_xref = [{
        "id": "xref:" + hashlib.sha1(
            f"{e.get('source_statute')}|{e.get('source_section')}|"
            f"{e.get('target_section')}".encode()).hexdigest()[:16],
        "text": (
            f"{e['source_statute']} section {e['source_section']} corresponds to "
            f"{e['target_statute']} section {e['target_section']}."
            if e.get("source_section") and e.get("target_section")
            else (f"{e['target_statute']} section {e['target_section']} is a new "
                  f"provision with no predecessor."
                  if not e.get("source_section")
                  else f"{e['source_statute']} section {e['source_section']} has "
                       f"no counterpart in the new code.")
        ) + (f" Relation: {e['relation']}. {e['note']}".rstrip()),
        "metadata": {
            "source_statute": e.get("source_statute"),
            "source_section": e.get("source_section"),
            "target_statute": e.get("target_statute"),
            "target_section": e.get("target_section"),
            "relation": e.get("relation"),
            "confidence": e.get("confidence"),
            "record_type": "crossreference",
            "domain_tags": ["criminal_law"],
            "verification_status": xref.get("verification_status"),
        },
    } for e in xref["entries"]]

    n_stat = write_jsonl(os.path.join(KB, "vector_db", "legacy_embeddings", "statutes.jsonl"),
                         embed_statutes)
    n_case = write_jsonl(os.path.join(KB, "vector_db", "legacy_embeddings", "caselaw.jsonl"),
                         embed_cases)
    n_xref = write_jsonl(os.path.join(KB, "vector_db", "legacy_embeddings", "crossreference.jsonl"),
                         embed_xref)

    failures = [
        {"file": d["source_file"], "act_name": d["act_name"],
         "status": d["extraction_status"], "reason": d["reason"]}
        for d in extraction if d.get("extraction_status") == "failed"
    ]

    manifest = {
        "name": "Indian legal knowledge base",
        "generated": date.today().isoformat(),
        "generated_by": "scripts/kb_builder.py",
        "domains": DOMAINS,
        "coverage": {
            d: {
                "statute_documents": domain_docs.get(d, 0),
                "statute_sections": domain_counts.get(d, 0),
                "case_law_documents": len(cases) if d == "criminal_law" else 0,
                "has_case_law": d == "criminal_law",
                "jurisdictions": sorted(jurisdictions.get(d, [])),
            } for d in DOMAINS
        },
        "totals": {
            "statute_documents": sum(domain_docs.values()),
            "statute_sections": sum(domain_counts.values()),
            "cases": len(cases),
            "crossreference_entries": len(xref["entries"]),
            "vector_db_records": n_stat + n_case + n_xref,
        },
        "regime_tag_counts": dict(regime_counts),
        "documents": manifest_docs,
        "extraction_failures": failures,
        "caselaw": {
            "dataset": "IndianBailJudgments-1200",
            "records": len(cases),
            "duplicate_title_date_groups": len(dups),
            "records_flagged_possible_duplicate": len(dup_ids),
            "note": "Duplicates are flagged with possible_duplicate_of and "
                    "retained, not deleted -- they may be separate proceedings "
                    "sharing a cause title and date.",
        },
        "crossreference": {
            "verification_status": xref.get("verification_status"),
            "caveat": xref.get("caveat"),
            "coverage": xref.get("coverage", {}).get(
                "caselaw_citation_coverage_pct"),
        },
        "sources": {k: SOURCES[k] for k in sorted(sources_used)},
        "quality": {
            "errors": quality.get("counts", {}).get("error", 0),
            "warnings": quality.get("counts", {}).get("warning", 0),
            "report": "data/processed/_quality_report.json",
        },
    }
    write(os.path.join(KB, "manifest.json"), manifest)
    write_readme(manifest, xref)
    return manifest


def write_readme(m: dict, xref: dict) -> None:
    cov = m["coverage"]
    t = m["totals"]
    lines: list[str] = []
    a = lines.append

    a("# Indian Legal Knowledge Base")
    a("")
    a(f"Generated {m['generated']} by `scripts/kb_builder.py`. "
      f"All counts below are computed from the files in this directory.")
    a("")
    a("## What this contains")
    a("")
    a(f"- **{t['statute_documents']} statute documents** / "
      f"**{t['statute_sections']:,} sections** across {len(DOMAINS)} domains")
    a(f"- **{t['cases']:,} case law records** (criminal law only)")
    a(f"- **{t['crossreference_entries']} crossreference entries** "
      f"(IPC/CrPC/Evidence Act to BNS/BNSS/BSA)")
    a(f"- **{t['vector_db_records']:,} legacy vector-db records**")
    a("")
    a("## Coverage by domain")
    a("")
    a("| Domain | Statute docs | Sections | Case law | Jurisdictions |")
    a("|---|---:|---:|---:|---|")
    for d in DOMAINS:
        c = cov[d]
        case = f"{c['case_law_documents']:,}" if c["has_case_law"] else "**none**"
        juris = ", ".join(c["jurisdictions"]) or "—"
        a(f"| {d} | {c['statute_documents']} | {c['statute_sections']:,} | "
          f"{case} | {juris} |")
    a("")
    a("### Case law coverage is criminal law only")
    a("")
    a("This is the most important limitation of this knowledge base. "
      "Case law exists for **one of five domains**:")
    a("")
    a("- **criminal_law** — has both statutes and case law "
      f"({t['cases']:,} bail judgments).")
    a("- **constitutional_law, consumer_protection, family_law, "
      "tenancy_property** — **statutes only. There is no case law for these "
      "four domains.**")
    a("")
    a("The case law that does exist is also narrow: it is entirely "
      "**bail decisions**, not criminal law judgments generally. It does not "
      "cover convictions, sentencing, appeals on merits, or trial procedure. "
      "Any claim of general criminal case law coverage would be wrong.")
    a("")
    a("## Directory layout")
    a("")
    a("```")
    a("knowledge_base/")
    a("  statutes/<domain>/<act>.json      one record per section")
    a("  caselaw/criminal_law/             bail judgments")
    a("  crossreference/                   IPC/CrPC/IEA -> BNS/BNSS/BSA")
    a("  vector_db/legacy_embeddings/*.jsonl  legacy {id, text, metadata} records")
    a("  manifest.json                     counts, per-document provenance")
    a("```")
    a("")
    a("## Sources and licences")
    a("")
    for key, s in m["sources"].items():
        a(f"### {s['name']}")
        a("")
        a(f"- **URL**: {s['url'] or '_not recorded_'}")
        a(f"- **Provenance note**: {s['url_note']}")
        a(f"- **Licence**: {s['license']}")
        a(f"- **Licence verified**: {'yes' if s['license_verified'] else '**no**'}")
        a("")
    a("Only the IndianBailJudgments-1200 licence (CC-BY-4.0) is stated by the "
      "source itself. The statute licences are a reading of Indian copyright "
      "law, not a licence grant found in the files; the acquisition URLs for "
      "the statute PDFs were not recorded and have not been reconstructed.")
    a("")
    a("**Attribution required**: case law records are CC-BY-4.0 and must be "
      "attributed to the IndianBailJudgments-1200 dataset author when "
      "redistributed.")
    a("")
    a("## Crossreference caveat")
    a("")
    a(f"- Verification status: `{m['crossreference']['verification_status']}`")
    a(f"- {m['crossreference']['caveat']}")
    a(f"- Citation-weighted coverage of IPC sections appearing in the case law: "
      f"**{m['crossreference']['coverage']}%**")
    unmapped = xref.get("coverage", {}).get("unmapped_cited_sections", [])
    a(f"- {len(unmapped)} IPC sections cited in the case law are **not yet "
      f"mapped** and need manual completion.")
    a("")
    a("## Known gaps and defects")
    a("")
    if m["extraction_failures"]:
        a("**Documents that failed extraction and contribute nothing:**")
        a("")
        for f in m["extraction_failures"]:
            a(f"- `{f['file']}` ({f['act_name']}) — {f['reason']}")
        a("")
    dq = [d for d in m["documents"] if d["sections_with_encoding_damage"]]
    if dq:
        a("**Documents with partial encoding damage** (affected sections carry "
          "a `data_quality_flag`):")
        a("")
        for d in dq:
            a(f"- `{d['file']}` — {d['sections_with_encoding_damage']} of "
              f"{d['sections']} sections contain undecodable glyphs")
        a("")
    notes = [d for d in m["documents"] if d.get("content_note")]
    if notes:
        a("**Documents whose filename does not describe their contents:**")
        a("")
        for d in notes:
            a(f"- `{d['file']}` — {d['content_note']}")
        a("")
    cl = m["caselaw"]
    a(f"**Case law duplicates**: {cl['duplicate_title_date_groups']} groups "
      f"({cl['records_flagged_possible_duplicate']} records) share a title and "
      f"date. {cl['note']}")
    a("")
    a("**Not covered:**")
    a("")
    a("- Case law for constitutional, consumer, family and tenancy law — none.")
    a("- Family law beyond the three Acts here (no Hindu Succession Act, "
      "Hindu Adoption and Maintenance Act, Indian Divorce Act, Muslim "
      "Personal Law, Guardians and Wards Act).")
    a("- Rent control for states beyond those listed above; Karnataka was "
      "collected but could not be extracted.")
    a("- The Indian Evidence Act 1872 itself is **not** in this corpus, only "
      "its successor the BSA 2023. IEA→BSA source sections are therefore "
      "unverified against primary text.")
    a("- Schedules, forms and the Statement of Objects and Reasons are "
      "excluded; extraction stops at the end of the operative sections.")
    a("- Tamil-script text in the Tamil Nadu gazettes is set in a legacy "
      "non-Unicode font and is not recoverable. English text is unaffected.")
    a("")

    os.makedirs(KB, exist_ok=True)
    with open(os.path.join(KB, "README.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


def main(argv: list[str]) -> int:
    m = build()
    t = m["totals"]
    print(f"knowledge_base/ written")
    print(f"  statute documents : {t['statute_documents']}")
    print(f"  statute sections  : {t['statute_sections']}")
    print(f"  cases             : {t['cases']}")
    print(f"  crossref entries  : {t['crossreference_entries']}")
    print(f"  vector-db records : {t['vector_db_records']}")
    print("\n  by domain:")
    for d, c in m["coverage"].items():
        print(f"    {d:<22} docs={c['statute_documents']:<3} "
              f"sections={c['statute_sections']:<5} "
              f"caselaw={c['case_law_documents']}")
    if m["extraction_failures"]:
        print(f"\n  extraction failures: {len(m['extraction_failures'])}")
        for f in m["extraction_failures"]:
            print(f"    - {f['file']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
