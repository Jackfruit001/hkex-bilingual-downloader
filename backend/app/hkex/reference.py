"""Reference data: the stock directory and the headline category index."""

import asyncio
import gzip
import json
import time
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from app.domain.errors import AppError, ErrorCode
from app.domain.models import Lang, Stock
from app.hkex.client import HkexClient
from app.hkex.parse import ParsedCategory, clean_text


def _padded(code: Any) -> str:
    text = str(code).strip()
    return text.zfill(5) if text.isdigit() else text


class CategoryIndex:
    """Maps localised category text to tier codes, which are the same in both languages.

    Resolution is by parent and child together (the same child name occurs under several
    parents) and is all or nothing: if any named category is unknown the result is empty, so
    a partial code set can never look like a match or a conflict.
    """

    def __init__(
        self,
        tier_one: Mapping[Lang, Mapping[str, str]],
        tier_two: Mapping[Lang, Mapping[tuple[str, str], tuple[str, ...]]],
    ) -> None:
        self._tier_one = tier_one
        self._tier_two = tier_two

    @classmethod
    def from_raw(
        cls,
        tierone_en: Iterable[Mapping[str, Any]],
        tiertwo_en: Iterable[Mapping[str, Any]],
        tierone_tc: Iterable[Mapping[str, Any]],
        tiertwo_tc: Iterable[Mapping[str, Any]],
    ) -> "CategoryIndex":
        one: dict[Lang, dict[str, str]] = {}
        two: dict[Lang, dict[tuple[str, str], tuple[str, ...]]] = {}
        for lang, t1, t2 in ((Lang.EN, tierone_en, tiertwo_en), (Lang.TC, tierone_tc, tiertwo_tc)):
            one[lang] = {clean_text(e["name"]): str(e["code"]) for e in t1}
            grouped: dict[tuple[str, str], list[str]] = defaultdict(list)
            for e in t2:
                grouped[(str(e["t1code"]), clean_text(e["name"]))].append(str(e["code"]))
            two[lang] = {k: tuple(v) for k, v in grouped.items()}
        return cls(one, two)

    def resolve(self, lang: Lang, parsed: ParsedCategory) -> tuple[str, ...]:
        parent = self._tier_one[lang].get(parsed.parent)
        if parent is None:
            return ()
        if not parsed.children:
            return (parent,)
        found: list[str] = []
        for child in parsed.children:
            options = self._tier_two[lang].get((parent, child), ())
            if len(options) != 1:  # unknown, or the name is not unique under this parent
                return ()
            found.append(options[0])
        return tuple(dict.fromkeys(found))


class StockDirectory:
    """Active and delisted securities. A code can belong to several over time (code reuse)."""

    def __init__(self, stocks: Iterable[Stock]) -> None:
        self._by_code: dict[str, list[Stock]] = defaultdict(list)
        for s in stocks:
            self._by_code[s.code].append(s)
        for group in self._by_code.values():
            group.sort(key=lambda s: (not s.active, s.stock_id))

    @classmethod
    def from_raw(
        cls,
        active_en: Iterable[Mapping[str, Any]],
        active_tc: Iterable[Mapping[str, Any]],
        inactive_en: Iterable[Mapping[str, Any]],
        inactive_tc: Iterable[Mapping[str, Any]],
    ) -> "StockDirectory":
        stocks: list[Stock] = []
        for active, en_list, tc_list in (
            (True, active_en, active_tc),
            (False, inactive_en, inactive_tc),
        ):
            tc_names = {int(e["i"]): clean_text(e["n"]) for e in tc_list}
            for e in en_list:
                sid = int(e["i"])
                stocks.append(
                    Stock(
                        stock_id=sid,
                        code=_padded(e["c"]),
                        name_en=clean_text(e["n"]),
                        name_tc=tc_names.get(sid),
                        active=active,
                    )
                )
        return cls(stocks)

    def __len__(self) -> int:
        return sum(len(g) for g in self._by_code.values())

    def lookup(self, code: str) -> list[Stock]:
        return list(self._by_code.get(code, ()))

    def resolve(self, code: str, stock_id: int | None = None) -> Stock:
        """The one security for a code, or an error that tells the user what to do."""
        found = self.lookup(code)
        if stock_id is not None:
            found = [s for s in found if s.stock_id == stock_id]
        if not found:
            raise AppError(
                ErrorCode.UNKNOWN_STOCK_CODE,
                f"No HKEX security uses code {code}. Check the code and try again.",
                {"code": code},
            )
        if len(found) > 1:
            raise AppError(
                ErrorCode.AMBIGUOUS_STOCK_CODE,
                f"Code {code} has belonged to more than one company. Choose the one you mean.",
                {"code": code, "choices": [s.model_dump() for s in found]},
            )
        return found[0]


# --- loading: live, cache, snapshot -----------------------------------------------------

REFERENCE_BASE = "https://www1.hkexnews.hk/ncms/script/eds/"
REFERENCE_FILES = (
    "activestock_sehk_e",
    "activestock_sehk_c",
    "inactivestock_sehk_e",
    "inactivestock_sehk_c",
    "tierone_e",
    "tierone_c",
    "tiertwo_e",
    "tiertwo_c",
)
DEFAULT_SNAPSHOT = Path(__file__).parent / "data" / "reference_snapshot.json.gz"
MIN_ACTIVE_STOCKS = 1000  # a shorter active list means a truncated or wrong response
_UNAVAILABLE = "HKEXnews didn't respond. Try again in a minute."


@dataclass(frozen=True)
class ReferenceData:
    stocks: StockDirectory
    categories: CategoryIndex
    source: Literal["live", "snapshot"]
    as_of: datetime


def _build(
    raw: Mapping[str, Any], source: Literal["live", "snapshot"], as_of: datetime
) -> ReferenceData:
    try:
        if len(raw["activestock_sehk_e"]) < MIN_ACTIVE_STOCKS:
            raise ValueError("active stock list is too short")
        stocks = StockDirectory.from_raw(
            raw["activestock_sehk_e"],
            raw["activestock_sehk_c"],
            raw["inactivestock_sehk_e"],
            raw["inactivestock_sehk_c"],
        )
        categories = CategoryIndex.from_raw(
            raw["tierone_e"], raw["tiertwo_e"], raw["tierone_c"], raw["tiertwo_c"]
        )
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise AppError(
            ErrorCode.HKEX_UNAVAILABLE, _UNAVAILABLE, {"reason": f"bad reference data: {exc}"}
        ) from exc
    return ReferenceData(stocks, categories, source, as_of)


def build_snapshot(raw: Mapping[str, Any], generated_at: datetime) -> bytes:
    """A gzipped JSON copy of the reference data with only the fields the app uses."""

    def stocks(en: Iterable[Mapping[str, Any]], tc: Iterable[Mapping[str, Any]]) -> list[list[Any]]:
        names = {int(e["i"]): e["n"] for e in tc}
        return [[int(e["i"]), e["c"], e["n"], names.get(int(e["i"]))] for e in en]

    body = {
        "generated_at": generated_at.isoformat(),
        "active": stocks(raw["activestock_sehk_e"], raw["activestock_sehk_c"]),
        "inactive": stocks(raw["inactivestock_sehk_e"], raw["inactivestock_sehk_c"]),
        "categories": {
            name: [{k: e[k] for k in ("code", "name", "t1code") if k in e} for e in raw[name]]
            for name in ("tierone_e", "tierone_c", "tiertwo_e", "tiertwo_c")
        },
    }
    return gzip.compress(
        json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode(), mtime=0
    )


def load_snapshot(path: Path) -> ReferenceData:
    try:
        body = json.loads(gzip.decompress(path.read_bytes()))

        def raw_stocks(rows: list[list[Any]], tc: bool) -> list[dict[str, Any]]:
            return [
                {"i": r[0], "c": r[1], "n": r[3] if tc else r[2]}
                for r in rows
                if not tc or r[3] is not None
            ]

        raw: dict[str, Any] = {
            "activestock_sehk_e": raw_stocks(body["active"], False),
            "activestock_sehk_c": raw_stocks(body["active"], True),
            "inactivestock_sehk_e": raw_stocks(body["inactive"], False),
            "inactivestock_sehk_c": raw_stocks(body["inactive"], True),
            **body["categories"],
        }
        as_of = datetime.fromisoformat(body["generated_at"])
    except (
        OSError,
        ValueError,
        KeyError,
        IndexError,
        TypeError,
        gzip.BadGzipFile,
        EOFError,
    ) as exc:
        raise AppError(
            ErrorCode.HKEX_UNAVAILABLE, _UNAVAILABLE, {"reason": f"bad snapshot: {exc}"}
        ) from exc
    return _build(raw, "snapshot", as_of)


class ReferenceService:
    """Loads the stock and category lists once, refreshes them after a TTL, and falls back.

    If HKEXnews cannot be reached: keep the previous data (even if stale); otherwise use the
    bundled snapshot. After a failure live loading is not retried for `retry_after_failure_s`,
    so a broken upstream is not hit on every request.
    """

    def __init__(
        self,
        client: HkexClient,
        *,
        ttl_s: float = 24 * 3600,
        retry_after_failure_s: float = 300.0,
        clock: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        snapshot_path: Path | None = DEFAULT_SNAPSHOT,
    ) -> None:
        self._client = client
        self._ttl = ttl_s
        self._retry_after_failure = retry_after_failure_s
        self._clock = clock
        self._now = now
        self._snapshot_path = snapshot_path
        self._data: ReferenceData | None = None
        self._valid_until = 0.0
        self._lock = asyncio.Lock()

    async def _load_live(self) -> ReferenceData:
        raw: dict[str, Any] = {}

        async def fetch(name: str) -> None:
            raw[name] = await self._client.get_json(f"{REFERENCE_BASE}{name}.json")

        try:
            async with asyncio.TaskGroup() as group:
                for name in REFERENCE_FILES:
                    group.create_task(fetch(name))
        except ExceptionGroup as group_error:
            first = group_error.exceptions[0]
            if isinstance(first, AppError):
                raise first from None
            raise
        return _build(raw, "live", self._now())

    async def get(self) -> ReferenceData:
        async with self._lock:
            if self._data is not None and self._clock() < self._valid_until:
                return self._data
            try:
                self._data = await self._load_live()
                self._valid_until = self._clock() + self._ttl
            except AppError:
                self._valid_until = self._clock() + self._retry_after_failure
                if self._data is None:
                    if self._snapshot_path is None:
                        raise
                    try:
                        self._data = load_snapshot(self._snapshot_path)
                    except AppError:
                        self._valid_until = 0.0
                        raise
            return self._data
