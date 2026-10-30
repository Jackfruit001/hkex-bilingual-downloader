"""Per-language search with cumulative pagination (SPEC §3.2 and §3.3).

Verified behaviour (research notes §9): `rowRange=N` returns rows 1 to N, `recordCnt` holds the
total, `lang=ZH` selects the Chinese section and the response echoes `lang: "C"`; any other
value silently returns English, so the echo is checked on every call.
"""

import asyncio
import json
import time
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from typing import Any

from app.domain.errors import AppError, ErrorCode
from app.domain.models import Document, Lang, Stock
from app.domain.timeutil import hkex_date
from app.domain.validation import EARLIEST_DATE
from app.hkex.client import HkexClient
from app.hkex.parse import RowError, has_chinese_suffix, parse_row
from app.hkex.reference import CategoryIndex

SERVLET_URL = "https://www1.hkexnews.hk/search/titleSearchServlet.do"
FIRST_PAGE = 100
ROW_CAP = 5_000  # most rows requested in one call
MAX_ROWS = 20_000  # most rows per language per search

_LANG_PARAM = {Lang.EN: "EN", Lang.TC: "ZH"}
_LANG_ECHO = {Lang.EN: "E", Lang.TC: "C"}
_SECTION = {Lang.EN: "English", Lang.TC: "Chinese"}


@dataclass
class LangStats:
    calls: int = 0
    rows_fetched: int = 0
    rows_skipped: int = 0
    splits: int = 0
    rows_with_c_suffix: int = 0  # English section rows that look Chinese
    rows_without_c_suffix: int = 0  # Chinese section rows that look English


@dataclass
class SearchDiagnostics:
    english: LangStats = field(default_factory=LangStats)
    chinese: LangStats = field(default_factory=LangStats)
    outside_range: int = 0
    warnings: list[str] = field(default_factory=list)
    duration_s: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SearchOutput:
    english: list[Document]
    chinese: list[Document]
    diagnostics: SearchDiagnostics


def _params(stock: Stock, lang: Lang, lo: date, hi: date, row_range: int) -> dict[str, Any]:
    return {
        "sortDir": 0,
        "sortByOptions": "DateTime",
        "category": 0 if stock.active else 1,
        "market": "SEHK",
        "stockId": stock.stock_id,
        "documentType": -1,
        "fromDate": hkex_date(lo),
        "toDate": hkex_date(hi),
        "title": "",
        "searchType": 0,
        "t1code": -2,
        "t2Gcode": -2,
        "t2code": -2,
        "rowRange": row_range,
        "lang": _LANG_PARAM[lang],
    }


def _rows(envelope: dict[str, Any]) -> list[Any]:
    result = envelope.get("result")
    if isinstance(result, str):
        result = None if result in ("", "null") else json.loads(result)
    return result if isinstance(result, list) else []


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class _LanguageSearch:
    def __init__(
        self,
        client: HkexClient,
        stock: Stock,
        lang: Lang,
        categories: CategoryIndex | None,
        stats: LangStats,
        warnings: list[str],
    ) -> None:
        self._client = client
        self._stock = stock
        self._lang = lang
        self._categories = categories
        self._stats = stats
        self._warnings = warnings
        self._raw: list[dict[str, Any]] = []

    async def _call(self, lo: date, hi: date, row_range: int) -> tuple[list[Any], int]:
        envelope = await self._client.get_json(
            SERVLET_URL, _params(self._stock, self._lang, lo, hi, row_range)
        )
        self._stats.calls += 1
        echo = envelope.get("lang")
        if echo != _LANG_ECHO[self._lang]:
            raise AppError(
                ErrorCode.HKEX_UNAVAILABLE,
                "HKEXnews didn't respond. Try again in a minute.",
                {
                    "reason": f"Asked for the {_SECTION[self._lang]} section but HKEXnews answered "
                    f"in language code {echo!r}"
                },
            )
        rows = _rows(envelope)
        return rows, _int(envelope.get("recordCnt"), len(rows))

    async def fetch(self, lo: date, hi: date) -> None:
        rows, total = await self._call(lo, hi, FIRST_PAGE)
        if total > MAX_ROWS:
            raise AppError(
                ErrorCode.TOO_MANY_RESULTS,
                "This search returns more than 20,000 documents. "
                "Narrow the dates or choose a category.",
                {"total": total},
            )
        if total > ROW_CAP:
            if lo == hi:
                rows, _ = await self._call(lo, hi, ROW_CAP)
                self._warnings.append(
                    f"The {_SECTION[self._lang]} section has more than {ROW_CAP} documents "
                    f"on {lo}; showing the newest {ROW_CAP}."
                )
            else:
                mid = lo + timedelta(days=(hi - lo).days // 2)
                self._stats.splits += 1
                await self.fetch(lo, mid)
                await self.fetch(mid + timedelta(days=1), hi)
                return
        elif total > len(rows):
            rows, _ = await self._call(lo, hi, total)
        if len(rows) < min(total, ROW_CAP):
            self._warnings.append(
                f"HKEXnews reported {total} {_SECTION[self._lang]} documents for {lo} to {hi} "
                f"but returned {len(rows)}."
            )
        self._raw.extend(r for r in rows if isinstance(r, dict))

    def documents(self) -> list[Document]:
        docs: dict[str, Document] = {}
        for raw in self._raw:
            try:
                doc = parse_row(raw, self._lang, self._categories)
            except RowError:
                self._stats.rows_skipped += 1
                continue
            if (
                doc.news_id in docs
            ):  # an exact repeat; `path` cannot be the key (shared /dod/ pages)
                continue
            docs[doc.news_id] = doc
            chinese = has_chinese_suffix(doc.path)
            if self._lang is Lang.TC and not chinese:
                self._stats.rows_without_c_suffix += 1
            if self._lang is Lang.EN and chinese:
                self._stats.rows_with_c_suffix += 1
        self._stats.rows_fetched = len(docs)
        if self._stats.rows_skipped:
            self._warnings.append(
                f"Skipped {self._stats.rows_skipped} {_SECTION[self._lang]} rows that HKEXnews "
                "returned without a usable date, id or link."
            )
        return sorted(docs.values(), key=lambda d: (d.release_at, d.news_id), reverse=True)


async def search_language(
    client: HkexClient,
    stock: Stock,
    lang: Lang,
    start: date,
    end: date,
    categories: CategoryIndex | None = None,
    *,
    stats: LangStats | None = None,
    warnings: list[str] | None = None,
) -> list[Document]:
    """All documents of one section for the dates given (inclusive), unfiltered by HKT."""
    search = _LanguageSearch(
        client,
        stock,
        lang,
        categories,
        stats or LangStats(),
        warnings if warnings is not None else [],
    )
    await search.fetch(start, end)
    return search.documents()


async def search_both(
    client: HkexClient,
    stock: Stock,
    start: date,
    end: date,
    categories: CategoryIndex | None = None,
) -> SearchOutput:
    """Query both sections with one day of buffer, then keep documents released inside the range.

    The buffer means the result does not depend on how HKEX treats the boundary dates; the
    filter uses each document's own Hong Kong release time.
    """
    started = time.monotonic()
    diag = SearchDiagnostics()
    lo = max(start - timedelta(days=1), EARLIEST_DATE)
    hi = end + timedelta(days=1)
    english, chinese = await asyncio.gather(
        search_language(
            client, stock, Lang.EN, lo, hi, categories, stats=diag.english, warnings=diag.warnings
        ),
        search_language(
            client, stock, Lang.TC, lo, hi, categories, stats=diag.chinese, warnings=diag.warnings
        ),
    )

    def inside(docs: list[Document]) -> list[Document]:
        kept = [d for d in docs if start <= d.release_at.date() <= end]
        diag.outside_range += len(docs) - len(kept)
        return kept

    out = SearchOutput(inside(english), inside(chinese), diag)
    diag.duration_s = round(time.monotonic() - started, 3)
    return out
