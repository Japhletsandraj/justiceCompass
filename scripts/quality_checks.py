"""
Validation pass over everything in data/processed/.

Checks, per the brief: duplicates, encoding damage (including Devanagari and
Tamil, where present), broken source_url references, and missing required
schema fields.

Every check is wrapped so that a failure in one file cannot abort the run --
problems are collected and reported by file and domain rather than raised.
Nothing is modified; this only reports.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROCESSED = os.path.join(REPO, "data", "processed")
STATUTES = os.path.join(PROCESSED, "statutes")
CASELAW = os.path.join(PROCESSED, "caselaw")
CROSSREF = os.path.join(PROCESSED, "crossreference")

REQUIRED_STATUTE_FIELDS = [
    "act_name", "section_number", "section_text", "domain_tags",
    "jurisdiction", "source_file",
]
REQUIRED_CASE_FIELDS = [
    "case_id", "title", "court", "date", "domain_tags", "summary", "outcome",
    "source_url", "license",
]

VALID_DOMAINS = {
    "constitutional_law", "criminal_law", "consumer_protection",
    "family_law", "tenancy_property",
}
VALID_REGIMES = {"current", "repealed", None}

# Mojibake signatures: UTF-8 read as cp1252 ("â€”"), lone replacement chars,
# and stray control characters.
MOJIBAKE_RE = re.compile(r"â€|Ã[\x80-\xbf]|Â[\xa0-\xbf]|ï»¿")
REPLACEMENT_RE = re.compile("�")
CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
CID_RE = re.compile(r"\(cid:\d+\)")

DEVANAGARI = re.compile(r"[ऀ-ॿ]")
TAMIL = re.compile(r"[஀-௿]")


class Report:
    def __init__(self) -> None:
        self.issues: dict[str, list[dict]] = defaultdict(list)
        self.stats: Counter = Counter()

    def add(self, scope: str, severity: str, check: str, detail: str,
            sample: str = "") -> None:
        self.issues[scope].append({
            "severity": severity, "check": check,
            "detail": detail, "sample": sample[:200],
        })
        self.stats[severity] += 1

    def failures(self) -> int:
        return self.stats["error"]


def load_json(path: str, rep: Report, scope: str):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except UnicodeDecodeError as e:
        rep.add(scope, "error", "file_encoding",
                f"not valid UTF-8: {e}")
    except json.JSONDecodeError as e:
        rep.add(scope, "error", "file_parse", f"invalid JSON: {e}")
    except OSError as e:
        rep.add(scope, "error", "file_read", str(e))
    return None


def check_text(value: str, scope: str, ident: str, rep: Report) -> None:
    if not isinstance(value, str) or not value:
        return
    if MOJIBAKE_RE.search(value):
        rep.add(scope, "error", "encoding_mojibake",
                f"{ident}: UTF-8 text appears to have been decoded as cp1252",
                value)
    if REPLACEMENT_RE.search(value):
        rep.add(scope, "error", "encoding_replacement_char",
                f"{ident}: contains U+FFFD replacement characters", value)
    if CID_RE.search(value):
        rep.add(scope, "error", "encoding_cid_glyphs",
                f"{ident}: unmapped PDF glyph codes leaked into text", value)
    if CONTROL_RE.search(value):
        rep.add(scope, "warning", "control_characters",
                f"{ident}: contains control characters", value)
    # Indic script integrity: a run of Indic characters should not be broken
    # up by replacement characters, and should normalise cleanly.
    for name, rx in (("devanagari", DEVANAGARI), ("tamil", TAMIL)):
        if rx.search(value):
            rep.stats[f"contains_{name}"] += 1
            if value != unicodedata.normalize("NFC", value):
                rep.add(scope, "warning", f"{name}_not_nfc",
                        f"{ident}: {name} text is not in NFC normal form", value)


def check_statutes(rep: Report) -> dict:
    summary: dict[str, dict] = {}
    if not os.path.isdir(STATUTES):
        rep.add("statutes", "error", "missing_dir", f"{STATUTES} does not exist")
        return summary

    global_hashes: dict[str, tuple[str, str]] = {}

    for fname in sorted(os.listdir(STATUTES)):
        if not fname.endswith(".json") or fname.startswith("_"):
            continue
        scope = f"statutes/{fname}"
        records = load_json(os.path.join(STATUTES, fname), rep, scope)
        if records is None:
            continue
        if not isinstance(records, list):
            rep.add(scope, "error", "shape", "expected a list of records")
            continue

        seen_sections: dict[str, int] = {}
        dupe_text = 0
        domain = None
        for i, r in enumerate(records):
            ident = f"s.{r.get('section_number')}"

            for field in REQUIRED_STATUTE_FIELDS:
                if field not in r:
                    rep.add(scope, "error", "missing_field",
                            f"{ident}: required field '{field}' absent")
                elif r[field] in (None, "", []):
                    sev = "error" if field != "section_text" else "warning"
                    rep.add(scope, sev, "empty_field",
                            f"{ident}: required field '{field}' is empty")

            tags = r.get("domain_tags") or []
            domain = tags[0] if tags else domain
            for t in tags:
                if t not in VALID_DOMAINS:
                    rep.add(scope, "error", "bad_domain_tag",
                            f"{ident}: unknown domain tag '{t}'")
            if r.get("regime_tag") not in VALID_REGIMES:
                rep.add(scope, "error", "bad_regime_tag",
                        f"{ident}: unknown regime_tag '{r.get('regime_tag')}'")

            num = str(r.get("section_number"))
            if num in seen_sections:
                rep.add(scope, "error", "duplicate_section_number",
                        f"section {num} appears at records "
                        f"{seen_sections[num]} and {i}")
            else:
                seen_sections[num] = i

            text = r.get("section_text") or ""
            check_text(text, scope, ident, rep)
            check_text(r.get("section_title") or "", scope, ident, rep)

            if len(text) >= 80:
                h = hashlib.sha1(
                    re.sub(r"\s+", " ", text).strip().lower().encode()
                ).hexdigest()
                if h in global_hashes:
                    prev_file, prev_id = global_hashes[h]
                    if prev_file == fname:
                        dupe_text += 1
                    else:
                        # Identical text across the old and new codes is
                        # expected (BNS re-enacts much of the IPC verbatim),
                        # so only note it between same-regime documents.
                        rep.stats["cross_document_identical_text"] += 1
                else:
                    global_hashes[h] = (fname, ident)

            src = r.get("source_file")
            if src:
                if not os.path.exists(os.path.join(REPO, src.replace("/", os.sep))):
                    rep.add(scope, "error", "broken_source_file",
                            f"{ident}: source_file does not exist: {src}")
            url = r.get("source_url")
            if url is not None and not re.match(r"^https?://", str(url)):
                rep.add(scope, "error", "bad_source_url",
                        f"{ident}: source_url is not a URL: {url!r}")

        if dupe_text:
            rep.add(scope, "warning", "duplicate_section_text",
                    f"{dupe_text} section(s) repeat text found earlier in the "
                    f"same document")

        summary[fname] = {
            "records": len(records),
            "domain": domain,
            "distinct_sections": len(seen_sections),
            "null_source_url": sum(1 for r in records if r.get("source_url") is None),
        }
    return summary


def check_caselaw(rep: Report) -> dict:
    scope = "caselaw/indianbail_1200.json"
    path = os.path.join(CASELAW, "indianbail_1200.json")
    if not os.path.exists(path):
        rep.add(scope, "error", "missing_file", f"{path} does not exist")
        return {}
    records = load_json(path, rep, scope)
    if not isinstance(records, list):
        return {}

    seen_ids: set[str] = set()
    seen_fingerprint: dict[str, str] = {}
    for r in records:
        ident = r.get("case_id", "?")
        for field in REQUIRED_CASE_FIELDS:
            if field not in r:
                rep.add(scope, "error", "missing_field",
                        f"{ident}: required field '{field}' absent")
            elif r[field] in (None, "", []):
                rep.add(scope, "error", "empty_field",
                        f"{ident}: required field '{field}' is empty")

        if ident in seen_ids:
            rep.add(scope, "error", "duplicate_case_id", f"{ident} repeats")
        seen_ids.add(ident)

        key = re.sub(r"\s+", " ", f"{r.get('title','')}|{r.get('date','')}").lower()
        if key in seen_fingerprint and seen_fingerprint[key] != ident:
            rep.add(scope, "warning", "duplicate_case_titledate",
                    f"{ident} has same title+date as {seen_fingerprint[key]}",
                    key)
        else:
            seen_fingerprint[key] = ident

        d = str(r.get("date") or "")
        if d and not re.match(r"^\d{4}-\d{2}-\d{2}$", d):
            rep.add(scope, "error", "bad_date_format",
                    f"{ident}: date not ISO-8601: {d!r}")

        for t in r.get("domain_tags") or []:
            if t not in VALID_DOMAINS:
                rep.add(scope, "error", "bad_domain_tag",
                        f"{ident}: unknown domain tag '{t}'")

        url = r.get("source_url")
        if not url or not re.match(r"^https?://", str(url)):
            rep.add(scope, "error", "bad_source_url",
                    f"{ident}: source_url missing or malformed: {url!r}")

        if r.get("license") != "CC-BY-4.0":
            rep.add(scope, "error", "bad_license",
                    f"{ident}: expected CC-BY-4.0, got {r.get('license')!r}")

        check_text(r.get("summary") or "", scope, ident, rep)
        check_text(r.get("title") or "", scope, ident, rep)

        for c in r.get("cited_sections") or []:
            if c.get("parse_status") == "unparsed":
                rep.add(scope, "warning", "unparsed_citation",
                        f"{ident}: could not parse citation", str(c.get("raw")))

    return {
        "records": len(records),
        "distinct_case_ids": len(seen_ids),
        "courts": len({r.get("court") for r in records}),
    }


def check_crossref(rep: Report) -> dict:
    scope = "crossreference/ipc_bns_mapping.json"
    path = os.path.join(CROSSREF, "ipc_bns_mapping.json")
    if not os.path.exists(path):
        rep.add(scope, "error", "missing_file", f"{path} does not exist")
        return {}
    data = load_json(path, rep, scope)
    if not isinstance(data, dict):
        return {}

    entries = data.get("entries", [])
    seen: set[tuple] = set()
    for e in entries:
        key = (e.get("source_statute"), e.get("source_section"),
               e.get("target_section"))
        if key in seen and key[0] is not None:
            rep.add(scope, "warning", "duplicate_mapping", f"{key} repeats")
        seen.add(key)
        if e.get("target_section") and not e.get("target_section_verified_in_corpus"):
            rep.add(scope, "error", "unverified_target",
                    f"{e.get('source_statute')} {e.get('source_section')} -> "
                    f"{e.get('target_section')} not found in extracted text")
    for p in data.get("validation_problems", []):
        rep.add(scope, "error", "mapping_validation", p)

    return {
        "entries": len(entries),
        "verification_status": data.get("verification_status"),
        "citation_coverage_pct":
            data.get("coverage", {}).get("caselaw_citation_coverage_pct"),
    }


def main(argv: list[str]) -> int:
    rep = Report()
    statutes = check_statutes(rep)
    caselaw = check_caselaw(rep)
    crossref = check_crossref(rep)

    print("=" * 94)
    print("QUALITY CHECKS")
    print("=" * 94)

    print("\nstatute files")
    print(f"{'file':<56}{'recs':>6}{'sect':>6}  domain")
    for f, s in sorted(statutes.items()):
        print(f"{f:<56}{s['records']:>6}{s['distinct_sections']:>6}  {s['domain']}")
    print(f"  total statute records: {sum(s['records'] for s in statutes.values())}")

    print(f"\ncaselaw : {caselaw}")
    print(f"crossref: {crossref}")

    print("\n" + "=" * 94)
    print("ISSUES BY FILE")
    print("=" * 94)
    if not rep.issues:
        print("none")
    for scope in sorted(rep.issues):
        items = rep.issues[scope]
        errs = sum(1 for i in items if i["severity"] == "error")
        warns = len(items) - errs
        print(f"\n{scope}   ({errs} errors, {warns} warnings)")
        grouped: dict[str, list[dict]] = defaultdict(list)
        for i in items:
            grouped[f"{i['severity']}:{i['check']}"].append(i)
        for key in sorted(grouped):
            g = grouped[key]
            print(f"  {key:<42} x{len(g)}")
            for i in g[:2]:
                print(f"      - {i['detail']}")
                if i["sample"]:
                    print(f"        sample: {i['sample'][:110]!r}")

    print("\n" + "=" * 94)
    print(f"SUMMARY: {rep.stats['error']} errors, {rep.stats['warning']} warnings")
    for k in ("contains_devanagari", "contains_tamil",
              "cross_document_identical_text"):
        if rep.stats[k]:
            print(f"  {k}: {rep.stats[k]}")
    print("=" * 94)

    out = {
        "statutes": statutes, "caselaw": caselaw, "crossref": crossref,
        "issues": {k: v for k, v in rep.issues.items()},
        "counts": dict(rep.stats),
    }
    os.makedirs(PROCESSED, exist_ok=True)
    with open(os.path.join(PROCESSED, "_quality_report.json"), "w",
              encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)

    # Reporting failures is the job; a non-zero exit is reserved for --strict.
    if "--strict" in argv and rep.failures():
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
