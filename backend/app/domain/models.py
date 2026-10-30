"""Domain models. Frozen, so a document cannot change after it is parsed (SPEC §3.4)."""

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class Lang(StrEnum):
    EN = "en"
    TC = "tc"


class Flag(StrEnum):
    """Markers HKEX puts on corrected entries (research notes §6)."""

    CANCELLED = "cancelled"
    HEADLINES_REVISED = "headlines_revised"
    REVISED = "revised"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class Stock(_Frozen):
    stock_id: int
    code: str
    name_en: str
    name_tc: str | None = None
    active: bool = True


class Category(_Frozen):
    """A tier-two headline category."""

    code: str
    name: str
    t1code: str
    group_code: str | None = None


class Document(_Frozen):
    path: str
    lang: Lang
    release_at: datetime
    stock_codes: tuple[str, ...]
    stock_names: tuple[str, ...]
    title: str
    category_text: str
    category_prefix: str = ""
    category_codes: tuple[str, ...] = ()
    file_type: str
    size_label: str
    folder_date: date | None
    seq: int | None
    is_stub: bool
    flags: frozenset[Flag]
    news_id: str
    source_url: str
