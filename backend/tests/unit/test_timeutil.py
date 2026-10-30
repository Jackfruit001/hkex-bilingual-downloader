from datetime import UTC, date, datetime, timedelta

import pytest

from app.domain.timeutil import HKT, hkex_date, parse_hkex_datetime, today_hkt


def test_parse_hkex_datetime_is_hong_kong_time() -> None:
    dt = parse_hkex_datetime("28/10/2026 22:52")
    assert dt == datetime(2026, 10, 28, 22, 52, tzinfo=HKT)
    assert dt.utcoffset() == timedelta(hours=8)


@pytest.mark.parametrize(
    "bad", ["", "2026-10-28 22:52", "28/10/2026", "31/02/2026 10:00", "28/10/2026 25:00"]
)
def test_parse_hkex_datetime_rejects_malformed(bad: str) -> None:
    with pytest.raises(ValueError, match="DATE_TIME"):
        parse_hkex_datetime(bad)


def test_today_is_hong_kong_date_not_utc_date() -> None:
    # 17:30 UTC on 29 Oct is already 01:30 on 30 Oct in Hong Kong.
    now = datetime(2026, 10, 29, 17, 30, tzinfo=UTC)
    assert today_hkt(lambda: now) == date(2026, 10, 30)
    # 15:59 UTC is still the same day in Hong Kong (23:59).
    assert today_hkt(lambda: datetime(2026, 10, 29, 15, 59, tzinfo=UTC)) == date(2026, 10, 29)


def test_today_requires_a_timezone_aware_clock() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        today_hkt(lambda: datetime(2026, 10, 29, 12, 0))


def test_hkex_date_format() -> None:
    assert hkex_date(date(2026, 1, 5)) == "20260105"
