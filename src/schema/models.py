"""
JusticeCompass — canonical document schema.

Every record that lands in ``knowledge_base/`` passes through one of these models
first. Nothing is written to the deliverable folder unvalidated.

Two primary document types:
  * :class:`StatuteSection` — one section/article of an Act (or of the Constitution)
  * :class:`CaseDocument`   — one judgment/order, stored as citation + short summary

Supporting models (needed by the KB folder structure, not scraped directly):
  * :class:`CrossReferenceEntry` — IPC/CrPC/Evidence Act -> BNS/BNSS/BSA mapping row
  * :class:`Chunk`              — flattened unit written to embeddings_ready/chunks.jsonl
  * :class:`DomainMetadata`     — the metadata.json sitting in every domain folder
  * :class:`BuildManifest`      — knowledge_base/manifest.json

Copyright posture is enforced *here*, not left to the scrapers' good behaviour:
statute text may only be stored when the source licence permits full-text storage,
and case records are hard-capped at ``SUMMARY_MAX_CHARS`` of prose.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import date, datetime, timezone
from enum import Enum
from typing import Annotated, Any, Literal, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    StringConstraints,
    computed_field,
    field_validator,
    model_validator,
)

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

SCHEMA_VERSION = "1.0.0"

#: Hard ceiling on any prose we store for a judgment. Citation + short summary
#: only — see the copyright policy in config.yaml (`copyright_policy`).
SUMMARY_MAX_CHARS = 1200

#: Commencement of the new criminal regime (BNS / BNSS / BSA).
NEW_CRIMINAL_REGIME_COMMENCEMENT = date(2024, 7, 1)

_ZERO_WIDTH = re.compile(r"[​-‏﻿­]")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_MULTI_SPACE = re.compile(r"[ \t]{2,}")
_MULTI_NEWLINE = re.compile(r"\n{3,}")

NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Slug = Annotated[str, StringConstraints(pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$")]


def clean_text(value: str) -> str:
    """Normalise scraped text: NFKC, drop zero-width/control chars, tidy whitespace.

    Deliberately conservative — it never re-wraps or truncates, so section text
    stays byte-comparable across re-runs (which is what dedup and checksums rely on).
    """
    text = unicodedata.normalize("NFKC", value)
    text = _ZERO_WIDTH.sub("", text)
    text = _CONTROL.sub("", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _MULTI_SPACE.sub(" ", text)
    text = _MULTI_NEWLINE.sub("\n\n", text)
    return "\n".join(line.rstrip() for line in text.split("\n")).strip()


def stable_id(*parts: object) -> str:
    """Deterministic 16-hex-char id from the parts that make a document unique.

    Deterministic ids mean a re-run overwrites rather than duplicates, and
    ``--resume`` can tell which documents it already has.
    """
    joined = "|".join(str(p).strip().lower() for p in parts if p is not None)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #


class Domain(str, Enum):
    """The five legal domains. Values double as folder names under
    ``knowledge_base/statutes/`` and ``knowledge_base/caselaw/`` — do not rename
    without updating kb_builder.py."""

    CRIMINAL_LAW = "criminal_law"
    CONSUMER_PROTECTION = "consumer_protection"
    FAMILY_LAW = "family_law"
    TENANCY_PROPERTY = "tenancy_property"
    CONSTITUTIONAL_LAW = "constitutional_law"


class Regime(str, Enum):
    """Old-vs-new criminal law regime.

    ARCHIVED sections are kept, never deleted: decades of case law cite IPC/CrPC/
    Evidence Act section numbers, and a retrieval hit on "IPC 498A" must resolve.
    """

    CURRENT = "current"  # in force today (BNS/BNSS/BSA and all non-criminal Acts)
    ARCHIVED = "archived"  # repealed but retained for historical case-law lookup
    UNAFFECTED = "unaffected"  # outside the 2023 criminal overhaul entirely


class StatuteFamily(str, Enum):
    IPC = "ipc"  # Indian Penal Code, 1860            -> archived
    CRPC = "crpc"  # Code of Criminal Procedure, 1973 -> archived
    EVIDENCE_ACT = "evidence_act"  # Indian Evidence Act, 1872 -> archived
    BNS = "bns"  # Bharatiya Nyaya Sanhita, 2023
    BNSS = "bnss"  # Bharatiya Nagarik Suraksha Sanhita, 2023
    BSA = "bsa"  # Bharatiya Sakshya Adhiniyam, 2023
    CONSTITUTION = "constitution"
    OTHER = "other"  # CPA 2019, HMA 1955, TPA 1882, state rent Acts, ...


class Jurisdiction(str, Enum):
    UNION = "union"
    STATE = "state"


class CourtLevel(str, Enum):
    SUPREME_COURT = "supreme_court"
    HIGH_COURT = "high_court"
    DISTRICT_COURT = "district_court"
    NCDRC = "ncdrc"  # National Consumer Disputes Redressal Commission
    SCDRC = "scdrc"  # State commission
    DCDRC = "dcdrc"  # District commission
    TRIBUNAL = "tribunal"  # NCLT, rent tribunals, family courts, ...
    OTHER = "other"


class CaseOutcome(str, Enum):
    ALLOWED = "allowed"
    DISMISSED = "dismissed"
    PARTLY_ALLOWED = "partly_allowed"
    REMANDED = "remanded"
    CONVICTED = "convicted"
    ACQUITTED = "acquitted"
    BAIL_GRANTED = "bail_granted"
    BAIL_REJECTED = "bail_rejected"
    SETTLED = "settled"
    DIRECTIONS_ISSUED = "directions_issued"
    UNKNOWN = "unknown"


class LicenseUsage(str, Enum):
    """What we are actually allowed to do with a source.

    UNVERIFIED is the default for anything we have not confirmed by reading the
    licence ourselves; build_kb.py refuses to pull an UNVERIFIED or RESEARCH_ONLY
    source unless it is explicitly enabled in config.yaml.
    """

    PUBLIC_DOMAIN = "public_domain"
    COMMERCIAL_OK = "commercial_ok"
    ATTRIBUTION_REQUIRED = "attribution_required"
    SHARE_ALIKE = "share_alike"
    RESEARCH_ONLY = "research_only"
    NO_REDISTRIBUTION = "no_redistribution"
    UNVERIFIED = "unverified"


class RetrievalMethod(str, Enum):
    HTML = "html"
    PDF = "pdf"
    API = "api"
    DATASET = "dataset"  # HuggingFace / Kaggle / GitHub bulk download
    MANUAL = "manual"  # hand-entered (e.g. the static IPC->BNS table)


class ClassificationStatus(str, Enum):
    """ratio_decidendi / obiter_dicta are filled by a later classification step,
    never by the scraper."""

    PENDING = "pending"
    COMPLETE = "complete"
    NOT_APPLICABLE = "not_applicable"


class MappingRelationship(str, Enum):
    """How an old section maps onto the new regime."""

    ONE_TO_ONE = "one_to_one"  # renumbered, substance intact
    MERGED = "merged"  # several old sections -> one new section
    SPLIT = "split"  # one old section -> several new sections
    SUBSTANTIVELY_CHANGED = "substantively_changed"  # renumbered *and* reworded
    NO_EQUIVALENT = "no_equivalent"  # dropped (e.g. s.377 IPC, s.497 IPC)
    NEW_PROVISION = "new_provision"  # no old counterpart at all


# --------------------------------------------------------------------------- #
# Shared sub-models
# --------------------------------------------------------------------------- #


class LicenseInfo(BaseModel):
    """Licence/terms attached to every document, carried through to chunks.

    ``verified_by_human`` is the field that matters: nothing on GitHub or
    HuggingFace is assumed usable until a person has read the terms and flipped
    this to True with a date.
    """

    model_config = ConfigDict(extra="forbid")

    license_id: NonEmptyStr = Field(
        description="SPDX id where one exists, else a local slug "
        "(e.g. 'IN-Copyright-Act-s52', 'CC-BY-4.0', 'unknown')."
    )
    usage: LicenseUsage = LicenseUsage.UNVERIFIED
    full_text_storage_allowed: bool = Field(
        default=False,
        description="May we store the complete text, or only citation + summary?",
    )
    attribution_text: Optional[str] = Field(
        default=None, description="Exact credit line to reproduce, if required."
    )
    verified_by_human: bool = False
    verified_on: Optional[date] = None
    verification_url: Optional[HttpUrl] = Field(
        default=None, description="Where the terms were read."
    )
    notes: Optional[str] = None

    @model_validator(mode="after")
    def _verification_needs_a_date(self) -> "LicenseInfo":
        if self.verified_by_human and self.verified_on is None:
            raise ValueError("verified_by_human=True requires verified_on")
        return self

    @model_validator(mode="after")
    def _unverified_cannot_permit_full_text(self) -> "LicenseInfo":
        if self.full_text_storage_allowed and self.usage is LicenseUsage.UNVERIFIED:
            raise ValueError(
                "full_text_storage_allowed=True is not permitted while usage is "
                "'unverified' — confirm the licence first"
            )
        return self


class Provenance(BaseModel):
    """Where a document came from and how, so any record can be traced back."""

    model_config = ConfigDict(extra="forbid")

    source_name: NonEmptyStr = Field(description="e.g. 'India Code', 'eSCR'.")
    source_url: HttpUrl
    source_id: Optional[str] = Field(
        default=None, description="Key of this source in config.yaml."
    )
    retrieval_method: RetrievalMethod = RetrievalMethod.HTML
    retrieved_at: Optional[datetime] = None
    raw_path: Optional[str] = Field(
        default=None,
        description="Repo-relative path of the untouched capture under data/raw/ "
        "(gitignored; intermediate only).",
    )
    content_sha256: Optional[str] = Field(
        default=None, description="Checksum of the cleaned text, for dedup/drift checks."
    )

    @field_validator("content_sha256")
    @classmethod
    def _checksum_shape(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not re.fullmatch(r"[0-9a-f]{64}", v):
            raise ValueError("content_sha256 must be a lowercase hex sha256 digest")
        return v


class StatuteReference(BaseModel):
    """A pointer to a section, used for 'cited by' links on cases."""

    model_config = ConfigDict(extra="forbid")

    act_short_name: NonEmptyStr  # "BNS", "IPC", "CPA 2019"
    section_number: NonEmptyStr  # "354A", "21", "Article 21"
    statute_family: StatuteFamily = StatuteFamily.OTHER
    doc_id: Optional[str] = Field(
        default=None, description="Resolved StatuteSection.doc_id, when known."
    )


# --------------------------------------------------------------------------- #
# Base document
# --------------------------------------------------------------------------- #


class BaseDocument(BaseModel):
    """Fields shared by every KB document."""

    model_config = ConfigDict(extra="forbid", use_enum_values=False, validate_assignment=True)

    doc_id: str = Field(default="", description="Deterministic; auto-filled if blank.")
    schema_version: str = SCHEMA_VERSION
    domains: list[Domain] = Field(min_length=1, description="At least one domain tag.")
    provenance: Provenance
    license: LicenseInfo
    language: str = Field(default="en", description="ISO 639-1.")
    ingested_at: datetime = Field(default_factory=_utcnow)
    notes: Optional[str] = None

    @field_validator("domains")
    @classmethod
    def _dedupe_domains(cls, v: list[Domain]) -> list[Domain]:
        seen: list[Domain] = []
        for d in v:
            if d not in seen:
                seen.append(d)
        return seen

    def natural_key(self) -> tuple[object, ...]:  # pragma: no cover - overridden
        raise NotImplementedError

    @model_validator(mode="after")
    def _fill_doc_id(self):
        if not self.doc_id:
            # validate_assignment is on, so set through __dict__ to avoid recursion
            self.__dict__["doc_id"] = stable_id(*self.natural_key())
        return self

    def to_jsonl_line(self) -> str:
        """One JSON object, one line — the .jsonl contract for the whole KB."""
        return self.model_dump_json(exclude_none=False)


# --------------------------------------------------------------------------- #
# Statute / section documents
# --------------------------------------------------------------------------- #


class StatuteSection(BaseDocument):
    """One section of an Act, or one Article of the Constitution.

    Statute text is government text and is stored in full — but only when the
    source's licence says so (`license.full_text_storage_allowed`).
    """

    doc_type: Literal["statute_section"] = "statute_section"

    # --- identity -------------------------------------------------------- #
    act_name: NonEmptyStr = Field(description="Full official name, e.g. "
                                  "'Bharatiya Nyaya Sanhita, 2023'.")
    act_short_name: NonEmptyStr = Field(description="e.g. 'BNS', 'CPA 2019', 'TPA'.")
    act_year: Optional[int] = Field(default=None, ge=1800, le=2100)
    act_number: Optional[str] = Field(
        default=None, description="e.g. '45 of 2023' (India Code enactment number)."
    )
    section_number: NonEmptyStr = Field(
        description="Kept as a string — real numbering includes '354A', '21B', "
        "'Article 19', 'Order XXI Rule 1'."
    )
    section_title: Optional[str] = None
    part_or_chapter: Optional[str] = Field(
        default=None, description="e.g. 'Chapter V — Of offences against woman and child'."
    )

    # --- content --------------------------------------------------------- #
    text: NonEmptyStr = Field(description="Cleaned full text of the section.")
    illustrations: list[str] = Field(default_factory=list)
    explanations: list[str] = Field(default_factory=list)
    provisos: list[str] = Field(default_factory=list)

    # --- classification --------------------------------------------------- #
    regime: Regime = Regime.UNAFFECTED
    statute_family: StatuteFamily = StatuteFamily.OTHER
    jurisdiction: Jurisdiction = Jurisdiction.UNION
    state: Optional[Slug] = Field(
        default=None,
        description="Required when jurisdiction is 'state'. Slug doubles as the "
        "filename under statutes/tenancy_property/rent_control_by_state/.",
    )

    # --- temporal / regime linkage ---------------------------------------- #
    effective_from: Optional[date] = None
    effective_until: Optional[date] = Field(
        default=None, description="Repeal date for archived sections."
    )
    superseded_by_act: Optional[str] = Field(
        default=None, description="Required when regime is 'archived'."
    )
    corresponding_new_sections: list[str] = Field(
        default_factory=list,
        description="On archived sections: the BNS/BNSS/BSA counterpart(s).",
    )
    corresponding_old_sections: list[str] = Field(
        default_factory=list,
        description="On current sections: the IPC/CrPC/Evidence Act antecedent(s).",
    )
    amendment_history: list[str] = Field(default_factory=list)

    # --- retrieval aids ---------------------------------------------------- #
    keywords: list[str] = Field(default_factory=list)
    is_offence: Optional[bool] = None
    punishment_summary: Optional[str] = Field(
        default=None, description="Short normalised punishment string, if applicable."
    )

    # ---------------------------------------------------------------------- #

    def natural_key(self) -> tuple[object, ...]:
        return ("statute", self.act_short_name, self.state or "union", self.section_number)

    @field_validator("text", "section_title", "punishment_summary", mode="before")
    @classmethod
    def _clean(cls, v: Any) -> Any:
        return clean_text(v) if isinstance(v, str) else v

    @field_validator("illustrations", "explanations", "provisos", mode="before")
    @classmethod
    def _clean_list(cls, v: Any) -> Any:
        if isinstance(v, list):
            return [clean_text(x) if isinstance(x, str) else x for x in v]
        return v

    @field_validator("section_number", mode="before")
    @classmethod
    def _normalise_section_number(cls, v: Any) -> Any:
        if not isinstance(v, str):
            return v
        # "Sec. 354-A " / "S 354 A" -> "354A"; Articles keep their prefix.
        s = clean_text(v)
        s = re.sub(r"^(sec(tion)?\.?|s\.)\s*", "", s, flags=re.IGNORECASE)
        if re.fullmatch(r"\d+\s*[-–]?\s*[A-Za-z]{0,2}", s):
            s = re.sub(r"[\s\-–]", "", s).upper()
        return s

    @model_validator(mode="after")
    def _state_required_for_state_law(self) -> "StatuteSection":
        if self.jurisdiction is Jurisdiction.STATE and not self.state:
            raise ValueError("jurisdiction='state' requires a state slug")
        if self.jurisdiction is Jurisdiction.UNION and self.state:
            raise ValueError("state must be empty for union legislation")
        return self

    @model_validator(mode="after")
    def _archived_sections_declare_successor(self) -> "StatuteSection":
        """An archived section must say what replaced it — otherwise a retrieval hit
        on an IPC number gives the user repealed law with no forward pointer."""
        if self.regime is Regime.ARCHIVED and not self.superseded_by_act:
            raise ValueError(
                "regime='archived' requires superseded_by_act "
                "(e.g. 'Bharatiya Nyaya Sanhita, 2023')"
            )
        return self

    @model_validator(mode="after")
    def _dates_are_ordered(self) -> "StatuteSection":
        if self.effective_from and self.effective_until:
            if self.effective_until < self.effective_from:
                raise ValueError("effective_until precedes effective_from")
        return self

    @model_validator(mode="after")
    def _licence_permits_full_text(self) -> "StatuteSection":
        if not self.license.full_text_storage_allowed:
            raise ValueError(
                f"cannot store full section text: licence '{self.license.license_id}' "
                "does not allow full-text storage"
            )
        return self


# --------------------------------------------------------------------------- #
# Case / precedent documents
# --------------------------------------------------------------------------- #


class CaseDocument(BaseDocument):
    """One judgment, stored as citation + short summary only.

    ``ratio_decidendi`` and ``obiter_dicta`` are deliberate empty placeholders:
    they are filled by a separate classification step downstream, never scraped.
    """

    doc_type: Literal["case"] = "case"

    # --- identity -------------------------------------------------------- #
    title: NonEmptyStr = Field(description="e.g. 'Vishaka v. State of Rajasthan'.")
    neutral_citation: Optional[str] = Field(
        default=None, description="e.g. '2024 INSC 123'."
    )
    reporter_citations: list[str] = Field(
        default_factory=list, description="e.g. ['AIR 1997 SC 3011', '(1997) 6 SCC 241']."
    )
    case_number: Optional[str] = Field(default=None, description="e.g. 'Crl.A. 123/2019'.")

    # --- court ------------------------------------------------------------ #
    court_level: CourtLevel
    court_name: NonEmptyStr = Field(description="e.g. 'Supreme Court of India'.")
    state: Optional[Slug] = Field(default=None, description="For High Courts / state fora.")
    bench_strength: Optional[int] = Field(default=None, ge=1, le=15)
    judges: list[str] = Field(default_factory=list)
    date_decided: Optional[date] = None

    # --- substance (length-capped by design) -------------------------------- #
    summary: str = Field(
        default="",
        max_length=SUMMARY_MAX_CHARS,
        description=f"Short neutral summary, hard-capped at {SUMMARY_MAX_CHARS} chars. "
        "Never a verbatim dump of the judgment.",
    )
    outcome: CaseOutcome = CaseOutcome.UNKNOWN
    ratio_decidendi: str = Field(
        default="", description="PLACEHOLDER — filled by the later classification step."
    )
    obiter_dicta: str = Field(
        default="", description="PLACEHOLDER — filled by the later classification step."
    )
    classification_status: ClassificationStatus = ClassificationStatus.PENDING

    # --- linkage ------------------------------------------------------------ #
    statutes_cited: list[StatuteReference] = Field(default_factory=list)
    cases_cited: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    is_landmark: bool = False

    # --- copyright guard ----------------------------------------------------- #
    full_text_stored: bool = Field(
        default=False,
        description="Must stay False unless the licence explicitly allows it AND "
        "config.copyright_policy.store_full_judgment_text is turned on.",
    )
    full_text: Optional[str] = Field(
        default=None, description="Normally None. Only populated under the guard above."
    )

    # ------------------------------------------------------------------------ #

    def natural_key(self) -> tuple[object, ...]:
        return (
            "case",
            self.neutral_citation
            or (self.reporter_citations[0] if self.reporter_citations else None)
            or self.case_number
            or self.title,
            self.court_name,
            self.date_decided,
        )

    @field_validator("summary", "ratio_decidendi", "obiter_dicta", mode="before")
    @classmethod
    def _clean(cls, v: Any) -> Any:
        return clean_text(v) if isinstance(v, str) else v

    @field_validator("title", mode="before")
    @classmethod
    def _normalise_title(cls, v: Any) -> Any:
        if not isinstance(v, str):
            return v
        return re.sub(r"\bvs?\.?\b", "v.", clean_text(v), flags=re.IGNORECASE)

    @model_validator(mode="after")
    def _identifiable(self) -> "CaseDocument":
        """A case with no citation and no case number cannot be verified by a user,
        and cannot be deduped reliably. Reject it rather than let it into the KB."""
        if not (self.neutral_citation or self.reporter_citations or self.case_number):
            raise ValueError(
                "case needs at least one of neutral_citation / reporter_citations / "
                "case_number"
            )
        return self

    @model_validator(mode="after")
    def _classification_placeholders_are_consistent(self) -> "CaseDocument":
        if self.classification_status is ClassificationStatus.PENDING and (
            self.ratio_decidendi or self.obiter_dicta
        ):
            raise ValueError(
                "ratio_decidendi/obiter_dicta populated while classification_status "
                "is 'pending' — set it to 'complete'"
            )
        return self

    @model_validator(mode="after")
    def _full_text_guard(self) -> "CaseDocument":
        if self.full_text and not self.full_text_stored:
            raise ValueError("full_text present but full_text_stored is False")
        if self.full_text_stored and not self.license.full_text_storage_allowed:
            raise ValueError(
                f"licence '{self.license.license_id}' does not permit storing full "
                "judgment text — keep citation + summary only"
            )
        return self


# --------------------------------------------------------------------------- #
# Cross-reference (IPC/CrPC/Evidence Act -> BNS/BNSS/BSA)
# --------------------------------------------------------------------------- #


class CrossReferenceEntry(BaseModel):
    """One row of knowledge_base/crossreference/ipc_to_bns_mapping.jsonl."""

    # extra="ignore" (not "forbid") so a written .jsonl line round-trips: computed
    # fields are emitted on dump and would otherwise be rejected on re-read.
    model_config = ConfigDict(extra="ignore")

    mapping_id: str = Field(default="")
    schema_version: str = SCHEMA_VERSION

    old_act_short_name: NonEmptyStr  # "IPC" | "CrPC" | "Evidence Act"
    old_statute_family: StatuteFamily
    old_section: NonEmptyStr
    old_section_title: Optional[str] = None

    new_act_short_name: Optional[str] = None  # "BNS" | "BNSS" | "BSA" | None
    new_statute_family: Optional[StatuteFamily] = None
    new_sections: list[str] = Field(
        default_factory=list, description="Empty when relationship is 'no_equivalent'."
    )
    new_section_title: Optional[str] = None

    relationship: MappingRelationship
    domains: list[Domain] = Field(min_length=1)
    substantive_change_note: Optional[str] = Field(
        default=None, description="What actually changed, if anything."
    )
    confidence: Literal["high", "medium", "low"] = "high"
    verified_against: Optional[str] = Field(
        default=None, description="Authority relied on, e.g. 'MHA comparative table'."
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_one_to_one(self) -> bool:
        """Convenience flag for consumers: True only for a clean 1:1 renumbering."""
        return (
            self.relationship is MappingRelationship.ONE_TO_ONE
            and len(self.new_sections) == 1
        )

    @model_validator(mode="after")
    def _relationship_matches_targets(self) -> "CrossReferenceEntry":
        n = len(self.new_sections)
        rel = self.relationship
        if rel is MappingRelationship.NO_EQUIVALENT and n:
            raise ValueError("'no_equivalent' must have an empty new_sections list")
        if rel is not MappingRelationship.NO_EQUIVALENT and n == 0:
            raise ValueError(f"relationship '{rel.value}' requires at least one new section")
        if rel is MappingRelationship.ONE_TO_ONE and n != 1:
            raise ValueError("'one_to_one' must map to exactly one new section")
        if rel is MappingRelationship.SPLIT and n < 2:
            raise ValueError("'split' must map to two or more new sections")
        if not self.mapping_id:
            self.__dict__["mapping_id"] = stable_id(
                "xref", self.old_act_short_name, self.old_section
            )
        return self

    def to_jsonl_line(self) -> str:
        return self.model_dump_json(exclude_none=False)


# --------------------------------------------------------------------------- #
# Embedding-ready chunk
# --------------------------------------------------------------------------- #


class Chunk(BaseModel):
    """One line of knowledge_base/embeddings_ready/chunks.jsonl.

    Flattened and self-describing on purpose: the RAG pipeline loads this file
    alone and needs every filter/citation field inline, with no joins back into
    statutes/ or caselaw/.
    """

    # extra="ignore" so chunks.jsonl round-trips — see CrossReferenceEntry.
    model_config = ConfigDict(extra="ignore")

    chunk_id: str = Field(default="")
    schema_version: str = SCHEMA_VERSION

    doc_id: NonEmptyStr
    doc_type: Literal["statute_section", "case", "crossref"]
    chunk_index: int = Field(ge=0)
    total_chunks: int = Field(ge=1)

    text: NonEmptyStr

    # denormalised filter/citation surface
    domains: list[Domain] = Field(min_length=1)
    regime: Regime = Regime.UNAFFECTED
    title: NonEmptyStr = Field(description="Human-readable label for citation display.")
    act_short_name: Optional[str] = None
    section_number: Optional[str] = None
    citation: Optional[str] = None
    court_level: Optional[CourtLevel] = None
    date: Optional[date] = None
    jurisdiction: Jurisdiction = Jurisdiction.UNION
    state: Optional[Slug] = None

    source_url: HttpUrl
    license_id: NonEmptyStr
    license_usage: LicenseUsage

    @computed_field  # type: ignore[prop-decorator]
    @property
    def char_count(self) -> int:
        return len(self.text)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def approx_tokens(self) -> int:
        """Rough ~4 chars/token estimate — for budgeting only, not billing."""
        return max(1, round(len(self.text) / 4))

    @field_validator("text", mode="before")
    @classmethod
    def _clean(cls, v: Any) -> Any:
        return clean_text(v) if isinstance(v, str) else v

    @model_validator(mode="after")
    def _finalise(self) -> "Chunk":
        if self.chunk_index >= self.total_chunks:
            raise ValueError("chunk_index must be < total_chunks")
        if not self.chunk_id:
            self.__dict__["chunk_id"] = f"{self.doc_id}::{self.chunk_index:04d}"
        return self

    def to_jsonl_line(self) -> str:
        return self.model_dump_json(exclude_none=False)


# --------------------------------------------------------------------------- #
# Folder metadata + build manifest
# --------------------------------------------------------------------------- #


class SourceAttribution(BaseModel):
    """One source credited in a domain folder's metadata.json."""

    model_config = ConfigDict(extra="forbid")

    source_name: NonEmptyStr
    source_url: HttpUrl
    license: LicenseInfo
    document_count: int = Field(ge=0)


class DomainMetadata(BaseModel):
    """knowledge_base/<statutes|caselaw>/<domain>/metadata.json.

    Every domain folder carries its own sources, licences and counts so the folder
    is independently browsable — you can hand someone
    statutes/consumer_protection/ on its own and it still explains itself.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    domain: Domain
    collection: Literal["statutes", "caselaw"]
    description: NonEmptyStr
    sources: list[SourceAttribution] = Field(min_length=1)
    files: dict[str, int] = Field(
        default_factory=dict, description="filename -> document count."
    )
    document_count: int = Field(ge=0)
    last_updated: date
    kb_version: NonEmptyStr
    coverage_notes: Optional[str] = None
    known_gaps: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _counts_agree(self) -> "DomainMetadata":
        if self.files and sum(self.files.values()) != self.document_count:
            raise ValueError("document_count does not equal the sum of per-file counts")
        return self


class BuildManifest(BaseModel):
    """knowledge_base/manifest.json — regenerated on every run."""

    # extra="ignore" so manifest.json round-trips — see CrossReferenceEntry.
    model_config = ConfigDict(extra="ignore")

    schema_version: str = SCHEMA_VERSION
    kb_version: NonEmptyStr
    build_date: date
    built_at: datetime = Field(default_factory=_utcnow)
    pipeline_commit: Optional[str] = None

    statute_counts_by_domain: dict[Domain, int] = Field(default_factory=dict)
    caselaw_counts_by_domain: dict[Domain, int] = Field(default_factory=dict)
    crossref_count: int = Field(default=0, ge=0)
    chunk_count: int = Field(default=0, ge=0)

    sources_used: list[SourceAttribution] = Field(default_factory=list)
    validation_summary: dict[str, Any] = Field(default_factory=dict)
    steps_completed: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_documents(self) -> int:
        return (
            sum(self.statute_counts_by_domain.values())
            + sum(self.caselaw_counts_by_domain.values())
            + self.crossref_count
        )


__all__ = [
    "SCHEMA_VERSION",
    "SUMMARY_MAX_CHARS",
    "NEW_CRIMINAL_REGIME_COMMENCEMENT",
    "Domain",
    "Regime",
    "StatuteFamily",
    "Jurisdiction",
    "CourtLevel",
    "CaseOutcome",
    "LicenseUsage",
    "RetrievalMethod",
    "ClassificationStatus",
    "MappingRelationship",
    "LicenseInfo",
    "Provenance",
    "StatuteReference",
    "BaseDocument",
    "StatuteSection",
    "CaseDocument",
    "CrossReferenceEntry",
    "Chunk",
    "SourceAttribution",
    "DomainMetadata",
    "BuildManifest",
    "clean_text",
    "stable_id",
]
