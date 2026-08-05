"""
Section-level extraction for statute PDFs in data/raw/statutes/.

Design notes (why this is not a naive regex sweep):

* Most files are indiacode.nic.in exports that begin with an
  "ARRANGEMENT OF SECTIONS" table of contents. Every ToC entry looks exactly
  like a real section heading ("12. Definitions."), so parsing from page 1
  produces roughly double the true section count, half of them with empty
  bodies. We skip forward to the enacting formula ("BE it enacted ...") and
  parse only the body.

* indiacode footnotes ("1. Subs. by Act 4 of 2019, s. 2, for ...") are also
  indistinguishable from section headings by regex alone -- and they reset to
  1 on every page. We drop them by font size instead: footnotes are set
  smaller than body text, so any line whose median glyph size falls below a
  fraction of the page median is discarded before parsing.

* Section numbers must not run backwards. A monotonic constraint catches
  whatever survives the two filters above.

Nothing here guesses at section boundaries it cannot see. A file whose text
layer is missing or whose numbering is undetectable is reported with
extraction_status "failed" / "degraded" and contributes no sections.
"""

from __future__ import annotations

import json
import logging
import os
import re
import statistics
import sys
from dataclasses import dataclass, field, asdict
import pdfplumber

import gazette_extractor

for _noisy in ("pdfminer", "pdfplumber"):
    logging.getLogger(_noisy).setLevel(logging.ERROR)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_STATUTES = os.path.join(REPO, "data", "raw", "statutes")
OUT_DIR = os.path.join(REPO, "data", "processed", "statutes")


# --------------------------------------------------------------------------
# Document registry
#
# act_name / act_year here are transcribed from each PDF's own title block
# (verified by reading the first pages), not inferred from the filename.
# act_number is *detected from the document text* at parse time rather than
# hardcoded, so it stays empty when the document does not state it.
# source_url is deliberately null: the acquisition URLs were not recorded in
# data/raw, and inventing them would be fabricated provenance.
# --------------------------------------------------------------------------

CENTRAL = "India (Union)"

REGISTRY: dict[str, dict] = {
    # ---- consumer protection -------------------------------------------
    "consumer_protection/cpa_1986.pdf": dict(
        act_name="The Consumer Protection Act, 1986",
        act_year=1986,
        domain_tags=["consumer_protection"],
        jurisdiction=CENTRAL,
        regime_tag="repealed",
        document_type="principal_act",
    ),
    "consumer_protection/cpa_2019.pdf": dict(
        act_name="The Consumer Protection Act, 2019",
        act_year=2019,
        domain_tags=["consumer_protection"],
        jurisdiction=CENTRAL,
        regime_tag="current",
        document_type="principal_act",
    ),
    # ---- criminal law ---------------------------------------------------
    # NOTE: the file is named bna_2023.pdf but its title block reads
    # "The Bharatiya Sakshya Adhiniyam, 2023 (ACT NO. 47 OF 2023)".
    # We record what the document says and flag the filename mismatch.
    "criminal_law/bna_2023.pdf": dict(
        act_name="The Bharatiya Sakshya Adhiniyam, 2023",
        act_abbrev="BSA",
        act_year=2023,
        domain_tags=["criminal_law"],
        jurisdiction=CENTRAL,
        regime_tag="current",
        document_type="principal_act",
        filename_mismatch="File is named bna_2023.pdf; document is the Bharatiya "
        "Sakshya Adhiniyam (BSA), Act 47 of 2023.",
    ),
    "criminal_law/bns_2023.pdf": dict(
        act_name="The Bharatiya Nyaya Sanhita, 2023",
        act_abbrev="BNS",
        act_year=2023,
        domain_tags=["criminal_law"],
        jurisdiction=CENTRAL,
        regime_tag="current",
        document_type="principal_act",
    ),
    "criminal_law/bnss_2023.pdf": dict(
        act_name="The Bharatiya Nagarik Suraksha Sanhita, 2023",
        act_abbrev="BNSS",
        act_year=2023,
        domain_tags=["criminal_law"],
        jurisdiction=CENTRAL,
        regime_tag="current",
        document_type="principal_act",
    ),
    "criminal_law/crpc_1973_archived.pdf": dict(
        act_name="The Code of Criminal Procedure, 1973",
        act_abbrev="CrPC",
        act_year=1973,
        domain_tags=["criminal_law"],
        jurisdiction=CENTRAL,
        regime_tag="repealed",
        document_type="principal_act",
    ),
    "criminal_law/ipc_1860_archived.pdf": dict(
        act_name="The Indian Penal Code, 1860",
        act_abbrev="IPC",
        act_year=1860,
        domain_tags=["criminal_law"],
        jurisdiction=CENTRAL,
        regime_tag="repealed",
        document_type="principal_act",
    ),
    # ---- family law -----------------------------------------------------
    "family_law/dv_act_2005.pdf": dict(
        act_name="The Protection of Women from Domestic Violence Act, 2005",
        act_year=2005,
        domain_tags=["family_law"],
        jurisdiction=CENTRAL,
        regime_tag="current",
        document_type="principal_act",
    ),
    "family_law/hindu_marriage_act_1955.pdf": dict(
        act_name="The Hindu Marriage Act, 1955",
        act_year=1955,
        domain_tags=["family_law"],
        jurisdiction=CENTRAL,
        regime_tag="current",
        document_type="principal_act",
    ),
    "family_law/special_marriage_act_1954.pdf": dict(
        act_name="The Special Marriage Act, 1954",
        act_year=1954,
        domain_tags=["family_law"],
        jurisdiction=CENTRAL,
        regime_tag="current",
        document_type="principal_act",
    ),
    # ---- tenancy / property --------------------------------------------
    "tenancy_property/transfer_of_property_act_1882.pdf": dict(
        act_name="The Transfer of Property Act, 1882",
        act_year=1882,
        domain_tags=["tenancy_property"],
        jurisdiction=CENTRAL,
        regime_tag="current",
        document_type="principal_act",
    ),
    "tenancy_property/rent_control/Delhi_Rent_Act.pdf": dict(
        act_name="The Delhi Rent Control Act, 1958",
        act_year=1958,
        domain_tags=["tenancy_property"],
        jurisdiction="Delhi",
        regime_tag="current",
        document_type="principal_act",
    ),
    "tenancy_property/rent_control/Karnataka_Rent_Act_1999.pdf": dict(
        act_name="The Karnataka Rent Act, 1999",
        act_year=1999,
        domain_tags=["tenancy_property"],
        jurisdiction="Karnataka",
        regime_tag="current",
        document_type="principal_act",
    ),
    "tenancy_property/rent_control/Maharashtra_Rent_Control.pdf": dict(
        act_name="The Maharashtra Rent Control Act, 1999",
        act_year=1999,
        domain_tags=["tenancy_property"],
        jurisdiction="Maharashtra",
        regime_tag="current",
        document_type="principal_act",
    ),
    "tenancy_property/rent_control/West_Bengal_Rent_Act.pdf": dict(
        act_name="The West Bengal Premises Tenancy Act, 1997",
        act_year=1997,
        domain_tags=["tenancy_property"],
        jurisdiction="West Bengal",
        regime_tag="current",
        document_type="principal_act",
    ),
    # ---- tamil nadu: six documents kept separate, never merged ----------
    # ---- tamil nadu ------------------------------------------------------
    # These six are whole *gazette issues*, and five of the six filenames do
    # not describe their contents. act_name / document_type below record what
    # each document actually is, verified from its own text; content_note
    # records the discrepancy so the filename is never silently trusted.
    "tenancy_property/rent_control/tamilnadu/tnrrrlt_act_2017.pdf": dict(
        act_name="The Tamil Nadu Regulation of Rights and Responsibilities of "
        "Landlords and Tenants Act, 2017",
        act_year=2017,
        domain_tags=["tenancy_property"],
        jurisdiction="Tamil Nadu",
        regime_tag="current",
        document_type="principal_act",
        gazette=True,
        content_note="Gazette issue containing Acts 36-47 of 2017; only Act 42 "
        "of 2017 (the rent statute) is extracted.",
    ),
    "tenancy_property/rent_control/tamilnadu/tnrrrlt_amendment_act_2018.pdf": dict(
        act_name="The Tamil Nadu Regulation of Rights and Responsibilities of "
        "Landlords and Tenants (Amendment) Act, 2018",
        act_year=2018,
        domain_tags=["tenancy_property"],
        jurisdiction="Tamil Nadu",
        regime_tag="current",
        document_type="amendment",
        amends="The Tamil Nadu Regulation of Rights and Responsibilities of "
        "Landlords and Tenants Act, 2017",
        gazette=True,
        content_note="Gazette issue containing Acts 35-40 of 2018; only Act 39 "
        "of 2018 (the rent amendment) is extracted.",
    ),
    "tenancy_property/rent_control/tamilnadu/tnrrrlt_rules_2019.pdf": dict(
        act_name="Amendments to the Tamil Nadu Regulation of Rights and "
        "Responsibilities of Landlords and Tenants Rules, 2019",
        act_year=2019,
        domain_tags=["tenancy_property"],
        jurisdiction="Tamil Nadu",
        regime_tag="current",
        document_type="amendment",
        amends="The Tamil Nadu Regulation of Rights and Responsibilities of "
        "Landlords and Tenants Rules, 2019",
        gazette=True,
        content_note="Filename says 'rules'; the document is a one-page "
        "amendment to those Rules (G.O. Ms. No. 103, 11 July 2019).",
    ),
    "tenancy_property/rent_control/tamilnadu/notification_commencement_2019.pdf": dict(
        act_name="Notification: date of coming into force of the Tamil Nadu "
        "Regulation of Rights and Responsibilities of Landlords and Tenants "
        "Act, 2017",
        act_year=2019,
        domain_tags=["tenancy_property"],
        jurisdiction="Tamil Nadu",
        regime_tag="current",
        document_type="notification",
        gazette=True,
    ),
    "tenancy_property/rent_control/tamilnadu/notification_registration_extension_2019.pdf": dict(
        act_name="The Tamil Nadu Regulation of Rights and Responsibilities of "
        "Landlords and Tenants (Amendment) Act, 2019",
        act_year=2019,
        domain_tags=["tenancy_property"],
        jurisdiction="Tamil Nadu",
        regime_tag="current",
        document_type="amendment",
        amends="The Tamil Nadu Regulation of Rights and Responsibilities of "
        "Landlords and Tenants Act, 2017",
        gazette=True,
        content_note="Filename says 'notification'; the document is Act 22 of "
        "2019, an amending Act. The same gazette issue also carries Act 21 of "
        "2019 (fishermen welfare), which is unrelated and not extracted.",
    ),
    "tenancy_property/rent_control/tamilnadu/notification_rent_court_2019.pdf": dict(
        act_name="The Tamil Nadu Regulation of Rights and Responsibilities of "
        "Landlords and Tenants Rules, 2019",
        act_year=2019,
        domain_tags=["tenancy_property"],
        jurisdiction="Tamil Nadu",
        regime_tag="current",
        document_type="rules",
        gazette=True,
        content_note="Filename says 'notification'; the document is the "
        "principal TNRRRLT Rules, 2019 (G.O. Ms. No. 36, 22 February 2019).",
    ),
}


# --------------------------------------------------------------------------
# Text layer reconstruction
# --------------------------------------------------------------------------

@dataclass
class Line:
    text: str
    size: float
    page: int


def page_lines(page, page_no: int) -> list[Line]:
    """Rebuild lines from words, carrying median glyph size so footnotes can
    be told apart from body text."""
    try:
        words = page.extract_words(extra_attrs=["size"], use_text_flow=False)
    except Exception:
        return []
    # Bucket by baseline, not by glyph top: indiacode sets the initial letter of
    # chapter headings (and some section titles) in a larger point size, which
    # gives it a higher bbox top and would split "PRELIMINARY" into "P" +
    # "RELIMINARY". Characters on one printed line share a baseline.
    buckets: dict[int, list] = {}
    for w in words:
        key = round(w["bottom"] / 3.0)
        buckets.setdefault(key, []).append(w)
    out: list[Line] = []
    for key in sorted(buckets):
        ws = sorted(buckets[key], key=lambda w: w["x0"])
        text = " ".join(w["text"] for w in ws).strip()
        if not text:
            continue
        sizes = [w.get("size") or 0 for w in ws if w.get("size")]
        out.append(Line(text, statistics.median(sizes) if sizes else 0.0, page_no))
    return out


def is_heading_shaped(text: str) -> bool:
    """True for lines that look like a chapter/part heading rather than a
    footnote: short, at least three letters, and entirely upper-case."""
    t = text.strip()
    if len(t) > 120:
        return False
    letters = [c for c in t if c.isalpha()]
    return len(letters) >= 3 and all(c.isupper() for c in letters)


CID_RE = re.compile(r"\(cid:\d+\)")
PAGE_NUM_RE = re.compile(r"^\s*\d{1,4}\s*$")
FOOTNOTE_HINT_RE = re.compile(
    r"^\d+\.\s*(Subs\.|Ins\.|Omitted|Rep\.|Added|Sub\.|Certain words|The words|"
    r"Now|Vide|w\.e\.f\.|Cf\.|See\b)",
    re.I,
)


def load_lines(path: str) -> tuple[list[Line], int, float, str]:
    """Return (kept lines, page count, cid-garbage ratio, raw title-page text).

    The raw head is unfiltered: title-block details such as "(ACT NO. 45 OF
    2023)" are set smaller than the act title above them, so the footnote
    filter would otherwise discard exactly the line we need for provenance.
    """
    kept: list[Line] = []
    raw_head: list[str] = []
    cid_hits = 0
    total_chars = 0
    with pdfplumber.open(path) as pdf:
        npages = len(pdf.pages)
        for i, page in enumerate(pdf.pages):
            lines = page_lines(page, i + 1)
            if not lines:
                continue
            if i < 3:
                raw_head.extend(l.text for l in lines)
            for ln in lines:
                cid_hits += len(CID_RE.findall(ln.text))
                total_chars += len(ln.text)
            body_size = statistics.median([l.size for l in lines if l.size]) if any(
                l.size for l in lines
            ) else 0.0
            for ln in lines:
                if PAGE_NUM_RE.match(ln.text):
                    continue
                if FOOTNOTE_HINT_RE.match(ln.text):
                    continue
                # Type size alone cannot separate footnotes from headings: in
                # these indiacode exports the small-caps chapter headings and
                # the footnote apparatus are both set at 9pt against 11pt body
                # text. Among the undersized lines, keep the ones shaped like a
                # heading (short, all upper-case once the small-caps initial is
                # rejoined) and discard the rest as footnotes.
                if body_size and ln.size and ln.size < body_size * 0.95:
                    if not is_heading_shaped(ln.text):
                        continue
                kept.append(ln)
    ratio = (cid_hits * 6) / total_chars if total_chars else 0.0
    return kept, npages, ratio, " ".join(raw_head)


# --------------------------------------------------------------------------
# Body start detection (skip ARRANGEMENT OF SECTIONS)
# --------------------------------------------------------------------------

ENACT_MARKERS = (
    "beitenacted",
    "itisherebyenacted",
    "befurtherenacted",
    "whereasitisexpedient",
)
TOC_MARK_RE = re.compile(r"arrangement of sections|^contents$", re.I)


def _compact(text: str) -> str:
    """Lower-case with all whitespace removed.

    Matching happens on this form because small caps split words in the text
    layer: the Hindu Marriage Act's enacting formula extracts as
    "B E it enacted by Parliament", which no spaced pattern would match.
    """
    return re.sub(r"\s+", "", text).lower()


def find_body_start(lines: list[Line]) -> tuple[int, str]:
    """Index of first body line, plus how we decided."""
    has_toc = any(TOC_MARK_RE.search(l.text) for l in lines[: min(len(lines), 400)])
    for i, ln in enumerate(lines):
        c = _compact(ln.text)
        if any(m in c for m in ENACT_MARKERS):
            return i + 1, "enacting_formula"
    if has_toc:
        # ToC present but no enacting formula found -- fall back to the last
        # "CHAPTER I" occurrence, which begins the body in indiacode layouts.
        idxs = [i for i, l in enumerate(lines) if re.match(r"^\s*CHAPTER\s+I\b", l.text)]
        if len(idxs) >= 2:
            return idxs[-1], "last_chapter_i_after_toc"
        return 0, "toc_present_but_unresolved"
    return 0, "no_front_matter"


# --------------------------------------------------------------------------
# Section parsing
# --------------------------------------------------------------------------

# indiacode wraps provisions inserted or substituted by amendment in square
# brackets, often preceded by a superscript footnote marker that extracts as a
# leading digit: "1[13A. Alternate relief in divorce proceedings.--...".
# Without the optional bracket prefix those sections are not recognised as
# section starts and get absorbed into the previous section's body (this was
# dropping HMA ss. 13A, 16, 19, 21A, 22, 23A and 28). The trailing "." is
# required, so ordinary sub-clause openers like "(2) It extends ..." still do
# not match.
SECTION_RE = re.compile(
    r"^\s*(?:\d{0,2}\s*[\[(]\s*)?(\d{1,3})\s*([A-Z]{0,2})\s*\.\s*(?:[-—–]*)\s*(.*)$"
)
CHAPTER_RE = re.compile(r"^\s*CHAPTER\s+([IVXLCDM]+|\d+)\s*[-—–.:]?\s*(.*)$", re.I)
PART_RE = re.compile(r"^\s*PART\s+([IVXLCDM]+|\d+)\s*[-—–.:]?\s*(.*)$")
SCHEDULE_RE = re.compile(r"^\s*(THE\s+)?(FIRST|SECOND|THIRD|\w+)?\s*SCHEDULE\b", re.I)

# Everything after one of these headings is post-enactment matter -- schedules,
# the Statement of Objects and Reasons, appended amendment acts. Those restart
# their own numbering from 1, which would otherwise be emitted as bogus
# low-numbered sections after the real body (e.g. CrPC picking up "1, 16, 28"
# from an appendix at p.261, after correctly ending at s.484 on p.195).
END_OF_BODY_RE = re.compile(
    r"^\s*(THE\s+)?((FIRST|SECOND|THIRD|FOURTH|FIFTH)\s+)?SCHEDULE\b"
    r"|^\s*STATEMENT\s+OF\s+OBJECTS\s+AND\s+REASONS\b"
    r"|^\s*APPENDIX\b",
    re.I,
)


def _key(num: int, alpha: str) -> tuple[int, str]:
    return (num, alpha)


def normalise_smallcaps(text: str | None) -> str | None:
    """Rejoin small-caps initials that PDF text extraction split off.

    indiacode sets headings in small caps with an oversized initial, which the
    text layer emits as a detached capital: "P RELIMINARY",
    "O F OFFENCES AFFECTING THE HUMAN BODY". Any single-letter token is glued
    to the following token when that token is also upper-case, applied left to
    right so "O" + "F" + "OFFENCES" resolves to "OF OFFENCES" rather than
    "O FOFFENCES". Headings that were never split are unaffected, since they
    contain no single-letter tokens.
    """
    if not text:
        return text
    toks = text.split()
    out: list[str] = []
    i = 0
    while i < len(toks):
        t = toks[i]
        if (
            len(t) == 1
            and t.isalpha()
            and t.isupper()
            and i + 1 < len(toks)
            and toks[i + 1][:1].isupper()
        ):
            out.append(t + toks[i + 1])
            i += 2
            continue
        out.append(t)
        i += 1
    joined = " ".join(out)
    joined = re.sub(r"\s+([,;.])", r"\1", joined)   # "OFFICERS , SERVICE" -> "OFFICERS,"
    return re.sub(r"\s{2,}", " ", joined).strip()


@dataclass
class Section:
    section_number: str
    section_title: str
    section_text: str
    chapter_number: str | None
    chapter_heading: str | None
    chapter_subheading: str | None
    part: str | None
    page_start: int
    extraction_confidence: str


def parse_sections(
    lines: list[Line], start: int
) -> tuple[list[Section], list[str], str | None]:
    sections: list[Section] = []
    anomalies: list[str] = []
    truncated_at: str | None = None
    # Some acts (the Hindu Marriage Act, for one) have no CHAPTER divisions and
    # organise sections under small-caps cross-headings instead. Only treat
    # bare all-caps lines as headings when the body really has no chapters,
    # otherwise all-caps lines inside section text would be swallowed.
    body = lines[start:]
    crossheading_mode = not any(CHAPTER_RE.match(l.text.strip()) for l in body)
    cur_chapter_no: str | None = None
    cur_chapter_head: str | None = None
    cur_chapter_sub: str | None = None
    cur_part: str | None = None
    last = (0, "")
    pending_chapter = False
    buf: list[str] = []
    cur: Section | None = None

    def flush():
        nonlocal cur, buf
        if cur is not None:
            body = " ".join(buf).strip()
            body = re.sub(r"^[\s‐-―.\-—–]+", "", body)  # dash left by title split
            cur.section_text = re.sub(r"\s{2,}", " ", body)
            n = len(cur.section_text)
            cur.extraction_confidence = (
                "high" if n >= 120 else "medium" if n >= 40 else "low"
            )
            sections.append(cur)
        cur, buf = None, []

    for ln in body:
        t = ln.text.strip()
        if not t:
            continue

        m_part = PART_RE.match(t)
        if m_part and len(t) < 60:
            cur_part = f"PART {m_part.group(1)}"
            if m_part.group(2).strip():
                cur_part += f" — {m_part.group(2).strip()}"
            continue

        m_ch = CHAPTER_RE.match(t)
        if m_ch and len(t) < 80:
            cur_chapter_no = m_ch.group(1).upper()
            tail = m_ch.group(2).strip()
            cur_chapter_head = normalise_smallcaps(tail) if tail else None
            cur_chapter_sub = None
            pending_chapter = not tail
            continue

        if pending_chapter:
            # The heading follows "CHAPTER N" on the next line(s) and may wrap.
            # Case is not a reliable signal on its own: indiacode uses small
            # caps ("P RELIMINARY") for the chapter heading, and BNS adds a
            # second, title-case sub-heading under it ("Of sexual offences").
            # So: take all-caps lines as the heading (wrapping across lines),
            # and a following title-case line as a separate sub-heading.
            if SECTION_RE.match(t) or CHAPTER_RE.match(t) or len(t) >= 120:
                pending_chapter = False
                cur_chapter_head = normalise_smallcaps(cur_chapter_head)
            else:
                if cur_chapter_head is None:
                    cur_chapter_head = t.strip()
                    pending_chapter = is_heading_shaped(t)
                elif is_heading_shaped(t):
                    cur_chapter_head = f"{cur_chapter_head} {t}".strip()
                else:
                    cur_chapter_sub = t.strip()
                    pending_chapter = False
                if not pending_chapter:
                    cur_chapter_head = normalise_smallcaps(cur_chapter_head)
                continue

        if END_OF_BODY_RE.match(t) and len(t) < 60 and t.isupper():
            flush()
            truncated_at = f"{t} (p.{ln.page})"
            break

        m = SECTION_RE.match(t)
        if m:
            num, alpha, rest = int(m.group(1)), m.group(2), m.group(3).strip()
            cand = _key(num, alpha)
            if cand > last:
                if num > last[0] + 40 and last[0] > 0:
                    anomalies.append(
                        f"numbering jump {last[0]}{last[1]} -> {num}{alpha} "
                        f"(p.{ln.page})"
                    )
                flush()
                title = rest
                inline = ""
                # "12. Definitions.—(1) In this Act ..." : split title from body
                sp = re.split(r"[.—–-]{1,2}\s*(?=[(—]|[A-Z][a-z])", rest, maxsplit=1)
                if len(sp) == 2 and len(sp[0]) < 120:
                    title, inline = sp[0].strip(), sp[1].strip()
                cur = Section(
                    section_number=f"{num}{alpha}",
                    section_title=title.rstrip(".").strip(),
                    section_text="",
                    chapter_number=cur_chapter_no,
                    chapter_heading=cur_chapter_head,
                    chapter_subheading=cur_chapter_sub,
                    part=cur_part,
                    page_start=ln.page,
                    extraction_confidence="unknown",
                )
                buf = [inline] if inline else []
                last = cand
                continue

        if crossheading_mode and is_heading_shaped(t) and not SECTION_RE.match(t):
            cur_chapter_head = normalise_smallcaps(t)
            cur_chapter_sub = None
            continue

        if cur is not None:
            buf.append(t)

    flush()
    return sections, anomalies, truncated_at


# --------------------------------------------------------------------------
# Per-document driver
# --------------------------------------------------------------------------

ACTNO_RE = re.compile(r"ACT\s+N[Oo]\.?\s*([IVXLCDM\d]+)\s+OF\s+(\d{4})", re.I)


@dataclass
class DocResult:
    source_file: str
    act_name: str
    extraction_status: str
    reason: str
    pages: int
    section_count: int
    body_start_method: str
    act_number: str | None
    anomalies: list[str] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)
    meta: dict = field(default_factory=dict)


def extract_gazette_document(rel: str, meta: dict) -> DocResult:
    """Route Tamil Nadu gazette issues through the gazette adapter."""
    path = os.path.join(RAW_STATUTES, rel.replace("/", os.sep))
    g = gazette_extractor.extract_gazette(path)
    act_name = meta.get("act_name", os.path.basename(rel))

    sections = [
        Section(
            section_number=s.section_number,
            section_title=s.section_title,
            section_text=s.section_text,
            chapter_number=s.chapter_number,
            chapter_heading=s.chapter_heading,
            chapter_subheading=None,
            part=None,
            page_start=s.page_start,
            extraction_confidence=s.extraction_confidence,
        )
        for s in g.sections
    ]
    if g.status == "whole_document" and g.whole_document_text:
        sections = [
            Section(
                section_number="(whole document)",
                section_title=act_name,
                section_text=g.whole_document_text,
                chapter_number=None,
                chapter_heading=None,
                chapter_subheading=None,
                part=None,
                page_start=1,
                extraction_confidence="whole_document",
            )
        ]

    anomalies = []
    if g.dropped_acts:
        anomalies.append(
            f"gazette issue also contains {len(g.dropped_acts)} unrelated act(s), "
            f"not extracted"
        )
    status = "ok" if g.status in ("ok", "whole_document") else g.status
    act_no = f"{g.act_number} of {meta.get('act_year')}" if g.act_number else None
    return DocResult(rel, act_name, status, g.reason, g.pages, len(sections),
                     "gazette_segmentation", act_no, anomalies, sections, meta)


def extract_document(rel: str) -> DocResult:
    path = os.path.join(RAW_STATUTES, rel.replace("/", os.sep))
    meta = REGISTRY.get(rel, {})
    act_name = meta.get("act_name", os.path.basename(rel))

    if meta.get("gazette"):
        return extract_gazette_document(rel, meta)

    lines, npages, cid_ratio, raw_head = load_lines(path)

    if cid_ratio > 0.25:
        return DocResult(
            rel, act_name, "failed",
            f"PDF has no usable text layer: {cid_ratio:.0%} of extracted content is "
            f"(cid:N) glyph codes with no ToUnicode mapping. Needs OCR or a "
            f"re-download of a text-bearing copy.",
            npages, 0, "n/a", None, meta=meta,
        )
    if not lines:
        return DocResult(rel, act_name, "failed",
                         "No extractable text (likely a scanned image PDF).",
                         npages, 0, "n/a", None, meta=meta)

    m_actno = ACTNO_RE.search(raw_head)
    act_number = f"{m_actno.group(1)} of {m_actno.group(2)}" if m_actno else None

    start, method = find_body_start(lines)
    sections, anomalies, truncated_at = parse_sections(lines, start)
    if truncated_at:
        anomalies.append(f"body parsing stopped at {truncated_at}")

    status, reason = "ok", ""
    if not sections:
        status = "failed"
        reason = ("No section boundaries detected. Document is dense paragraph "
                  "text without resolvable section numbering.")
    else:
        low = sum(1 for s in sections if s.extraction_confidence == "low")
        low_frac = low / len(sections)
        if method == "toc_present_but_unresolved":
            status, reason = "degraded", (
                "Table of contents detected but the body start could not be "
                "located; ToC entries may be mixed into the section list.")
        elif low_frac > 0.35:
            status, reason = "degraded", (
                f"{low}/{len(sections)} sections ({low_frac:.0%}) have bodies under "
                f"40 characters -- boundaries are probably unreliable.")
        elif meta.get("gazette") and len(sections) < 3:
            status, reason = "degraded", (
                "Gazette document yielded very few sections; likely a short "
                "notification rather than a sectioned instrument.")

    return DocResult(rel, act_name, status, reason, npages, len(sections), method,
                     act_number, anomalies, sections, meta)


def to_records(doc: DocResult) -> list[dict]:
    m = doc.meta
    out = []
    for s in doc.sections:
        rec = {
            "doc_id": f"{os.path.splitext(os.path.basename(doc.source_file))[0]}",
            "act_name": doc.act_name,
            "act_abbrev": m.get("act_abbrev"),
            "act_year": m.get("act_year"),
            "act_number": doc.act_number,
            "section_number": s.section_number,
            "section_title": s.section_title,
            "section_text": s.section_text,
            "chapter_number": s.chapter_number,
            "chapter_heading": s.chapter_heading,
            "chapter_subheading": s.chapter_subheading,
            "part": s.part,
            "domain_tags": m.get("domain_tags", []),
            "jurisdiction": m.get("jurisdiction"),
            "regime_tag": m.get("regime_tag"),
            "document_type": m.get("document_type"),
            "source_file": f"data/raw/statutes/{doc.source_file}",
            "source_url": None,          # not recorded at acquisition; see README
            "license": None,             # per-source; resolved in kb_builder
            "page_start": s.page_start,
            "extraction_confidence": s.extraction_confidence,
        }
        if m.get("amends"):
            rec["amends"] = m["amends"]
        if m.get("content_note"):
            rec["content_note"] = m["content_note"]
        if m.get("filename_mismatch"):
            rec["content_note"] = m["filename_mismatch"]
        out.append(rec)
    return out


def all_docs() -> list[str]:
    found = []
    for dirpath, _, files in os.walk(RAW_STATUTES):
        for f in sorted(files):
            if f.lower().endswith(".pdf"):
                rel = os.path.relpath(os.path.join(dirpath, f), RAW_STATUTES)
                found.append(rel.replace(os.sep, "/"))
    return sorted(found)


def main(argv: list[str]) -> int:
    dry = "--dry-run" in argv
    docs = all_docs()
    unregistered = [d for d in docs if d not in REGISTRY]
    results: list[DocResult] = []

    for rel in docs:
        sys.stderr.write(f"  parsing {rel} ...\n")
        sys.stderr.flush()
        results.append(extract_document(rel))

    print("\n" + "=" * 92)
    print(f"{'FILE':<58}{'PG':>5}{'SECS':>6}  STATUS")
    print("=" * 92)
    for r in results:
        print(f"{r.source_file:<58}{r.pages:>5}{r.section_count:>6}  {r.extraction_status}")
        if r.reason:
            print(f"{'':<58}{'':>11}  ! {r.reason}")
        for a in r.anomalies[:3]:
            print(f"{'':<58}{'':>11}  ~ {a}")
    print("=" * 92)
    ok = [r for r in results if r.extraction_status == "ok"]
    deg = [r for r in results if r.extraction_status == "degraded"]
    bad = [r for r in results if r.extraction_status == "failed"]
    print(f"ok={len(ok)}  degraded={len(deg)}  failed={len(bad)}  "
          f"total_sections={sum(r.section_count for r in results)}")
    if unregistered:
        print(f"UNREGISTERED FILES (no metadata): {unregistered}")

    if not dry:
        os.makedirs(OUT_DIR, exist_ok=True)
        for r in results:
            if r.extraction_status == "failed":
                continue
            recs = to_records(r)
            name = r.source_file.replace("/", "__").replace(".pdf", ".json")
            with open(os.path.join(OUT_DIR, name), "w", encoding="utf-8") as fh:
                json.dump(recs, fh, ensure_ascii=False, indent=2)
        report = [
            {k: v for k, v in asdict(r).items() if k != "sections"} for r in results
        ]
        with open(os.path.join(OUT_DIR, "_extraction_report.json"), "w",
                  encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)
        print(f"\nwrote {OUT_DIR}")
    else:
        print("\nDRY RUN -- nothing written to disk.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
