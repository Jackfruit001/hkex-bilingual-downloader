"""Error model. Every error carries a stable code and a message written for the user (SPEC §9)."""

from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
    INVALID_STOCK_CODE = "INVALID_STOCK_CODE"
    UNKNOWN_STOCK_CODE = "UNKNOWN_STOCK_CODE"
    AMBIGUOUS_STOCK_CODE = "AMBIGUOUS_STOCK_CODE"
    INVALID_DATE_RANGE = "INVALID_DATE_RANGE"
    NO_RESULTS = "NO_RESULTS"
    TOO_MANY_RESULTS = "TOO_MANY_RESULTS"
    HKEX_UNAVAILABLE = "HKEX_UNAVAILABLE"
    HKEX_RATE_LIMITED = "HKEX_RATE_LIMITED"
    NOT_A_PDF = "NOT_A_PDF"
    INVALID_DOCUMENT_PATH = "INVALID_DOCUMENT_PATH"
    DOWNLOAD_FAILED = "DOWNLOAD_FAILED"
    VERIFY_FAILED = "VERIFY_FAILED"
    ZIP_INCOMPLETE = "ZIP_INCOMPLETE"
    DOWNLOAD_LIMIT_EXCEEDED = "DOWNLOAD_LIMIT_EXCEEDED"


class AppError(Exception):
    def __init__(
        self, code: ErrorCode, message: str, details: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details

    def to_dict(self) -> dict[str, Any]:
        body: dict[str, Any] = {"code": self.code.value, "message": self.message}
        if self.details:
            body["details"] = self.details
        return body
