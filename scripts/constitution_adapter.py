"""
Two-file adapter for the Constitution of India.

Inputs
  Constitution Of India.csv : one column, 456 rows of article text
  Index.csv                 : Part -> article-range lookup (cp1252 encoded)

Three things make this harder than a split on the leading number:

1. Lettered articles appear in *two* different formats. Some are attached to
   the number ("2A. Sikkim to be associated with the Union"), others put the
   letter after the period ("39. A Equal justice and free legal aid",
   "243Z. A Elections to the Municipalities"). Handling only the first form
   silently loses Articles 39A, 43A, 224A, 226A, 233A, 239A and the whole
   243ZA-243ZG run.

2. Continuation rows imitate article openings. Row 1 is
   "1. The territories of the States; ..." -- a continuation of Article 1(3),
   not a second Article 1. Article numbers must therefore run strictly
   forward; anything that does not is appended to the article it follows.

3. The Part index needs range arithmetic over alphanumeric article ids
   ("Article 243P-243ZG"), a single-article Part ("Article 51A"), a Part with
   no articles at all (Part VII, repealed in 1956), and a trailing row whose
   Part cell is blank because its subject text wrapped.
"""

from __future__ import annotations

import csv
import json
import os
import re
import sys

import pandas as pd

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(REPO, "data", "raw", "statutes", "constitutional_law")
ARTICLES_CSV = os.path.join(RAW, "Constitution Of India.csv")
INDEX_CSV = os.path.join(RAW, "Index.csv")
OUT_DIR = os.path.join(REPO, "data", "processed", "statutes")

# "39. A Equal justice ..." / "243Z. A Elections ..."
# The trailing lookahead for an upper-case word is what separates a real
# lettered article from a continuation line such as "2. A person who ...".
LETTER_AFTER_DOT_RE = re.compile(r"^(\d{1,3})([A-Z]{0,2})\.\s+([A-Z])\s+(?=[A-Z])")
# "2A. Sikkim ..." / "1. Name and territory ..."
LETTER_BEFORE_DOT_RE = re.compile(r"^(\d{1,3})([A-Z]{0,3})\.\s+")

RANGE_RE = re.compile(
    r"Article\s+(\d{1,3}[A-Z]{0,3})\s*(?:[-–—]\s*(\d{1,3}[A-Z]{0,3}))?", re.I
)
ART_KEY_RE = re.compile(r"^(\d{1,3})([A-Z]{0,3})$")


def article_key(article_id: str) -> tuple[int, str]:
    """Sort key for alphanumeric article ids.

    Plain lexicographic comparison of the letter suffix is correct for the
    ranges actually used: A < O, P < ZG, ZH < ZT.
    """
    m = ART_KEY_RE.match(article_id)
    if not m:
        return (10**6, article_id)
    return (int(m.group(1)), m.group(2))


# --------------------------------------------------------------------------
# Part index
# --------------------------------------------------------------------------

def load_parts() -> list[dict]:
    df = pd.read_csv(INDEX_CSV, encoding="cp1252")
    df.columns = [c.strip() for c in df.columns]
    part_col, subj_col, art_col = df.columns[0], df.columns[1], df.columns[2]

    parts: list[dict] = []
    for _, row in df.iterrows():
        part = row[part_col]
        subject = str(row[subj_col]).strip() if pd.notna(row[subj_col]) else ""
        arts = str(row[art_col]).strip() if pd.notna(row[art_col]) else ""

        if pd.isna(part) or not str(part).strip():
            # Trailing row: the subject text wrapped onto its own line with no
            # Part number ("Hindi and Repeals"). Fold it into the previous Part.
            if parts and subject:
                parts[-1]["subject"] = f"{parts[-1]['subject']} {subject}".strip()
            continue

        entry = {
            "part": str(part).strip(),
            "subject": subject,
            "articles_raw": arts,
            "lo": None,
            "hi": None,
            "note": None,
        }
        m = RANGE_RE.search(arts)
        if m:
            lo = m.group(1).upper()
            hi = (m.group(2) or lo).upper()
            entry["lo"], entry["hi"] = lo, hi
        else:
            # Part VII was repealed by the 7th Amendment and covers no articles.
            entry["note"] = "no article range in index (Part repealed or blank)"
        parts.append(entry)
    return parts


def part_for(article_id: str, parts: list[dict]) -> dict | None:
    k = article_key(article_id)
    for p in parts:
        if p["lo"] is None:
            continue
        if article_key(p["lo"]) <= k <= article_key(p["hi"]):
            return p
    return None


# --------------------------------------------------------------------------
# Articles
# --------------------------------------------------------------------------

def parse_articles() -> tuple[list[dict], list[dict]]:
    df = pd.read_csv(ARTICLES_CSV)
    rows = [str(x) for x in df[df.columns[0]].tolist()]

    articles: list[dict] = []
    continuations: list[dict] = []
    last = (0, "")

    for idx, raw in enumerate(rows):
        text = raw.strip()
        if not text or text.lower() == "nan":
            continue

        article_id = None
        rest = None

        m = LETTER_AFTER_DOT_RE.match(text)
        if m:
            article_id = f"{m.group(1)}{m.group(2)}{m.group(3)}"
            rest = text[m.end():].strip()
        else:
            m = LETTER_BEFORE_DOT_RE.match(text)
            if m:
                article_id = f"{m.group(1)}{m.group(2)}"
                rest = text[m.end():].strip()

        key = article_key(article_id) if article_id else None

        if article_id is None or key <= last:
            # Continuation of the article above, not a new one.
            if articles:
                articles[-1]["_body"].append(text)
                continuations.append(
                    {"row": idx, "looked_like": article_id,
                     "attached_to": articles[-1]["article_number"],
                     "preview": text[:90]}
                )
            continue

        title, body, clean = split_title(rest)
        articles.append({
            "article_number": article_id,
            "article_title": title,
            "title_split": "clean" if clean else "heuristic",
            "_body": [body] if body else [],
            "source_row": idx,
        })
        last = key

    for a in articles:
        a["article_text"] = re.sub(r"\s{2,}", " ", " ".join(a.pop("_body"))).strip()
    return articles, continuations


def split_title(rest: str) -> tuple[str, str, bool]:
    """Separate the article heading from its text.

    Returns (title, body, clean). Most rows put the heading on its own line,
    which splits cleanly. Some run heading and operative text together on one
    line with no reliable boundary ("Citizenship at the commencement of the
    Constitution At the commencement of this Constitution, every person who
    ..."). For those the body is returned *whole* and the title is a
    best-effort prefix, flagged clean=False -- cutting at a fixed offset
    truncated the text mid-word and lost its opening clause.
    """
    if not rest:
        return "", "", True

    if "\n" in rest:
        first, _, tail = rest.partition("\n")
        first = first.strip()
        if len(first) <= 160:
            return first.rstrip(":").strip(), tail.strip(), True

    head, sep, after = rest.partition(":")
    if sep and len(head) <= 160 and "\n" not in head:
        return head.strip(), after.strip(), True

    words = rest.split()
    title = " ".join(words[:14])
    if len(title) > 160:
        title = title[:160].rsplit(" ", 1)[0]
    return title.strip(), rest.strip(), False


# --------------------------------------------------------------------------

def build() -> tuple[list[dict], list[dict], list[dict]]:
    parts = load_parts()
    articles, continuations = parse_articles()

    records = []
    for a in articles:
        p = part_for(a["article_number"], parts)
        records.append({
            "doc_id": "constitution_of_india",
            "act_name": "The Constitution of India",
            "act_abbrev": "COI",
            "act_year": 1950,
            "act_number": None,
            "section_number": a["article_number"],
            "section_label": f"Article {a['article_number']}",
            "section_title": a["article_title"],
            "title_split": a["title_split"],
            "section_text": a["article_text"],
            "part": p["part"] if p else None,
            "part_subject": p["subject"] if p else None,
            "chapter_number": None,
            "chapter_heading": None,
            "chapter_subheading": None,
            "domain_tags": ["constitutional_law"],
            "jurisdiction": "India (Union)",
            "regime_tag": "current",
            "document_type": "constitution",
            "source_file": "data/raw/statutes/constitutional_law/"
                           "Constitution Of India.csv",
            "source_url": None,
            "license": None,
            "extraction_confidence": (
                "high" if len(a["article_text"]) >= 120
                else "medium" if len(a["article_text"]) >= 40 else "low"
            ),
        })
    return records, parts, continuations


def main(argv: list[str]) -> int:
    dry = "--dry-run" in argv
    records, parts, continuations = build()

    unassigned = [r["section_number"] for r in records if r["part"] is None]
    print(f"parts in index      : {len(parts)}")
    print(f"articles parsed     : {len(records)}")
    print(f"continuation rows   : {len(continuations)} (merged into previous article)")
    print(f"articles w/o a Part : {len(unassigned)}"
          + (f" -> {unassigned[:12]}" if unassigned else ""))

    lettered = [r["section_number"] for r in records
                if not r["section_number"].isdigit()]
    print(f"lettered articles   : {len(lettered)}")
    print(f"  e.g. {lettered[:14]}")

    print("\nfirst 10 parsed articles")
    print("=" * 92)
    show = records[:10]
    for want in ("2A", "51A"):
        if not any(r["section_number"] == want for r in show):
            hit = next((r for r in records if r["section_number"] == want), None)
            if hit:
                show.append(hit)
    for r in show:
        print(f"[Article {r['section_number']}] {r['section_title'][:70]}")
        print(f"   part={r['part']} ({r['part_subject']})  conf={r['extraction_confidence']}")
        print(f"   text: {r['section_text'][:190]}")
        print()

    if not dry:
        os.makedirs(OUT_DIR, exist_ok=True)
        with open(os.path.join(OUT_DIR, "constitutional_law__constitution.json"),
                  "w", encoding="utf-8") as fh:
            json.dump(records, fh, ensure_ascii=False, indent=2)
        with open(os.path.join(OUT_DIR, "_constitution_parts.json"),
                  "w", encoding="utf-8") as fh:
            json.dump(parts, fh, ensure_ascii=False, indent=2)
        print(f"wrote {len(records)} articles to {OUT_DIR}")
    else:
        print("DRY RUN -- nothing written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
