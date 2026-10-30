"""The golden entry (SPEC §10.4): what Zarif verifies and what the golden test reads.

`truth` is the claim a person confirms by opening both PDFs. `proposal` is what the matcher said
when the entry was drafted; it is there to be compared with, never to be believed, and the
golden test ignores it. Extra fields are an error so a misspelt `verified` cannot silently leave
an entry unverified.
"""

from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CaseType(StrEnum):
    # The twelve cases SPEC §10.4 requires, in a fixed display order.
    ORDINARY = "ordinary"
    SEVERAL_SAME_DAY = "several_same_day"
    SEVERAL_SAME_MINUTE = "several_same_minute"
    EN_ONLY_STUB = "en_only_stub"
    TC_ONLY_STUB = "tc_only_stub"
    SEPARATE_ANNUAL_REPORT = "separate_annual_report"
    BILINGUAL_IDENTICAL = "bilingual_identical"
    REVISED_OR_CANCELLED = "revised_or_cancelled"
    MULTI_FILE = "multi_file"
    WEB_PAGE = "web_page"
    PRE_2007 = "pre_2007"
    DELISTED = "delisted"
    # Worth recording, not required.
    SINGLE_NOT_FOUND = "single_not_found"
    BLOCK_LAYOUT = "block_layout"
    SEPARATE_OTHER = "separate_other"


REQUIRED_CASE_TYPES: tuple[CaseType, ...] = tuple(CaseType)[:12]


class _Strict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class DocRef(_Strict):
    news_id: str
    path: str
    title: str
    released: str  # "YYYY-MM-DD HH:MM", Hong Kong time


class Truth(_Strict):
    en: DocRef | None = None
    tc: DocRef | None = None
    # Why the missing side is missing: a stub notice, or nothing was found. Only for single entries.
    absent: Literal["stub", "not_found"] | None = None

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        present = (self.en is not None) + (self.tc is not None)
        if present == 0:
            raise ValueError("an entry needs at least one document")
        if present == 2 and self.absent is not None:
            raise ValueError("an entry with both versions cannot have an absent reason")
        if present == 1 and self.absent is None:
            raise ValueError("a single-language entry needs a reason: stub or not_found")
        return self


class Proposal(_Strict):
    status: str
    score: int | None = None
    evidence: list[str] = Field(default_factory=list)


class Entry(_Strict):
    id: str
    verified: bool = False
    stock_code: str = Field(pattern=r"^\d{5}$")
    stock_id: int
    stock_name: str
    scenario: str
    case_types: list[CaseType] = Field(min_length=1)
    truth: Truth
    notes: str = ""
    proposal: Proposal


def entry_id(stock_code: str, truth: Truth) -> str:
    """Stable across drafts: the code plus the news id of the English document (or the Chinese)."""
    if truth.en is not None:
        return f"{stock_code}-{truth.en.news_id}"
    assert truth.tc is not None
    return f"{stock_code}-tc-{truth.tc.news_id}"
