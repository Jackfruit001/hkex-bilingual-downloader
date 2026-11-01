"""Request and response shapes of the API (SPEC §7)."""

from pydantic import BaseModel, ConfigDict, Field

from app.downloads.jobs import Mode


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SearchRequest(_Body):
    stock_code: str = Field(max_length=20)
    stock_id: int | None = None
    start: str = Field(max_length=10)
    end: str = Field(max_length=10)
    categories: list[str] = Field(default_factory=list, max_length=40)
    keyword: str | None = Field(default=None, max_length=100)


class ContentCheckRequest(_Body):
    en_path: str = Field(max_length=300)
    tc_paths: list[str] = Field(min_length=1, max_length=5)


class DownloadItem(_Body):
    path: str = Field(max_length=300)
    filename: str = Field(max_length=300)


class DownloadRequest(_Body):
    mode: Mode
    items: list[DownloadItem] = Field(min_length=1, max_length=100)
    zip_name: str = Field(default="", max_length=200)


class StockOut(BaseModel):
    stock_id: int
    code: str
    name_en: str
    name_tc: str | None
    active: bool


class DocumentOut(BaseModel):
    path: str
    title: str
    file_type: str
    size_label: str
    source_url: str
    filename: str | None  # None when the entry is not a PDF
    downloadable: bool


class RivalOut(BaseModel):
    lang: str
    title: str
    path: str
    score: int


class AnnouncementOut(BaseModel):
    id: str
    status: str
    release_at: str  # ISO 8601 with +08:00
    category: str
    en: DocumentOut | None
    tc: DocumentOut | None
    evidence: list[str]
    notice_url: str | None  # the HKEXnews "other section" notice, a source and never a version
    rivals: list[RivalOut]
    format: str
    bilingual: bool
    separate: bool
    pair_zip_name: str | None
    pair_zip_downloadable: bool


class SearchResponse(BaseModel):
    company: StockOut
    alternatives: list[StockOut]
    start: str
    end: str
    announcements: list[AnnouncementOut]
    summary: dict[str, int]
    warnings: list[str]
    diagnostics: dict[str, object]
