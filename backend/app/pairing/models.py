"""Pairing results (SPEC §4.1). Frozen, like the documents they are built from."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from app.domain.models import Document, Lang


class Status(StrEnum):
    MATCHED = "matched"
    CHECK = "check"
    EN_ONLY = "en_only"
    TC_ONLY = "tc_only"


class SingleReason(StrEnum):
    STUB_IN_OTHER_SECTION = "stub_in_other_section"
    NOT_FOUND = "not_found"


class Format(StrEnum):
    PDF = "pdf"
    WEB_PAGE = "web_page"
    MULTI_FILE = "multi_file"
    OTHER = "other"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class SignalHit(_Frozen):
    """One scoring signal that applied to a pair. `kind` says which variant, for the evidence."""

    id: str  # "S1" .. "S7"
    points: int
    kind: str
    values: tuple[str, ...] = ()


class Rival(_Frozen):
    """Another document that could belong to the entry, with its score."""

    document: Document
    score: int


class Announcement(_Frozen):
    id: str
    status: Status
    release_at: datetime
    en: Document | None = None
    tc: Document | None = None
    score: int | None = None
    signals: tuple[SignalHit, ...] = ()
    evidence: tuple[str, ...] = ()
    reason: SingleReason | None = None
    stub: Document | None = None  # the HKEXnews notice, linked as a source, never a version
    rivals: tuple[Rival, ...] = ()
    format: Format = Format.PDF
    bilingual: bool = False  # one file, published in both sections
    separate: bool = False  # the two versions were published on different days
    layout_ambiguous: bool = False  # D-011


@dataclass(frozen=True)
class ContentVerdict:
    """The outcome of comparing figures in an English PDF with a Chinese one (SPEC §4.5)."""

    en_news_id: str
    tc_news_id: str
    score: float
    runner_up: float
    tokens: int
    conclusive: bool


@dataclass(frozen=True)
class ContentEvidence:
    """Facts learned from the files themselves; empty until files have been downloaded."""

    sha256: dict[tuple[Lang, str], str] = field(default_factory=dict)  # (lang, news_id) -> hex
    verdicts: tuple[ContentVerdict, ...] = ()


@dataclass(frozen=True)
class PairingDiagnostics:
    announcements: int = 0
    by_status: dict[str, int] = field(default_factory=dict)
    orphan_stubs: int = 0
    non_interleaved_groups: int = 0
    greedy_components: int = 0
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class PairingResult:
    announcements: tuple[Announcement, ...]
    diagnostics: PairingDiagnostics
