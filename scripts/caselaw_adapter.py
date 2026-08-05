"""
Adapter for IndianBailJudgments-1200 -> case/precedent schema.

Citation parsing is the substantive part. The `ipc_sections` column is a
stringified list whose entries arrive in many shapes:

    "120B"                  plain
    "354-A" / "354 A"       separated letter suffix
    "153(A)"                letter suffix written as a parenthetical
    "506(II)"               sub-clause, NOT a letter suffix
    "376(2)(i) r/w 511"     two citations in one token
    "15 NDPS" / "25 Arms Act"   statute named inline
    "3(5) of BNS, 2023"     a different code entirely
    "u/s 498A r/w 34"       prefix noise plus a conjunction

"153(A)" and "506(II)" are the hard pair: both are a number followed by a
parenthetical, but 153A is a distinct section of the IPC while 506(II) is the
second clause of section 506. Rather than guess, we resolve the parenthetical
against the section inventory actually extracted from the IPC and BNS in
step 1 -- "153A" exists as a section, "506II" does not -- so the decision is
made from the statute text instead of a hand-written list.
"""

from __future__ import annotations

import ast
import json
import os
import re
import sys
from collections import Counter

import pandas as pd

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_CSV = os.path.join(REPO, "data", "raw", "indianbail_1200.csv")
PROCESSED = os.path.join(REPO, "data", "processed")
STATUTE_DIR = os.path.join(PROCESSED, "statutes")
OUT_DIR = os.path.join(PROCESSED, "caselaw")

DATASET_NAME = "IndianBailJudgments-1200"
# Taken from scripts/data_loader.py, which is how this file was acquired.
DATASET_URL = "https://huggingface.co/datasets/SnehaDeshmukh/IndianBailJudgments-1200"
LICENSE = "CC-BY-4.0"

# Statutes that appear inline inside a section token. Order matters: longer,
# more specific names first so "Prevention of Corruption Act" is not shadowed.
STATUTE_PATTERNS: list[tuple[str, str]] = [
    (r"prevention\s+of\s+corruption\s+act|\bP\.?C\.?\s*Act\b", "Prevention of Corruption Act, 1988"),
    (r"explosive\s+substances?\s+act", "Explosive Substances Act, 1908"),
    (r"motor\s+vehicles?\s+act", "Motor Vehicles Act, 1988"),
    (r"\bNDPS\b|narcotic", "NDPS Act, 1985"),
    (r"\bPOCSO\b|protection\s+of\s+children", "POCSO Act, 2012"),
    (r"\bMCOCA\b|maharashtra\s+control", "MCOCA, 1999"),
    (r"\bUA\(?P\)?\s*A?\b|unlawful\s+activities", "UAPA, 1967"),
    (r"\barms\s+act\b", "Arms Act, 1959"),
    (r"\bBNSS\b", "Bharatiya Nagarik Suraksha Sanhita, 2023"),
    (r"\bBSA\b|sakshya", "Bharatiya Sakshya Adhiniyam, 2023"),
    (r"\bBNS\b|nyaya\s+sanhita", "Bharatiya Nyaya Sanhita, 2023"),
    (r"\bI\.?T\.?\s*Act\b|information\s+technology", "Information Technology Act, 2000"),
    (r"\bCr\.?P\.?C\.?\b", "Code of Criminal Procedure, 1973"),
    (r"\bSC\s*/?\s*ST\b|scheduled\s+castes", "SC/ST (Prevention of Atrocities) Act, 1989"),
    (r"\bJJ\s*Act\b|juvenile", "Juvenile Justice Act, 2015"),
    (r"dowry\s+prohibition", "Dowry Prohibition Act, 1961"),
    (r"\bgambling\b", "Gambling Act (State)"),
    (r"\bexcise\b", "Excise Act (State)"),
    (r"\bforeigners?\s+act\b", "Foreigners Act, 1946"),
    (r"\bessential\s+commodities\b", "Essential Commodities Act, 1955"),
    (r"\bcompanies\s+act\b", "Companies Act, 2013"),
    (r"\bnegotiable\s+instruments?\b|\bN\.?I\.?\s*Act\b", "Negotiable Instruments Act, 1881"),
    (r"\bPMLA\b|money\s+laundering", "PMLA, 2002"),
    (r"\bwildlife\b|wild\s+life", "Wild Life (Protection) Act, 1972"),
    (r"\bforest\s+act\b", "Indian Forest Act, 1927"),
    (r"\belectricity\s+act\b", "Electricity Act, 2003"),
    (r"\brailways?\s+act\b", "Railways Act, 1989"),
    (r"\bfood\s+safety\b|\bFSSAI\b", "Food Safety and Standards Act, 2006"),
    (r"\bcopyright\b", "Copyright Act, 1957"),
    (r"\btrade\s*marks?\b", "Trade Marks Act, 1999"),
]

# "u/s", "under section", "sec.", "s." and similar lead-ins.
PREFIX_NOISE_RE = re.compile(
    r"^\s*(u\s*/\s*s\.?|under\s+section[s]?|sections?|sec\.?|ss\.?|s\.)\s*",
    re.I,
)
# Splits joined citations ("498A r/w 34"). The comma is guarded so that the
# year in "3(5) of BNS, 2023" is not torn off into its own bogus citation.
SPLIT_RE = re.compile(
    r"\s*(?:r\s*/\s*w|read\s+with|&|\band\b|,(?!\s*\d{4}\b)|\+)\s*", re.I
)
# Fallback for "135 of the Bombay Police Act" -- a statute we do not have a
# pattern for. The section number is still recoverable; name the statute from
# the trailing text rather than silently attributing it to the IPC.
GENERIC_RE = re.compile(
    # The suffix group must not swallow the "of" in "135 of the Bombay Police
    # Act", which would yield section "135OF".
    r"^(\d{1,3})\s*(?!of\b)([A-Za-z]{1,2})?\s*((?:\([^)]*\)\s*)*)\s*"
    r"(?:of\s+)?(?:the\s+)?(.+?(?:act|code|adhiniyam|sanhita)\b.*)$",
    re.I,
)
# 354 / 354A / 354-A / 354 A, then any trailing (2)(i)(a) sub-clauses.
SECTION_RE = re.compile(
    r"^(\d{1,3})\s*[-\s]?\s*([A-Za-z]{1,2})?\s*((?:\([^)]*\)\s*)*)$"
)


def load_known_sections() -> dict[str, set[str]]:
    """Section inventories extracted in step 1, used to resolve ambiguity."""
    known: dict[str, set[str]] = {}
    for fname, key in (
        ("criminal_law__ipc_1860_archived.json", "IPC"),
        ("criminal_law__bns_2023.json", "BNS"),
    ):
        path = os.path.join(STATUTE_DIR, fname)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                known[key] = {
                    str(r["section_number"]).upper() for r in json.load(fh)
                }
        else:
            known[key] = set()
    return known


def detect_statute(text: str) -> str | None:
    for pat, name in STATUTE_PATTERNS:
        if re.search(pat, text, re.I):
            return name
    return None


def parse_citation(raw: str, known: dict[str, set[str]],
                   default_statute: str = "Indian Penal Code, 1860") -> list[dict]:
    """Normalise one raw token into zero or more structured citations."""
    if raw is None:
        return []
    text = str(raw).strip()
    if not text or text.lower() in {"nan", "none", "unknown", "n/a"}:
        return []

    out: list[dict] = []
    for piece in SPLIT_RE.split(text):
        piece = PREFIX_NOISE_RE.sub("", str(piece).strip()).strip(" .;:")
        if not piece:
            continue

        statute = detect_statute(piece) or default_statute
        # Remove the statute words, leaving the numbering behind.
        core = piece
        for pat, _ in STATUTE_PATTERNS:
            core = re.sub(pat, " ", core, flags=re.I)
        core = re.sub(r"\bof\b|\bthe\b|\bact\b|\bsections?\b|,\s*\d{4}", " ", core,
                      flags=re.I)
        core = re.sub(r"\s{2,}", " ", core).strip(" .;:,")
        if not core:
            continue

        # A bare year left over from an act name ("..., 2023") is not a citation.
        if re.fullmatch(r"\d{4}", core):
            continue

        m = SECTION_RE.match(core)
        if not m:
            mg = GENERIC_RE.match(piece)
            if mg:
                name = re.sub(r"\s{2,}", " ", mg.group(4)).strip(" .,;")
                out.append({
                    "statute": name[:1].upper() + name[1:],
                    "section": f"{mg.group(1)}{(mg.group(2) or '').upper()}",
                    "subsections": [
                        s.strip() for s in re.findall(r"\(([^)]*)\)", mg.group(3) or "")
                        if s.strip()
                    ],
                    "raw": piece,
                    "parse_status": "ok_generic_statute",
                })
                continue
            out.append({
                "statute": statute,
                "section": None,
                "subsections": [],
                "raw": piece,
                "parse_status": "unparsed",
            })
            continue

        num, suffix, tail = m.group(1), (m.group(2) or ""), (m.group(3) or "")
        subs = re.findall(r"\(([^)]*)\)", tail)

        # "153(A)" vs "506(II)": promote a leading parenthetical to a letter
        # suffix only when the resulting section actually exists in the code.
        if not suffix and subs:
            cand = subs[0].strip().upper()
            if re.fullmatch(r"[A-Z]{1,2}", cand):
                inventory = known.get(
                    "BNS" if "Nyaya" in statute else "IPC", set()
                )
                if f"{num}{cand}" in inventory:
                    suffix = cand
                    subs = subs[1:]

        section = f"{num}{suffix.upper()}" if suffix else num
        out.append({
            "statute": statute,
            "section": section,
            "subsections": [s.strip() for s in subs if s.strip()],
            "raw": piece,
            "parse_status": "ok",
        })
    return out


def as_list(value) -> list[str]:
    """The CSV stores lists as their Python repr."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    s = str(value).strip()
    if not s or s.lower() in {"nan", "none"}:
        return []
    try:
        parsed = ast.literal_eval(s)
        if isinstance(parsed, list):
            return [str(x).strip() for x in parsed if str(x).strip()]
        if isinstance(parsed, (str, int)):
            return [str(parsed).strip()]
    except (ValueError, SyntaxError):
        pass
    return [s]


def court_level(court: str) -> str:
    c = (court or "").lower()
    if "supreme court" in c:
        return "Supreme Court"
    if "high court" in c:
        return "High Court"
    if "sessions" in c or "district" in c:
        return "District / Sessions Court"
    if "tribunal" in c:
        return "Tribunal"
    return "Unknown"


def to_bool(v) -> bool | None:
    s = str(v).strip().lower()
    if s in {"true", "yes", "1"}:
        return True
    if s in {"false", "no", "0"}:
        return False
    return None


def build() -> tuple[list[dict], dict]:
    df = pd.read_csv(RAW_CSV)
    known = load_known_sections()
    records: list[dict] = []
    stats = Counter()
    unparsed: list[str] = []

    for _, row in df.iterrows():
        cites: list[dict] = []
        for tok in as_list(row.get("ipc_sections")):
            cites.extend(parse_citation(tok, known))
        for tok in as_list(row.get("special_laws")):
            # Bare numbers in special_laws still belong to a special statute,
            # not the IPC; keep the statute unknown rather than mislabelling.
            cites.extend(parse_citation(tok, known, default_statute="Unspecified special law"))

        for c in cites:
            stats[c["parse_status"]] += 1
            if c["parse_status"] == "unparsed":
                unparsed.append(c["raw"])

        date = str(row.get("date") or "").strip()
        rec = {
            "case_id": f"IBJ-{row.get('case_id')}",
            "title": str(row.get("case_title") or "").strip(),
            "citation": None,          # dataset carries no reported citation
            "citation_note": "No reported citation in source dataset; "
                             "identified by case_id and source_filename.",
            "court": str(row.get("court") or "").strip(),
            "court_level": court_level(str(row.get("court") or "")),
            "region": str(row.get("region") or "").strip() or None,
            "date": date or None,
            "year": int(date[:4]) if re.match(r"^\d{4}", date) else None,
            "judges": [j.strip() for j in str(row.get("judge") or "").split(",")
                       if j.strip()],
            "domain_tags": ["criminal_law"],
            "summary": str(row.get("summary") or "").strip(),
            "outcome": str(row.get("bail_outcome") or "").strip(),
            "outcome_detail": str(row.get("bail_outcome_label_detailed") or "").strip()
                              or None,
            # Requested as empty placeholders -- these require reading the full
            # judgment text, which this dataset does not include.
            "ratio_decidendi": "",
            "obiter_dicta": "",
            "cited_sections": cites,
            "case_details": {
                "bail_type": str(row.get("bail_type") or "").strip() or None,
                "is_bail_cancellation": to_bool(row.get("bail_cancellation_case")),
                "is_landmark": to_bool(row.get("landmark_case")),
                "crime_type": str(row.get("crime_type") or "").strip() or None,
                "accused_gender": str(row.get("accused_gender") or "").strip() or None,
                "prior_cases": str(row.get("prior_cases") or "").strip() or None,
                "parity_argument_used": to_bool(row.get("parity_argument_used")),
                "bias_flag": to_bool(row.get("bias_flag")),
                "facts": str(row.get("facts") or "").strip() or None,
                "legal_issues": as_list(row.get("legal_issues")),
                "judgment_reason": str(row.get("judgment_reason") or "").strip() or None,
                "legal_principles_discussed": as_list(
                    row.get("legal_principles_discussed")),
            },
            "source_dataset": DATASET_NAME,
            "source_url": DATASET_URL,
            "source_file": "data/raw/indianbail_1200.csv",
            "source_record": str(row.get("source_filename") or "").strip() or None,
            "license": LICENSE,
        }
        records.append(rec)

    summary = {
        "records": len(records),
        "citations_parsed": stats["ok"],
        "citations_unparsed": stats["unparsed"],
        "unparsed_examples": sorted(set(unparsed))[:25],
    }
    return records, summary


def main(argv: list[str]) -> int:
    dry = "--dry-run" in argv
    records, summary = build()

    print(f"cases                : {summary['records']}")
    print(f"citations parsed     : {summary['citations_parsed']}")
    print(f"citations unparsed   : {summary['citations_unparsed']}")
    if summary["unparsed_examples"]:
        print(f"  examples: {summary['unparsed_examples']}")

    lv = Counter(r["court_level"] for r in records)
    print(f"court levels         : {dict(lv)}")
    oc = Counter(r["outcome"] for r in records)
    print(f"outcomes             : {dict(oc)}")
    statutes = Counter(
        c["statute"] for r in records for c in r["cited_sections"]
    )
    print(f"statutes cited (top) : {statutes.most_common(8)}")

    print("\nsample citation normalisation")
    for probe in ["u/s 120B", "354-A", "354 A", "u/s 498A r/w 34", "153(A)",
                  "506(II)", "376(2)(i) r/w 511", "15 NDPS", "3(5) of BNS, 2023",
                  "66A IT Act"]:
        known = load_known_sections()
        got = parse_citation(probe, known)
        rendered = "; ".join(
            f"{c['statute'].split(',')[0]} s.{c['section']}"
            + (f"({')('.join(c['subsections'])})" if c["subsections"] else "")
            for c in got
        ) or "(none)"
        print(f"  {probe:<22} -> {rendered}")

    if not dry:
        os.makedirs(OUT_DIR, exist_ok=True)
        with open(os.path.join(OUT_DIR, "indianbail_1200.json"), "w",
                  encoding="utf-8") as fh:
            json.dump(records, fh, ensure_ascii=False, indent=2)
        with open(os.path.join(OUT_DIR, "_caselaw_report.json"), "w",
                  encoding="utf-8") as fh:
            json.dump(summary, fh, ensure_ascii=False, indent=2)
        print(f"\nwrote {len(records)} cases to {OUT_DIR}")
    else:
        print("\nDRY RUN -- nothing written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
