"""
chunk_records.py — turn the knowledge base into embedding-ready chunks.

Despite what the output directory is called, this builds no database and
opens no connection. It reads knowledge_base/ and writes JSONL text files;
loading them into Qdrant (or anything else) is a separate step.

Rebuilds from the canonical knowledge_base/ layer rather than from
vector_db/records/*.jsonl, because the embedding layer drops fields we need
(data_quality_flag, content_note, possible_duplicate_of, case_details).

Pipeline:
  1. structure-aware statute chunking (~512 token budget)
  2. Qdrant payload prep — native arrays, explicit nulls + has_<field> flags
  3. caselaw text enrichment (facts / issues / reasoning / principles)
  4. quality flags surfaced into the payload
  5. (cid:N) glyph cleanup, flag retained where a glyph can't be resolved
  6. duplicate handling — byte-identical deduped, near-duplicates kept + flagged
  7. hybrid lexical layer (BM25 sparse text + exact citation keys)

Output: knowledge_base/vector_db/records/{statutes,caselaw,crossreference}.jsonl
    knowledge_base/vector_db/records/report.json

Usage:
  python scripts/chunk_records.py --dry-run
  python scripts/chunk_records.py --run
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import re
import statistics
import unicodedata
import uuid
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KB = os.path.join(ROOT, "knowledge_base")
OUT = os.path.join(KB, "vector_db", "records")

# Namespace for deterministic Qdrant point ids. Qdrant point ids must be
# uint64 or UUID -- "stat:abc123#c0" is not a legal point id, so the readable
# id lives in the payload as record_id and the point id is a UUID5 of it.
NS = uuid.UUID("6f9619ff-8b86-d011-b42d-00c04fc964ff")

TOKEN_BUDGET = 512          # primary chunk budget
HEADER_RESERVE = 48         # tokens reserved for the re-prepended header
MIN_CHUNK_TOKENS = 40       # below this, merge forward rather than emit

CID_RE = re.compile(r"\(cid:(\d+)\)")

# Structural split markers for Indian statutory drafting, most-specific first.
# A marker only splits when it starts a line or follows sentence-final
# punctuation, so "(2)" inside a cross-reference like "under section 5(2)"
# does not trigger a split.
UNIT_MARKERS = [
    ("subsection", r"\(\d+[A-Za-z]?\)"),
    ("clause", r"\([a-z]{1,3}\)"),
    ("subclause", r"\((?:x{0,3})(?:ix|iv|v?i{0,3})\)"),
    ("proviso", r"Provided\s+(?:further\s+|also\s+)?that"),
    ("explanation", r"Explanation\s*\d*\s*[.—:-]"),
    ("exception", r"Exception\s*\d*\s*[.—:-]"),
    ("illustration", r"Illustrations?\s*[.—:-]"),
]
_MARKER_ALT = "|".join(f"(?:{pat})" for _, pat in UNIT_MARKERS)
SPLIT_RE = re.compile(
    r"(?:(?<=\n)|(?<=[.;:—]\s)|(?<=[.;:—]\n)|^)\s*(?=(?:%s))" % _MARKER_ALT
)
SENT_RE = re.compile(r"(?<=[.;:])\s+(?=[A-Z(])")

# Statute abbreviations that appear in citizen-phrased queries but are not in
# act_abbrev, mapped onto the abbrev the corpus actually uses.
ABBREV_ALIASES = {
    "IPC": ["IPC", "Indian Penal Code", "Penal Code"],
    "CrPC": ["CrPC", "CRPC", "Criminal Procedure Code", "Code of Criminal Procedure"],
    "BNS": ["BNS", "Bharatiya Nyaya Sanhita", "Nyaya Sanhita"],
    "BNSS": ["BNSS", "Bharatiya Nagarik Suraksha Sanhita", "Nagarik Suraksha Sanhita"],
    "BSA": ["BSA", "Bharatiya Sakshya Adhiniyam", "Sakshya Adhiniyam"],
    "COI": ["COI", "Constitution", "Constitution of India"],
    "CPA1986": ["CPA", "CPA 1986", "Consumer Protection Act"],
    "CPA2019": ["CPA", "CPA 2019", "Consumer Protection Act"],
    "PWDVA": ["PWDVA", "DV Act", "Domestic Violence Act"],
    "HMA": ["HMA", "Hindu Marriage Act"],
    "SMA": ["SMA", "Special Marriage Act"],
    "TPA": ["TPA", "Transfer of Property Act"],
    "DRCA": ["DRCA", "Delhi Rent Act", "Delhi Rent Control Act"],
    "MRCA": ["MRCA", "Maharashtra Rent Act", "Maharashtra Rent Control Act"],
    "WBPTA": ["WBPTA", "West Bengal Premises Tenancy Act", "West Bengal Rent Act"],
    "TNRRRLT": ["TNRRRLT", "Tamil Nadu Rent Act",
                "Tamil Nadu Regulation of Rights and Responsibilities of "
                "Landlords and Tenants Act"],
}

# 15 of 21 documents carry no act_abbrev in the KB, which would leave 669
# sections with no exact-citation path ("CPA section 35", "TPA 106"). Derived
# here rather than written back into the KB; payload records which is which.
DERIVED_ABBREV = {
    "the consumer protection act, 1986": "CPA1986",
    "the consumer protection act, 2019": "CPA2019",
    "the protection of women from domestic violence act, 2005": "PWDVA",
    "the hindu marriage act, 1955": "HMA",
    "the special marriage act, 1954": "SMA",
    "the transfer of property act, 1882": "TPA",
    "the delhi rent control act, 1958": "DRCA",
    "the maharashtra rent control act, 1999": "MRCA",
    "the west bengal premises tenancy act, 1997": "WBPTA",
}

# The unit of citation differs by document type — nobody searches for
# "Constitution section 21".
SECTION_WORD = {"constitution": "Article", "rules": "rule"}


# --------------------------------------------------------------------------
# token counting
# --------------------------------------------------------------------------

EMBED_MODEL = "BAAI/bge-m3"


def _load_token_counter():
    """The embedding model's own tokenizer if available, else a fallback.
    Chunk budgets are only meaningful against the tokenizer that will
    actually truncate, so the model's own comes first."""
    try:
        from transformers import AutoTokenizer
        tok = AutoTokenizer.from_pretrained(EMBED_MODEL)
        return ((lambda s: len(tok.encode(s, add_special_tokens=False))),
                f"hf/{EMBED_MODEL}")
    except Exception:
        pass
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        return (lambda s: len(enc.encode(s))), "tiktoken/cl100k_base"
    except Exception:
        pass

    def estimate(s: str) -> int:
        # Legal English runs token-dense (numbers, section refs, punctuation).
        # max of the two standard heuristics is the safer side to be wrong on.
        return max(len(s) // 4, int(len(s.split()) * 1.35)) or 1

    return estimate, "estimate(no tokenizer installed)"


count_tokens, TOKENIZER_NAME = _load_token_counter()


# --------------------------------------------------------------------------
# io helpers
# --------------------------------------------------------------------------

def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def write_jsonl(path, records):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    return len(records)


def point_id(record_id: str) -> str:
    return str(uuid.uuid5(NS, record_id))


def stat_base_id(doc_id, section_number) -> str:
    """Same id scheme as kb_builder.py, so parent ids stay stable."""
    h = hashlib.sha1(f"{doc_id}|{section_number}".encode()).hexdigest()[:16]
    return "stat:" + h


# --------------------------------------------------------------------------
# step 5 — glyph cleanup
# --------------------------------------------------------------------------

# Only glyph codes whose identity is established from context are mapped.
#
# (cid:9) — all 10 occurrences (West Bengal) sit at a marginal-note column
# break, e.g. "...Code of Criminal Procedure, 1973.(cid:9) The Controller
# shall be deemed...". Glyph 9 is the tab in the font's encoding and the
# surrounding text reads correctly with whitespace substituted.
#
# (cid:3468) and neighbours (Tamil Nadu amendment) are high-range Tamil font
# glyphs. The README already records Tamil-script text as unrecoverable from
# a legacy non-Unicode font, so these are NOT guessed — they become U+FFFD
# and the record keeps its data_quality_flag.
CID_MAP = {"9": " "}


def clean_glyphs(text: str):
    """Returns (cleaned_text, n_resolved, n_unresolved)."""
    resolved = unresolved = 0

    def sub(m):
        nonlocal resolved, unresolved
        code = m.group(1)
        if code in CID_MAP:
            resolved += 1
            return CID_MAP[code]
        unresolved += 1
        return "�"  # explicit "character could not be decoded"

    return CID_RE.sub(sub, text), resolved, unresolved


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("­", "").replace("​", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# --------------------------------------------------------------------------
# step 7 — lexical layer
# --------------------------------------------------------------------------

def resolve_abbrev(rec):
    """(abbrev, source) — KB value if present, else derived from act name."""
    if rec.get("act_abbrev"):
        return rec["act_abbrev"], "kb"
    name = str(rec.get("act_name") or "").lower().strip()
    if name in DERIVED_ABBREV:
        return DERIVED_ABBREV[name], "derived"
    if "tamil nadu regulation of rights" in name:
        return "TNRRRLT", "derived"
    return None, None


def _section_parts(section_number):
    n = str(section_number).strip()
    if not n or n.startswith("("):
        return []
    parts = [n]
    m = re.match(r"^(\d+[A-Za-z]?)\(", n)     # "103(2)" is also cited as "103"
    if m:
        parts.append(m.group(1))
    return parts


def section_variants(abbrev, section_number, word="section"):
    """Surface forms a user might type for one citation. Kept deliberately
    small — BM25 works on unigrams, so repeating "IPC section 302" sixteen
    ways only inflates term frequency and distorts ranking."""
    parts = _section_parts(section_number)
    if not parts or not abbrev:
        return []
    aliases = ABBREV_ALIASES.get(abbrev, [abbrev])
    out = [word]
    out += aliases                             # each alias once
    out += parts                               # each number form once
    out += [f"{aliases[0]} {word} {parts[0]}"]  # one canonical phrase
    return out


def citation_keys(abbrev, section_number):
    """Normalized exact-match keys for a Qdrant keyword payload index."""
    parts = _section_parts(section_number)
    if not parts or not abbrev:
        return []
    keys = set()
    for a in set(ABBREV_ALIASES.get(abbrev, [])) | {abbrev}:
        for p in parts:
            keys.add(f"{a.lower().replace(' ', '_').replace('.', '')}:{p.lower()}")
    return sorted(keys)


_ALIAS_LOOKUP = {a.lower(): ab for ab, al in ABBREV_ALIASES.items() for a in al}
# longest alias first, so "Consumer Protection Act" wins over "CPA"
_ALIAS_RE = re.compile(
    r"\b(" + "|".join(re.escape(a) for a in
                      sorted(_ALIAS_LOOKUP, key=len, reverse=True)) + r")\b",
    re.IGNORECASE)
_NUM_RE = re.compile(
    r"\b(?:s\.?|sec\.?|section|article|art\.?)\s*(\d+[A-Za-z]?(?:\(\d+\))?)"
    r"|\b(\d{1,3}[A-Za-z]?(?:\(\d+\))?)\b")


def parse_citation(query: str):
    """Detect a citation in a user query -> candidate citation_keys.

    Retrieval-time counterpart to citation_keys(); hybrid search applies the
    result as a hard payload filter when it fires. Statute name and section
    number are found independently rather than by one positional pattern, so
    filler words between them ("what does IPC section 420 say") don't break it.
    """
    nm = _NUM_RE.search(query)
    if not nm:
        return []
    num = nm.group(1) or nm.group(2)

    am = _ALIAS_RE.search(query)
    abbrev = _ALIAS_LOOKUP.get(am.group(1).lower()) if am else None
    if abbrev is None and re.search(r"\bart(?:icle)?\b", query, re.IGNORECASE):
        abbrev = "COI"            # "Article 21" means the Constitution
    if abbrev is None:
        # no statute named -> bare number, caller ranks candidates across acts
        return [f"*:{num.lower()}"]
    # "CPA" is ambiguous between the 1986 and 2019 Acts: return both and let
    # the regime_tag filter or the dense score break the tie.
    abbrevs = ([a for a in ("CPA1986", "CPA2019")]
               if abbrev.startswith("CPA") and am and
               am.group(1).lower() in ("cpa", "consumer protection act")
               else [abbrev])
    keys = []
    for a in abbrevs:
        keys += citation_keys(a, num)
    return sorted(set(keys))


def lexical_tokens(s: str):
    return [t for t in re.findall(r"[a-z0-9]+", s.lower()) if t]


# --------------------------------------------------------------------------
# step 1 — structure-aware chunking
# --------------------------------------------------------------------------

def split_units(text: str):
    """Split a section body into atomic structural units."""
    units = [u.strip() for u in SPLIT_RE.split(text) if u and u.strip()]
    return units or ([text.strip()] if text.strip() else [])


def hard_split(unit: str, budget: int):
    """A single structural unit that still busts the budget: sentences, then
    a character window as the last resort."""
    if count_tokens(unit) <= budget:
        return [unit]
    out, buf = [], ""
    for sent in SENT_RE.split(unit):
        cand = (buf + " " + sent).strip()
        if buf and count_tokens(cand) > budget:
            out.append(buf)
            buf = sent
        else:
            buf = cand
    if buf:
        out.append(buf)
    final = []
    for piece in out:
        if count_tokens(piece) <= budget:
            final.append(piece)
            continue
        # last resort: character window, shrunk until it actually fits — the
        # chars-per-token ratio is not constant across legal text
        step = budget * 4
        while True:
            windows, pos = [], 0
            while pos < len(piece):
                end = min(pos + step, len(piece))
                if end < len(piece):                  # snap to a word boundary
                    cut = piece.rfind(" ", pos + step // 2, end)
                    if cut > pos:
                        end = cut
                windows.append(piece[pos:end].strip())
                pos = end
            windows = [w for w in windows if w]
            if step <= 200 or all(count_tokens(w) <= budget for w in windows):
                break
            step = int(step * 0.85)
        final += windows
    return [f for f in final if f]


def chunk_section(text: str, budget: int):
    """Pack structural units into chunks under the budget. No overlap: the
    units are self-contained by construction, and the header carries the
    identifying context instead."""
    units = split_units(text)
    packed, buf = [], ""
    for unit in units:
        for piece in hard_split(unit, budget):
            cand = (buf + "\n" + piece).strip() if buf else piece
            if buf and count_tokens(cand) > budget:
                packed.append(buf)
                buf = piece
            else:
                buf = cand
    if buf:
        packed.append(buf)
    # fold a runt tail back into its predecessor, but never past the budget
    if (len(packed) > 1 and count_tokens(packed[-1]) < MIN_CHUNK_TOKENS
            and count_tokens(packed[-2]) + count_tokens(packed[-1]) <= budget):
        tail = packed.pop()
        packed[-1] = packed[-1] + "\n" + tail
    return packed or [""]


TITLE_MAX_CHARS = 120


def unreadable(text: str) -> bool:
    """Legacy non-Unicode font output, e.g. the Tamil Nadu rule 12 title:
    'yc f f r yc o o y y b b ss ss nane ] nane )...'.

    Deliberately narrow — genuine short titles like 'No inducement to be
    offered' score 0.60 on the short-token ratio, so length is required too.
    Exactly one title in 3,282 trips this; no body text does.
    """
    toks = [t for t in re.findall(r"\S+", text or "") if any(c.isalpha() for c in t)]
    if len(toks) < 8 or len(text) <= TITLE_MAX_CHARS:
        return False
    return sum(1 for t in toks if len(t) <= 2) / len(toks) >= 0.70


def build_header(rec, abbrev, idx, total):
    word = SECTION_WORD.get(rec.get("document_type"), "Section")
    label = rec.get("section_label") or f"{word} {rec.get('section_number')}"
    act = rec.get("act_name")
    head = f"{act} ({abbrev}) — {label}." if abbrev else f"{act} — {label}."
    title = rec.get("section_title")
    # The header is repeated on every chunk, so a damaged or runaway title
    # would be embedded N times and eat the token budget. The full value is
    # kept verbatim in the payload either way (per the leave-titles-as-is call).
    if title and unreadable(title):
        title = None
    elif title and len(title) > TITLE_MAX_CHARS:
        title = title[:TITLE_MAX_CHARS].rsplit(" ", 1)[0] + "…"
    if title:
        head += f" {title}"
    path = heading_path(rec)
    if path:
        head += f" [{path}]"
    if total > 1:
        head += f" (part {idx + 1} of {total})"
    return head


def heading_path(rec):
    return " > ".join(x for x in [rec.get("part"), rec.get("chapter_heading"),
                                  rec.get("chapter_subheading")] if x) or None


def nullable(payload: dict, fields):
    """Explicit null + has_<field> companion flag for cheap presence filters."""
    for f in fields:
        v = payload.get(f)
        present = v is not None and v != "" and v != []
        payload[f] = v if present else None
        payload[f"has_{f}"] = present
    return payload


# --------------------------------------------------------------------------
# statutes
# --------------------------------------------------------------------------

def prepare_statutes(report):
    out = []
    stats = {"docs": 0, "sections_in": 0, "sections_empty": 0, "chunks": 0,
             "sections_chunked": 0, "glyphs_resolved": 0, "glyphs_unresolved": 0,
             "records_with_glyphs": 0, "flagged_quality": 0, "flagged_note": 0,
             "headers_over_reserve": 0, "no_citation_key": 0,
             "abbrev_derived": 0, "abbrev_missing": 0,
             "unreadable_titles": 0}
    sizes = []
    per_section_chunks = []

    for path in sorted(glob.glob(os.path.join(KB, "statutes", "*", "*.json"))):
        recs = load(path)
        stats["docs"] += 1
        for rec in recs:
            stats["sections_in"] += 1
            raw = (rec.get("section_text") or "").strip()
            if not raw:
                stats["sections_empty"] += 1
                continue

            # Titles carry glyph damage too — one West Bengal record has its
            # only (cid:N) in the title, which a body-only pass would miss and
            # which lands in the embedded header.
            cleaned, n_res, n_unres = clean_glyphs(raw)
            title, t_res, t_unres = clean_glyphs(rec.get("section_title") or "")
            rec = dict(rec, section_title=normalize_text(title) or None)
            n_res, n_unres = n_res + t_res, n_unres + t_unres
            if n_res or n_unres:
                stats["records_with_glyphs"] += 1
                stats["glyphs_resolved"] += n_res
                stats["glyphs_unresolved"] += n_unres
            body = normalize_text(cleaned)

            # Step 5: the flag survives only if a glyph is still unresolved,
            # or the KB already carried a flag for another reason.
            dq = rec.get("data_quality_flag")
            if unreadable(rec.get("section_title") or ""):
                stats["unreadable_titles"] += 1
                dq = ((dq + "; ") if dq else "") + (
                    "section_title is legacy non-Unicode font output and is "
                    "not readable; omitted from the embedded header, retained "
                    "verbatim in this payload")
            if n_unres:
                dq = (dq or "contains unmapped PDF glyph codes") + \
                     f" ({n_unres} character(s) still undecodable after cleanup)"
            elif n_res and dq:
                dq = None  # every glyph in this record was resolved

            base = stat_base_id(rec.get("doc_id"), rec.get("section_number"))
            abbrev, abbrev_src = resolve_abbrev(rec)
            secno = rec.get("section_number")

            # The header is re-prepended to every chunk, so the body budget is
            # whatever the header leaves. Measured per section, not assumed:
            # act names here run to 100+ characters.
            hdr_cost = count_tokens(build_header(rec, abbrev, 98, 99))
            budget = max(TOKEN_BUDGET - hdr_cost, MIN_CHUNK_TOKENS)
            if hdr_cost > HEADER_RESERVE:
                stats["headers_over_reserve"] += 1

            chunks = chunk_section(body, budget)
            per_section_chunks.append(len(chunks))
            if len(chunks) > 1:
                stats["sections_chunked"] += 1

            word = SECTION_WORD.get(rec.get("document_type"), "section")
            lex = " ".join(section_variants(abbrev, secno, word) +
                           [str(rec.get("act_name") or ""),
                            str(rec.get("section_title") or "")])
            ckeys = citation_keys(abbrev, secno)
            if abbrev and not ckeys:
                stats["no_citation_key"] += 1

            for i, chunk in enumerate(chunks):
                header = build_header(rec, abbrev, i, len(chunks))
                text = f"{header}\n{chunk}".strip()
                rid = base if len(chunks) == 1 else f"{base}#c{i}"
                sizes.append(count_tokens(text))

                payload = {
                    "record_id": rid,
                    "record_type": "statute_section",
                    "parent_id": base,
                    "chunk_index": i,
                    "chunk_count": len(chunks),
                    "act_name": rec.get("act_name"),
                    "act_abbrev": abbrev,
                    "act_abbrev_source": abbrev_src,
                    "act_year": rec.get("act_year"),
                    "section_number": secno,
                    "section_title": rec.get("section_title"),
                    "heading_path": heading_path(rec),
                    "domain_tags": rec.get("domain_tags") or [],
                    "jurisdiction": rec.get("jurisdiction"),
                    "regime_tag": rec.get("regime_tag"),
                    "document_type": rec.get("document_type"),
                    "citation_keys": ckeys,
                    "extraction_confidence": rec.get("extraction_confidence"),
                    "data_quality_flag": dq,
                    "content_note": rec.get("content_note"),
                    "source": rec.get("source"),
                    "source_url": rec.get("source_url"),
                    "source_file": rec.get("source_file"),
                    "license": rec.get("license"),
                }
                if dq:
                    stats["flagged_quality"] += 1
                if rec.get("content_note"):
                    stats["flagged_note"] += 1
                if abbrev_src == "derived":
                    stats["abbrev_derived"] += 1
                elif abbrev is None:
                    stats["abbrev_missing"] += 1
                nullable(payload, ["section_title", "heading_path",
                                   "data_quality_flag", "content_note",
                                   "source_url"])
                out.append({"id": point_id(rid), "text": text,
                            "lexical_text": f"{lex} {chunk}", "payload": payload})

    stats["chunks"] = len(out)
    report["statutes"] = stats
    report["statute_chunk_tokens"] = size_summary(sizes)
    report["statute_chunks_per_section"] = dict(
        sorted(Counter(per_section_chunks).items()))
    return out


def size_summary(sizes):
    if not sizes:
        return {}
    s = sorted(sizes)
    pick = lambda q: s[min(len(s) - 1, int(len(s) * q))]
    return {"n": len(s), "min": s[0], "p50": pick(.5), "p90": pick(.9),
            "p99": pick(.99), "max": s[-1], "mean": round(statistics.mean(s), 1),
            "over_512": sum(1 for x in s if x > 512)}


# --------------------------------------------------------------------------
# caselaw
# --------------------------------------------------------------------------

def case_text_old(c):
    """kb_builder.py's version, kept for the before/after comparison."""
    return (f"{c['title']} ({c['court']}, {c['date']}). "
            f"Outcome: {c['outcome']}.\n{c['summary']}").strip()


def case_text_new(c):
    d = c.get("case_details") or {}
    parts = [f"{c['title']} ({c['court']}, {c['date']}). "
             f"Outcome: {c['outcome']}."]
    if c.get("outcome_detail"):
        parts.append(f"Outcome detail: {c['outcome_detail']}")
    if c.get("summary"):
        parts.append(f"Summary: {c['summary']}")
    if d.get("facts"):
        parts.append(f"Facts: {d['facts']}")
    if d.get("legal_issues"):
        parts.append(f"Legal issues: {as_text(d['legal_issues'])}")
    if d.get("judgment_reason"):
        parts.append(f"Reasoning: {d['judgment_reason']}")
    if d.get("legal_principles_discussed"):
        parts.append(f"Principles: {as_text(d['legal_principles_discussed'])}")
    if c.get("ratio_decidendi"):
        parts.append(f"Ratio: {c['ratio_decidendi']}")
    return normalize_text("\n".join(parts))


def as_text(v):
    if isinstance(v, list):
        return "; ".join(str(x) for x in v)
    return str(v)


def prepare_caselaw(report):
    cases = load(os.path.join(KB, "caselaw", "criminal_law",
                              "indianbail_1200.json"))
    stats = {"in": len(cases), "deduped": 0, "possible_duplicate_flagged": 0,
             "empty_cited_sections": 0, "principles_present": 0}

    # Step 6: byte-identical text -> index one, record the other as deduped_from.
    by_text = defaultdict(list)
    for c in cases:
        key = re.sub(r"\W+", " ", case_text_new(c).lower()).strip()
        by_text[key].append(c)
    dropped = {}
    for group in by_text.values():
        if len(group) > 1:
            group.sort(key=lambda c: c["case_id"])
            keep, rest = group[0], group[1:]
            dropped[keep["case_id"]] = [c["case_id"] for c in rest]
            for c in rest:
                c["_dropped_for"] = keep["case_id"]
                stats["deduped"] += 1

    out, samples = [], []
    for c in cases:
        if c.get("_dropped_for"):
            continue
        d = c.get("case_details") or {}
        new = case_text_new(c)
        cited = [f"{s['statute']} s.{s['section']}"
                 for s in (c.get("cited_sections") or []) if s.get("section")]
        if not cited:
            stats["empty_cited_sections"] += 1
        if d.get("legal_principles_discussed"):
            stats["principles_present"] += 1
        if c.get("possible_duplicate_of"):
            stats["possible_duplicate_flagged"] += 1

        ckeys, lex = [], [c["title"], new]
        for s in (c.get("cited_sections") or []):
            if not s.get("section"):
                continue
            ab = statute_abbrev_for(s.get("statute"))
            ckeys += citation_keys(ab, s["section"])
            # one canonical form per citation — a case citing 12 sections
            # must not outweigh the section itself on a citation query
            lex.append(f"{ab} {s['section']}")

        rid = f"case:{c['case_id']}"
        payload = {
            "record_id": rid,
            "record_type": "case",
            "case_id": c["case_id"],
            "title": c["title"],
            "court": c["court"],
            "court_level": c["court_level"],
            "region": c.get("region"),
            "date": c["date"],
            "year": c["year"],
            "outcome": c["outcome"],
            "crime_type": d.get("crime_type"),
            "bail_type": d.get("bail_type"),
            "is_landmark": bool(d.get("is_landmark")),
            "is_bail_cancellation": bool(d.get("is_bail_cancellation")),
            "domain_tags": c.get("domain_tags") or [],
            "cited_sections": cited,
            "citation_keys": sorted(set(ckeys)),
            "possible_duplicate_of": c.get("possible_duplicate_of"),
            "deduped_from": dropped.get(c["case_id"]),
            "data_quality_flag": None,
            "source": c.get("source_dataset"),
            "source_url": c.get("source_url"),
            "source_record": c.get("source_record"),
            "license": c.get("license"),
        }
        nullable(payload, ["region", "crime_type", "bail_type",
                           "cited_sections", "possible_duplicate_of",
                           "deduped_from", "data_quality_flag"])
        out.append({"id": point_id(rid), "text": new,
                    "lexical_text": " ".join(lex), "payload": payload})
        if len(samples) < 3:
            samples.append({"case_id": c["case_id"], "title": c["title"],
                            "old": case_text_old(c), "new": new})

    stats["out"] = len(out)
    report["caselaw"] = stats
    report["caselaw_tokens"] = {
        "old": size_summary([count_tokens(case_text_old(c)) for c in cases
                             if not c.get("_dropped_for")]),
        "new": size_summary([count_tokens(r["text"]) for r in out]),
    }
    report["_case_samples"] = samples
    return out


ABBREV_BY_NAME = {
    "indian penal code, 1860": "IPC",
    "code of criminal procedure, 1973": "CrPC",
    "bharatiya nyaya sanhita, 2023": "BNS",
    "bharatiya nagarik suraksha sanhita, 2023": "BNSS",
    "bharatiya sakshya adhiniyam, 2023": "BSA",
}


def statute_abbrev_for(name):
    if not name:
        return None
    key = str(name).lower().strip().removeprefix("the ")
    return ABBREV_BY_NAME.get(key, str(name).strip())


# --------------------------------------------------------------------------
# crossreference
# --------------------------------------------------------------------------

def prepare_crossref(report):
    x = load(os.path.join(KB, "crossreference", "ipc_bns_mapping.json"))
    out = []
    for e in x["entries"]:
        ss, sn = e.get("source_statute"), e.get("source_section")
        ts, tn = e.get("target_statute"), e.get("target_section")
        if sn and tn:
            head = f"{ss} section {sn} corresponds to {ts} section {tn}."
        elif not sn:
            head = f"{ts} section {tn} is a new provision with no predecessor."
        else:
            head = f"{ss} section {sn} has no counterpart in the new code."
        text = f"{head} Relation: {e.get('relation')}. {e.get('note') or ''}".strip()

        rid = "xref:" + hashlib.sha1(f"{ss}|{sn}|{tn}".encode()).hexdigest()[:16]
        ckeys = citation_keys(ss, sn) + citation_keys(ts, tn)
        lex = section_variants(ss, sn) + section_variants(ts, tn)
        payload = {
            "record_id": rid,
            "record_type": "crossreference",
            "source_statute": ss, "source_section": sn,
            "target_statute": ts, "target_section": tn,
            "relation": e.get("relation"),
            "confidence": e.get("confidence"),
            "caselaw_citations": e.get("caselaw_citations"),
            "source_section_verified_in_corpus": e.get("source_section_verified_in_corpus"),
            "target_section_verified_in_corpus": e.get("target_section_verified_in_corpus"),
            "domain_tags": ["criminal_law"],
            "citation_keys": sorted(set(ckeys)),
            "verification_status": x.get("verification_status"),
            "content_note": x.get("caveat"),
        }
        nullable(payload, ["source_statute", "source_section",
                           "target_statute", "target_section", "content_note"])
        out.append({"id": point_id(rid), "text": text,
                    "lexical_text": " ".join(lex + [text]), "payload": payload})

    report["crossreference"] = {
        "n": len(out),
        "null_source": sum(1 for r in out if not r["payload"]["has_source_section"]),
        "null_target": sum(1 for r in out if not r["payload"]["has_target_section"]),
    }
    return out


# --------------------------------------------------------------------------
# step 7 — verify the lexical layer answers citation queries
# --------------------------------------------------------------------------

def label(p):
    if p["record_type"] == "statute_section":
        n = f"{p.get('act_abbrev') or '?'} s.{p.get('section_number')}"
        return n + (f"#c{p['chunk_index']}" if p["chunk_count"] > 1 else "")
    return f"{p['record_type']}:{p.get('case_id') or p.get('record_id')}"


def verify_lexical(records, report):
    """BM25 ranks; it does not guarantee exact match. So the citation path is
    checked as it will actually run at query time:

      1. parse_citation() fires on the query  -> hard payload filter on
         citation_keys. This is the guarantee.
      2. BM25 over the sparse vector, scoped to statute_section, is the
         ranking fallback for citation-shaped queries the parser misses.
      3. unscoped BM25 is reported for information only — case records
         legitimately compete there, which is why (1) exists.
    """
    import math
    docs = [(r["payload"], lexical_tokens(r["lexical_text"])) for r in records]
    N = len(docs)
    df = Counter()
    for _, toks in docs:
        for t in set(toks):
            df[t] += 1
    avgdl = statistics.mean(len(t) for _, t in docs)

    def bm25(qtoks, only=None, k1=1.5, b=0.75):
        scored = []
        for payload, toks in docs:
            if only and payload["record_type"] != only:
                continue
            tf = Counter(toks)
            dl = len(toks)
            s = 0.0
            for q in qtoks:
                if q not in tf:
                    continue
                idf = math.log(1 + (N - df[q] + .5) / (df[q] + .5))
                s += idf * (tf[q] * (k1 + 1)) / (tf[q] + k1 * (1 - b + b * dl / avgdl))
            if s:
                scored.append((s, payload))
        scored.sort(key=lambda x: -x[0])
        return scored[:3]

    # expected: the key the filter must contain, or "*" when the query names
    # no statute (returning candidates across acts is the correct answer
    # there, not a miss), or None for a non-citation control.
    queries = [
        ("IPC 302", "ipc:302"),
        ("section 302", "*"),
        ("s. 302 IPC", "ipc:302"),
        ("what does IPC section 420 say", "ipc:420"),
        ("BNS 103", "bns:103"),
        ("CrPC 167 default bail", "crpc:167"),
        ("Article 21", "coi:21"),
        ("TPA section 106", "tpa:106"),
        ("CPA section 35", "cpa2019:35"),  # ambiguous 1986/2019 by design
        ("Indian Penal Code section 375", "ipc:375"),
        ("punishment for murder", None),      # non-citation control
    ]
    results = []
    for query, expected in queries:
        parsed = parse_citation(query)
        hit_keys = [k for k in parsed if not k.startswith("*:")]
        # step 1: hard filter
        if hit_keys:
            filtered = [p for p, _ in docs
                        if p["record_type"] == "statute_section"
                        and set(hit_keys) & set(p.get("citation_keys") or [])]
        elif parsed:  # bare number, no statute named -> rank across acts
            num = parsed[0].split(":", 1)[1]
            filtered = [p for p, _ in docs
                        if p["record_type"] == "statute_section"
                        and any(k.endswith(":" + num)
                                for k in (p.get("citation_keys") or []))]
        else:
            filtered = []
        parents = {p["parent_id"] for p in filtered}
        results.append({
            "query": query,
            "citation_detected": bool(parsed),
            "parsed_keys": parsed,
            "expected_key": expected,
            "expected_key_matched": (
                None if expected is None
                else (parsed and parsed[0].startswith("*:")) if expected == "*"
                else expected in parsed),
            "filter_hits": len(filtered),
            "filter_distinct_sections": len(parents),
            "filter_top": sorted({label(p) for p in filtered})[:4],
            "bm25_statutes_top": [label(p) for _, p in
                                  bm25(lexical_tokens(query), "statute_section")],
            "bm25_unscoped_top": [label(p) for _, p in bm25(lexical_tokens(query))],
        })
    report["lexical_verification"] = results
    return results


# --------------------------------------------------------------------------
# step 9 — embedding cost / time estimate
# --------------------------------------------------------------------------

def embed_estimate(all_records, report):
    toks = [count_tokens(r["text"]) for r in all_records]
    total = sum(toks)
    report["embedding_estimate"] = {
        "records": len(all_records),
        "total_tokens": total,
        "tokenizer": TOKENIZER_NAME,
        "local_bge_m3_cpu_minutes": round(len(all_records) / 12 / 60, 1),
        "local_bge_m3_gpu_minutes": round(len(all_records) / 220 / 60, 1),
        "openai_text_embedding_3_small_usd": round(total / 1e6 * 0.02, 3),
        "voyage_law_2_usd": round(total / 1e6 * 0.12, 3),
    }


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true",
                   help="report counts and samples, write nothing")
    g.add_argument("--run", action="store_true",
                   help="write knowledge_base/vector_db/records/")
    args = ap.parse_args()

    report = {"tokenizer": TOKENIZER_NAME, "token_budget": TOKEN_BUDGET}
    statutes = prepare_statutes(report)
    cases = prepare_caselaw(report)
    xref = prepare_crossref(report)
    everything = statutes + cases + xref
    verify_lexical(everything, report)
    embed_estimate(everything, report)

    ids = [r["id"] for r in everything]
    report["totals"] = {"records": len(everything), "duplicate_point_ids":
                        len(ids) - len(set(ids))}

    print_report(report, statutes, cases, args.dry_run)

    if args.run:
        write_jsonl(os.path.join(OUT, "statutes.jsonl"), statutes)
        write_jsonl(os.path.join(OUT, "caselaw.jsonl"), cases)
        write_jsonl(os.path.join(OUT, "crossreference.jsonl"), xref)
        clean = {k: v for k, v in report.items() if not k.startswith("_")}
        with open(os.path.join(OUT, "report.json"), "w", encoding="utf-8") as fh:
            json.dump(clean, fh, indent=2, ensure_ascii=False)
        print(f"\nwrote {len(everything)} records -> {OUT}")


def print_report(report, statutes, cases, dry):
    b = lambda s: f"\n{'=' * 70}\n{s}\n{'=' * 70}"
    print(b("1. STATUTE CHUNKING"))
    s = report["statutes"]
    print(f"  docs {s['docs']}  sections in {s['sections_in']}  "
          f"empty skipped {s['sections_empty']}")
    print(f"  chunks out {s['chunks']}  (sections that split: {s['sections_chunked']})")
    print(f"  tokenizer: {report['tokenizer']}   budget: {report['token_budget']}")
    t = report["statute_chunk_tokens"]
    print(f"  chunk tokens  min {t['min']}  p50 {t['p50']}  p90 {t['p90']}  "
          f"p99 {t['p99']}  max {t['max']}  mean {t['mean']}")
    print(f"  chunks over 512 tokens: {t['over_512']}")
    print(f"  chunks per section: {report['statute_chunks_per_section']}")
    print(f"  headers costing more than the {HEADER_RESERVE}-token reserve: "
          f"{s['headers_over_reserve']}")
    print(f"  unreadable titles kept out of the header: {s['unreadable_titles']}")
    print(f"  act_abbrev derived / still missing: "
          f"{s['abbrev_derived']} / {s['abbrev_missing']}")

    print(b("2. PREPARED PAYLOAD SAMPLES"))
    for r in [statutes[0], statutes[len(statutes) // 2], cases[0]]:
        print(json.dumps(r["payload"], ensure_ascii=False, indent=2)[:1400])
        print("-" * 70)

    print(b("3. CASELAW ENRICHMENT (before / after)"))
    for smp in report.get("_case_samples", []):
        print(f"\n[{smp['case_id']}] {smp['title'][:70]}")
        print(f"  BEFORE {count_tokens(smp['old']):4d} tok / {len(smp['old']):5d} ch")
        print(f"  AFTER  {count_tokens(smp['new']):4d} tok / {len(smp['new']):5d} ch"
              f"   ({count_tokens(smp['new']) / max(count_tokens(smp['old']), 1):.1f}x)")
        print("  --- after ---")
        print("  " + smp["new"][:900].replace("\n", "\n  "))
    ct = report["caselaw_tokens"]
    print(f"\n  corpus-wide  before p50 {ct['old']['p50']} tok / "
          f"after p50 {ct['new']['p50']} tok")

    print(b("4-6. FLAGS, GLYPHS, DUPLICATES"))
    print(f"  statute chunks carrying data_quality_flag : {s['flagged_quality']}")
    print(f"  statute chunks carrying content_note      : {s['flagged_note']}")
    print(f"  records with (cid:N) glyphs               : {s['records_with_glyphs']}")
    print(f"    glyphs resolved / left undecodable      : "
          f"{s['glyphs_resolved']} / {s['glyphs_unresolved']}")
    c = report["caselaw"]
    print(f"  cases in / out                            : {c['in']} / {c['out']}")
    print(f"    byte-identical deduped (deduped_from)   : {c['deduped']}")
    print(f"    possible_duplicate_of carried through   : "
          f"{c['possible_duplicate_flagged']}")
    print(f"    empty cited_sections (noted, not fixed) : "
          f"{c['empty_cited_sections']}")

    print(b("7. LEXICAL / HYBRID VERIFICATION"))
    print("  path 1 = citation parser + citation_keys payload filter (the guarantee)")
    print("  path 2 = BM25 sparse vector scoped to statutes (ranking fallback)\n")
    for v in report["lexical_verification"]:
        ok = "OK  " if (v["expected_key_matched"] or
                        (v["expected_key"] is None and not v["citation_detected"])) else "CHECK"
        print(f"  [{ok}] {v['query']}")
        print(f"         parsed      : {v['parsed_keys'] or 'no citation detected'}")
        print(f"         filter      : {v['filter_hits']} chunk(s) across "
              f"{v['filter_distinct_sections']} section(s) {v['filter_top']}")
        print(f"         bm25 statute: {v['bm25_statutes_top']}")
        print(f"         bm25 all    : {v['bm25_unscoped_top']}")

    print(b("9. EMBEDDING ESTIMATE"))
    e = report["embedding_estimate"]
    for k, v in e.items():
        print(f"  {k:<38} {v}")

    print(b("TOTALS"))
    print(f"  records: {report['totals']['records']}  "
          f"duplicate point ids: {report['totals']['duplicate_point_ids']}")
    print(f"  crossreference: {report['crossreference']}")
    if dry:
        print("\n(dry run — nothing written)")


if __name__ == "__main__":
    main()
