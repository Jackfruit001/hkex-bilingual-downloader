from datetime import date

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.domain.errors import AppError, ErrorCode
from app.domain.validation import normalise_stock_code, parse_iso_date, validate_date_range

TODAY = date(2026, 10, 30)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("700", "00700"),
        ("0700", "00700"),
        ("00700", "00700"),
        ("700.HK", "00700"),
        ("700.hk", "00700"),
        (" 0700 . Hk ", "00700"),
        ("1", "00001"),
        ("09688", "09688"),
        ("０７００", "00700"),  # full-width digits from a Chinese input method
    ],
)
def test_normalise_stock_code_accepts_common_forms(raw: str, expected: str) -> None:
    assert normalise_stock_code(raw) == expected


@pytest.mark.parametrize(
    "raw", ["", "   ", "abc", "123456", "70O", "-700", "7.00", ".HK", "700.HK.HK", "٣٣٣", "²"]
)
def test_normalise_stock_code_rejects_bad_input(raw: str) -> None:
    with pytest.raises(AppError) as exc:
        normalise_stock_code(raw)
    assert exc.value.code is ErrorCode.INVALID_STOCK_CODE
    assert "up to 5 digits" in exc.value.message


@given(st.integers(min_value=0, max_value=99999))
def test_normalise_round_trips_any_five_digit_code(n: int) -> None:
    code = f"{n:05d}"
    assert normalise_stock_code(str(n)) == code
    assert normalise_stock_code(code + ".HK") == code
    assert len(code) == 5


@given(st.text())
def test_normalise_never_returns_anything_but_five_ascii_digits(raw: str) -> None:
    try:
        out = normalise_stock_code(raw)
    except AppError as exc:
        assert exc.code is ErrorCode.INVALID_STOCK_CODE
    else:
        assert len(out) == 5
        assert all(c in "0123456789" for c in out)


def test_valid_range_including_single_day_and_today() -> None:
    validate_date_range(date(2026, 10, 28), date(2026, 10, 28), TODAY)
    validate_date_range(date(2026, 10, 1), TODAY, TODAY)
    validate_date_range(date(1999, 4, 1), TODAY, TODAY)


@pytest.mark.parametrize(
    ("start", "end", "fragment"),
    [
        (date(2026, 10, 29), date(2026, 10, 28), "start date is after the end date"),
        (
            date(2026, 10, 1),
            date(2026, 10, 31),
            "end date is in the future; today in Hong Kong is 2026-10-30",
        ),
        (date(1999, 3, 31), date(2000, 1, 1), "start on 1 April 1999"),
    ],
)
def test_invalid_ranges_say_why(start: date, end: date, fragment: str) -> None:
    with pytest.raises(AppError) as exc:
        validate_date_range(start, end, TODAY)
    assert exc.value.code is ErrorCode.INVALID_DATE_RANGE
    assert fragment in exc.value.message


def test_start_after_end_is_reported_before_future_end() -> None:
    with pytest.raises(AppError) as exc:
        validate_date_range(date(2026, 12, 2), date(2026, 12, 1), TODAY)
    assert "after the end date" in exc.value.message


def test_parse_iso_date_is_strict() -> None:
    assert parse_iso_date("2026-10-28") == date(2026, 10, 28)
    for bad in ["20261028", "2026-1-28", "28/10/2026", "2026-02-30", "", "2026-10-28T00:00"]:
        with pytest.raises(AppError) as exc:
            parse_iso_date(bad)
        assert exc.value.code is ErrorCode.INVALID_DATE_RANGE
