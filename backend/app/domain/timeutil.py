"""Hong Kong time helpers. Business logic never uses the server's or browser's local zone."""

import re
from collections.abc import Callable
from datetime import date, datetime
from zoneinfo import ZoneInfo

HKT = ZoneInfo("Asia/Hong_Kong")

_DATE_TIME = re.compile(r"^(\d{2})/(\d{2})/(\d{4}) (\d{2}):(\d{2})$")


def parse_hkex_datetime(value: str) -> datetime:
    """Parse the servlet's `DD/MM/YYYY HH:MM` (Hong Kong time) into an aware datetime."""
    m = _DATE_TIME.match(value.strip())
    if not m:
        raise ValueError(f"Unexpected DATE_TIME value: {value!r}")
    day, month, year, hour, minute = (int(g) for g in m.groups())
    try:
        return datetime(year, month, day, hour, minute, tzinfo=HKT)
    except ValueError as exc:
        raise ValueError(f"Invalid DATE_TIME value: {value!r}") from exc


def _utc_now() -> datetime:
    return datetime.now(ZoneInfo("UTC"))


def today_hkt(clock: Callable[[], datetime] = _utc_now) -> date:
    """Today's date in Hong Kong. `clock` must return an aware datetime (injectable for tests)."""
    now = clock()
    if now.tzinfo is None:
        raise ValueError("clock() must return a timezone-aware datetime")
    return now.astimezone(HKT).date()


def hkex_date(d: date) -> str:
    """Servlet date parameter format."""
    return d.strftime("%Y%m%d")
