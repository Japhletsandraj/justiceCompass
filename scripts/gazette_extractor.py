"""
Adapter for Tamil Nadu Government Gazette PDFs.

These files are not single acts, and their filenames do not describe their
contents. Two structural facts drive this module:

1. A gazette issue carries *many* unrelated acts. tnrrrlt_act_2017.pdf holds
   Acts 36 to 47 of 2017; the rent statute is only Act 42. Parsing the file as
   one document produces a section list spanning twelve different statutes, so
   we segment on "ACT No. N OF YYYY" and keep only the segment whose long
   title is about rent/landlords/tenants.

2. The page is set in three columns. Section titles are *marginal notes* in the
   right margin (x0 >= ~495) rather than inline headings, statutory citations
   sit in the left margin (x1 <= ~100), and the body runs between them. Reading
   the page as a single text flow interleaves all three, which is what produced
   lines like "Amendment of 4. In section 1 of the principal Act". We classify
   each line by horizontal position and reunite the marginal notes with their
   sections by vertical position.

Everything here is specific to this gazette layout; the indiacode statutes go
through pdf_extractor.py instead.
"""

from __future__ import annotations

import logging
import re
import statistics
from dataclasses import dataclass

import pdfplumber

for _noisy in ("pdfminer", "pdfplumber"):
    logging.getLogger(_noisy).setLevel(logging.ERROR)

# Column boundaries in PDF points, for the 595pt-wide pages in this collection.
LEFT_MARGIN_MAX_X1 = 100.0
RIGHT_MARGIN_MIN_X0 = 495.0

ACT_HEADER_RE = re.compile(r"^ACT\s+No\.\s*(\d+)\s+(?:OF|of)\s+(\d{4})", re.I)
LONG_TITLE_RE = re.compile(r"^An Act\b")
RUNNING_HEAD_RE = re.compile(
    r"TAMIL NADU GOVERNMENT GAZETTE|PUBLISHED BY AUTHORITY|EXTRAORDINARY$"
    r"|^\[?\s*\d+\s*\]?$|PRINTED AND PUBLISHED BY",
    re.I,
)
# The rent statute, its rules and its amendments -- used to pick the relevant
# segment out of a gazette issue full of unrelated acts.
RELEVANCE_RE = re.compile(
    r"regulation of rent|landlords? and tenants?|regulation of rights and "
    r"responsibilities",
    re.I,
)

SECTION_RE = re.compile(r"^\s*(\d{1,3})\s*([A-Z]{0,2})\s*\.\s*(.*)$")
CHAPTER_RE = re.compile(r"^\s*CHAPTER\s+([IVXLCDM]+|\d+)\s*\.?\s*(.*)$", re.I)
CID_RE = re.compile(r"\(cid:\d+\)")


@dataclass
class GLine:
    text: str
    page: int
    y: float          # absolute vertical position across the document
    x0: float
    x1: float
    size: float
    column: str       # "body" | "left" | "right"


def read_lines(path: str) -> tuple[list[GLine], int]:
    out: list[GLine] = []
    with pdfplumber.open(path) as pdf:
        npages = len(pdf.pages)
        for i, page in enumerate(pdf.pages):
            try:
                words = page.extract_words(extra_attrs=["size"])
            except Exception:
                continue
            # Which side the marginal notes sit on is not stable: the 2017 act
            # puts them in the right margin, the 2018 amendment in the left,
            # and the 2019 Rules put the *rule numbers themselves* in a left
            # column (so an x-position rule silently deleted every section
            # number and found zero sections). Type size is stable across all
            # of them -- marginal notes are 8pt against 9pt body -- so classify
            # by size and use x only to order words within a line.
            page_sizes = [w.get("size") or 0 for w in words if w.get("size")]
            if not page_sizes:
                continue
            body_size = statistics.median(page_sizes)

            buckets: dict[int, list] = {}
            for w in words:
                buckets.setdefault(round(w["bottom"] / 3.0), []).append(w)
            for key in sorted(buckets):
                ws = sorted(buckets[key], key=lambda w: w["x0"])
                groups: dict[str, list] = {"margin": [], "body": []}
                for w in ws:
                    sz = w.get("size") or body_size
                    groups["margin" if sz < body_size * 0.95 else "body"].append(w)
                for col, gws in groups.items():
                    if not gws:
                        continue
                    text = " ".join(w["text"] for w in gws).strip()
                    if not text or RUNNING_HEAD_RE.search(text):
                        continue
                    sizes = [w.get("size") or 0 for w in gws if w.get("size")]
                    out.append(
                        GLine(
                            text=text,
                            page=i + 1,
                            y=i * 10000.0 + gws[0]["bottom"],
                            x0=gws[0]["x0"],
                            x1=gws[-1]["x1"],
                            size=statistics.median(sizes) if sizes else 0.0,
                            column=col,
                        )
                    )
    return out, npages


@dataclass
class Segment:
    act_number: str | None
    act_year: int | None
    long_title: str
    lines: list[GLine]


def segment_by_act(lines: list[GLine]) -> list[Segment]:
    """Split a gazette issue into its constituent acts."""
    body = [l for l in lines if l.column == "body"]
    starts: list[tuple[int, str, int]] = []
    for i, l in enumerate(body):
        m = ACT_HEADER_RE.match(l.text)
        if m:
            starts.append((i, m.group(1), int(m.group(2))))

    if not starts:
        return [Segment(None, None, "", lines)]

    segs: list[Segment] = []
    for n, (idx, num, year) in enumerate(starts):
        end_idx = starts[n + 1][0] if n + 1 < len(starts) else len(body)
        chunk = body[idx:end_idx]
        title_parts: list[str] = []
        for l in chunk[:12]:
            if LONG_TITLE_RE.match(l.text) or title_parts:
                title_parts.append(l.text)
                if l.text.rstrip().endswith("."):
                    break
        y_lo = chunk[0].y
        y_hi = chunk[-1].y if chunk else y_lo
        # carry the marginal notes that fall inside this act's vertical span
        seg_lines = [l for l in lines if y_lo <= l.y <= y_hi]
        segs.append(
            Segment(num, year, " ".join(title_parts).strip(), seg_lines)
        )
    return segs


def pick_relevant(segs: list[Segment]) -> tuple[list[Segment], list[Segment]]:
    """Split segments into (rent-related, everything else)."""
    if len(segs) == 1 and segs[0].act_number is None:
        return segs, []
    keep, drop = [], []
    for s in segs:
        text_head = " ".join(l.text for l in s.lines[:40])
        if RELEVANCE_RE.search(s.long_title) or RELEVANCE_RE.search(text_head):
            keep.append(s)
        else:
            drop.append(s)
    return keep, drop


@dataclass
class GSection:
    section_number: str
    section_title: str
    section_text: str
    chapter_number: str | None
    chapter_heading: str | None
    page_start: int
    extraction_confidence: str


# Marginal material mixes section headings with statutory cross-references
# ("Central Act 43 of 1995.", "Tamil Nadu Act V of 1920."). Strip the latter so
# they do not end up as section titles.
CITATION_RE = re.compile(
    r"(Central|Tamil\s+Nadu)\s+Act\s+[IVXLCDM\d]+\s+of\s+\d{4}\.?"
    r"|(?<!\w)[IVXLCDM\d]+\s+of\s+\d{4}\.?"
    r"|(Central|Tamil\s+Nadu)\s+Act\b",
    re.I,
)
# Colophons and press marks also sit in the small type and would otherwise be
# picked up as section titles.
PRESS_MARK_RE = re.compile(
    r"PRINTED AND PUBLISHED.*|ON BEHALF OF THE GOVERNMENT.*"
    r"|DIRECTOR OF STATIONERY.*|\d+-Ex-[IVX\-\d]+",
    re.I,
)
# The 2019 Rules carry inline headings ("3. Making of an application ...--")
# instead of marginal notes, so recover the title from the body text.
INLINE_TITLE_RE = re.compile(r"^\s*(.{3,120}?)\s*[—–]\s*")


def clean_margin_note(text: str) -> str:
    """Turn accumulated marginal fragments into a section title."""
    t = PRESS_MARK_RE.sub(" ", text)
    t = CITATION_RE.sub(" ", t)
    t = re.sub(r"(\w)-\s+(\w)", r"\1\2", t)   # "com- mencement" -> "commencement"
    t = re.sub(r"\s{2,}", " ", t)
    return t.strip(" .,;-")


def parse_segment(seg: Segment) -> list[GSection]:
    body = [l for l in seg.lines if l.column == "body"]
    margins = [l for l in seg.lines if l.column == "margin"]

    starts: list[tuple[int, str, str]] = []
    last = (0, "")
    for i, l in enumerate(body):
        m = SECTION_RE.match(l.text)
        if not m:
            continue
        num, alpha = int(m.group(1)), m.group(2)
        if (num, alpha) <= last:
            continue
        # A gazette body line like "(2) Where, in relation ..." never matches,
        # but a stray numbered clause can; require the remainder to look like
        # the start of a provision rather than a bare fragment.
        starts.append((i, f"{num}{alpha}", m.group(3).strip()))
        last = (num, alpha)

    sections: list[GSection] = []
    chapters: list[tuple[float, str, str | None]] = []
    for i, l in enumerate(body):
        mc = CHAPTER_RE.match(l.text)
        if mc and len(l.text) < 40:
            head = mc.group(2).strip() or None
            if head is None and i + 1 < len(body) and len(body[i + 1].text) < 60:
                head = body[i + 1].text.strip().rstrip(".")
            chapters.append((l.y, mc.group(1).upper(), head))

    for n, (idx, number, first_rest) in enumerate(starts):
        end = starts[n + 1][0] if n + 1 < len(starts) else len(body)
        chunk = body[idx:end]
        text = " ".join([first_rest] + [c.text for c in chunk[1:]])
        text = re.sub(r"\s{2,}", " ", text).strip()

        y_lo, y_hi = chunk[0].y, chunk[-1].y
        note = clean_margin_note(
            " ".join(m.text for m in margins if y_lo - 6 <= m.y <= y_hi + 6)
        )

        if not note:
            m_inline = INLINE_TITLE_RE.match(text)
            if m_inline and not m_inline.group(1).startswith("("):
                note = m_inline.group(1).strip(" .,;-")

        ch_no = ch_head = None
        for cy, cno, chead in chapters:
            if cy <= y_lo:
                ch_no, ch_head = cno, chead
        conf = "high" if len(text) >= 120 and note else (
            "medium" if len(text) >= 40 else "low"
        )
        sections.append(
            GSection(number, note, text, ch_no, ch_head, chunk[0].page, conf)
        )
    return sections


@dataclass
class GResult:
    status: str
    reason: str
    pages: int
    act_number: str | None
    long_title: str
    sections: list[GSection]
    dropped_acts: list[str]
    # Short instruments (a commencement notification, a one-page amendment to
    # the Rules) have no sections at all. They are still real documents, so
    # they are carried as a single whole-document record rather than dropped.
    whole_document_text: str | None = None


def extract_gazette(path: str) -> GResult:
    lines, npages = read_lines(path)
    if not lines:
        return GResult("failed", "No extractable text.", npages, None, "", [], [])

    cid = sum(len(CID_RE.findall(l.text)) for l in lines)
    chars = sum(len(l.text) for l in lines)
    if chars and (cid * 6) / chars > 0.25:
        return GResult(
            "failed",
            "No usable text layer (CID glyph codes without ToUnicode).",
            npages, None, "", [], [],
        )

    segs = segment_by_act(lines)
    keep, drop = pick_relevant(segs)
    dropped = [
        f"Act {s.act_number} of {s.act_year}: {s.long_title[:70]}" for s in drop
    ]

    if not keep:
        return GResult(
            "failed",
            f"Gazette contains {len(segs)} act(s), none of them rent/tenancy "
            f"related.",
            npages, None, "", [], dropped,
        )

    seg = max(keep, key=lambda s: len(s.lines))
    sections = parse_segment(seg)

    status, reason = "ok", ""
    whole = None
    if not sections:
        status = "whole_document"
        reason = (
            "No section numbering present; captured as a single whole-document "
            "record (short notification or one-page amending instrument)."
        )
        whole = re.sub(
            r"\s{2,}", " ",
            " ".join(l.text for l in seg.lines if l.column == "body"),
        ).strip()
    else:
        low = sum(1 for s in sections if s.extraction_confidence == "low")
        if low / len(sections) > 0.35:
            status = "degraded"
            reason = f"{low}/{len(sections)} sections have very short bodies."

    return GResult(
        status, reason, npages, seg.act_number, seg.long_title, sections, dropped,
        whole_document_text=whole,
    )
