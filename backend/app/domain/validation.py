"""Input validation as pure functions (SPEC §3.1)."""

import re
from datetime import date

from app.domain.errors import AppError, ErrorCode

EARLIEST_DATE = date(1999, 4, 1)  # earliest HKEXnews records (SPEC §3.1)

_STOCK_CODE = re.compile(r"[0-9]{1,5}")
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$", re.ASCII)

# Chinese input methods produce full-width digits; fold only those, nothing else.
_FULL_WIDTH_DIGITS = {0xFF10 + i: ord("0") + i for i in range(10)}

_INVALID_CODE_MESSAGE = "Enter a stock code of up to 5 digits, for example 00700."


def normalise_stock_code(raw: str) -> str:
    """`700`, `0700`, `700.HK` and full-width digits all become the 5-digit string `00700`."""
    text = re.sub(r"\s+", "", raw.translate(_FULL_WIDTH_DIGITS))
    if text.lower().endswith(".hk"):
        text = text[:-3]
    if not _STOCK_CODE.fullmatch(text):
        raise AppError(ErrorCode.INVALID_STOCK_CODE, _INVALID_CODE_MESSAGE, {"input": raw[:40]})
    return text.zfill(5)


def parse_iso_date(raw: str) -> date:
    """Strict `YYYY-MM-DD`; no other spelling is accepted."""
    if _ISO_DATE.match(raw):
        try:
            return date.fromisoformat(raw)
        except ValueError:
            pass
    raise AppError(
        ErrorCode.INVALID_DATE_RANGE,
        f"'{raw[:20]}' is not a date. Use the form YYYY-MM-DD, for example 2026-10-28.",
    )


def validate_date_range(start: date, end: date, today: date) -> None:
    """Both ends inclusive. `today` is today's date in Hong Kong."""
    if start > end:
        raise AppError(ErrorCode.INVALID_DATE_RANGE, "The start date is after the end date.")
    if end > today:
        raise AppError(
            ErrorCode.INVALID_DATE_RANGE,
            f"The end date is in the future; today in Hong Kong is {today.isoformat()}.",
        )
    if start < EARLIEST_DATE:
        raise AppError(ErrorCode.INVALID_DATE_RANGE, "HKEXnews records start on 1 April 1999.")
