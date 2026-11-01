"""Fetch, verify and cache one HKEXnews PDF (SPEC §6).

A client only ever sends a document path. The path is checked against the allowlist and turned
into a URL here; nothing else is fetched. Files are verified before anything is offered.
"""

import asyncio
import hashlib
import io
import re
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader

from app.domain.errors import AppError, ErrorCode
from app.hkex.client import HkexClient

BASE_URL = "https://www1.hkexnews.hk"
PATH_RE = re.compile(
    r"^/listedco/listconews/[A-Za-z]+/\d{4}/\d{4}/(?:[A-Za-z0-9_]+/)?[A-Za-z0-9_]+\.(?:pdf|htm|html)$",
    re.IGNORECASE,
)
CACHE_TTL_S = 3600.0
CACHE_MAX_BYTES = 1024**3


@dataclass(frozen=True)
class VerifiedFile:
    path: str  # the HKEXnews path it came from
    file: Path
    size: int
    sha256: str
    pages: int


def source_url(path: str) -> str:
    """The HKEXnews URL for a document path; refuses anything that is not a listed-company PDF."""
    if not PATH_RE.fullmatch(path):
        raise AppError(
            ErrorCode.INVALID_DOCUMENT_PATH,
            "That is not an HKEXnews document path. Search again and use the download buttons.",
        )
    if not path.lower().endswith(".pdf"):
        raise AppError(
            ErrorCode.NOT_A_PDF,
            "This entry is a web page on HKEXnews, not a PDF. Open it on HKEXnews.",
        )
    return BASE_URL + path


def verify_pdf(data: bytes) -> tuple[str, int]:
    """SHA-256 and page count of a PDF; raises VERIFY_FAILED with the reason otherwise."""

    def fail(reason: str) -> AppError:
        return AppError(
            ErrorCode.VERIFY_FAILED,
            f"HKEXnews sent a file that isn't a complete PDF ({reason}). Nothing was saved.",
            {"reason": reason},
        )

    if not data.startswith(b"%PDF-"):
        raise fail("it is not a PDF file")
    try:
        pages = len(PdfReader(io.BytesIO(data), strict=False).pages)
    except Exception as exc:  # pypdf raises many kinds of error on damaged files
        raise fail("it can't be opened") from exc
    if pages < 1:
        raise fail("it has no pages")
    return hashlib.sha256(data).hexdigest(), pages


class Fetcher:
    """Downloads verified PDFs into a disk cache; the same path within an hour is not re-fetched."""

    def __init__(
        self,
        client: HkexClient,
        *,
        directory: Path | None = None,
        max_concurrency: int = 6,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client = client
        self._dir = directory or Path(tempfile.mkdtemp(prefix="hkex-cache-"))
        self._dir.mkdir(parents=True, exist_ok=True)
        self._slots = asyncio.Semaphore(max_concurrency)
        self._clock = clock
        self._cache: dict[str, tuple[float, VerifiedFile]] = {}
        self.cache_hits = 0

    def _cached(self, path: str) -> VerifiedFile | None:
        entry = self._cache.get(path)
        if entry is None:
            return None
        stored_at, verified = entry
        if self._clock() - stored_at > CACHE_TTL_S or not verified.file.exists():
            self._cache.pop(path, None)
            return None
        return verified

    def _evict(self) -> None:
        """Drop the oldest files while the cache is over its size cap."""
        total = sum(v.size for _, v in self._cache.values())
        for path, (_, verified) in sorted(self._cache.items(), key=lambda kv: kv[1][0]):
            if total <= CACHE_MAX_BYTES:
                break
            verified.file.unlink(missing_ok=True)
            del self._cache[path]
            total -= verified.size

    async def fetch(self, path: str) -> VerifiedFile:
        url = source_url(path)
        if (hit := self._cached(path)) is not None:
            self.cache_hits += 1
            return hit
        async with self._slots:
            download = await self._client.get_bytes(url)
        sha256, pages = verify_pdf(download.body)
        target = self._dir / f"{hashlib.sha1(path.encode()).hexdigest()}.pdf"
        target.write_bytes(download.body)
        verified = VerifiedFile(path, target, len(download.body), sha256, pages)
        self._cache[path] = (self._clock(), verified)
        self._evict()
        return verified
