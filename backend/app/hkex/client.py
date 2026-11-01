"""Polite HTTP client for HKEXnews.

Bounded concurrency, spacing between requests, retries with exponential backoff and jitter,
`Retry-After` support, an identifying User-Agent, and a hard allowlist of hosts. Redirects are
never followed: a redirect from these endpoints means something is wrong.
"""

import asyncio
import json
import random
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.config import Settings
from app.config import settings as default_settings
from app.domain.errors import AppError, ErrorCode

ALLOWED_HOSTS = frozenset({"www1.hkexnews.hk", "www.hkexnews.hk"})
RETRY_AFTER_CAP_S = 30.0

_UNAVAILABLE = "HKEXnews didn't respond. Try again in a minute."
_RATE_LIMITED = "HKEXnews is limiting requests. Retrying shortly."
MAX_DOWNLOAD_BYTES = 150 * 1024 * 1024


@dataclass(frozen=True)
class Download:
    """A fully received body and the length the server announced for it (if any)."""

    body: bytes
    content_length: int | None


def check_allowed_url(url: str) -> None:
    """Only https URLs on the HKEXnews hosts, with no user info and no unusual port."""
    parts = urlsplit(url)
    if (
        parts.scheme != "https"
        or parts.hostname not in ALLOWED_HOSTS
        or parts.username is not None
        or parts.port not in (None, 443)
    ):
        raise ValueError(f"URL is not on the HKEXnews allowlist: {url[:80]}")


def parse_retry_after(value: str | None, now: datetime | None = None) -> float | None:
    """Seconds from a `Retry-After` header (integer seconds or an HTTP date), capped."""
    if not value:
        return None
    value = value.strip()
    if value.isdigit():
        return min(float(value), RETRY_AFTER_CAP_S)
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    seconds = (when - (now or datetime.now(UTC))).total_seconds()
    return min(max(seconds, 0.0), RETRY_AFTER_CAP_S)


class _Retryable(Exception):
    def __init__(self, status: int | None, retry_after: float | None = None) -> None:
        super().__init__(f"retryable failure (status {status})")
        self.status = status
        self.retry_after = retry_after


class HkexClient:
    def __init__(
        self,
        *,
        config: Settings = default_settings,
        http: httpx.AsyncClient | None = None,
        max_concurrency: int = 4,
        min_interval_s: float = 0.25,
        max_retries: int = 3,
        base_backoff_s: float = 1.0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], float] = time.monotonic,
        jitter: Callable[[], float] = random.random,
    ) -> None:
        self._http = http or httpx.AsyncClient(
            headers={"User-Agent": config.user_agent},
            timeout=httpx.Timeout(config.read_timeout_s, connect=config.connect_timeout_s),
            follow_redirects=False,
        )
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._pace_lock = asyncio.Lock()
        self._next_start = 0.0
        self._min_interval = min_interval_s
        self._max_retries = max_retries
        self._base_backoff = base_backoff_s
        self._sleep = sleep
        self._clock = clock
        self._jitter = jitter
        self.requests_made = 0
        self.retries_made = 0

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _pace(self) -> None:
        async with self._pace_lock:
            wait = self._next_start - self._clock()
            if wait > 0:
                await self._sleep(wait)
            self._next_start = self._clock() + self._min_interval

    async def _attempt(self, url: str, params: Mapping[str, Any] | None) -> Any:
        async with self._semaphore:
            await self._pace()
            self.requests_made += 1
            try:
                response = await self._http.get(url, params=params)
            except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as exc:
                raise _Retryable(None) from exc
        status = response.status_code
        if status == 429:
            raise _Retryable(status, parse_retry_after(response.headers.get("retry-after")))
        if status >= 500:
            raise _Retryable(status, parse_retry_after(response.headers.get("retry-after")))
        if status != 200:
            raise AppError(ErrorCode.HKEX_UNAVAILABLE, _UNAVAILABLE, {"status": status})
        try:
            return json.loads(response.text)
        except ValueError as exc:  # an HTML page (for example a bot challenge) with status 200
            raise _Retryable(status) from exc

    async def _attempt_download(self, url: str) -> Download:
        async with self._semaphore:
            await self._pace()
            self.requests_made += 1
            try:
                async with self._http.stream("GET", url) as response:
                    status = response.status_code
                    if status == 429 or status >= 500:
                        retry_after = parse_retry_after(response.headers.get("retry-after"))
                        raise _Retryable(status, retry_after)
                    if status != 200:  # includes redirects, which are never followed
                        raise AppError(
                            ErrorCode.DOWNLOAD_FAILED,
                            "HKEXnews didn't send the file. Nothing was saved.",
                            {"status": status},
                        )
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body += chunk
                        if len(body) > MAX_DOWNLOAD_BYTES:
                            raise AppError(
                                ErrorCode.DOWNLOAD_FAILED,
                                "The file is larger than this app allows. Nothing was saved.",
                            )
                    announced = response.headers.get("content-length", "")
            except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as exc:
                raise _Retryable(None) from exc
        length = int(announced) if announced.isdigit() else None
        if length is not None and length != len(body):
            raise _Retryable(200)  # cut short: try again before giving up
        return Download(bytes(body), length)

    async def get_bytes(self, url: str) -> Download:
        """A whole file, retried like any request; the caller verifies what it contains."""
        check_allowed_url(url)
        return await self._with_retries(lambda: self._attempt_download(url), download=True)

    async def get_json(self, url: str, params: Mapping[str, Any] | None = None) -> Any:
        check_allowed_url(url)
        return await self._with_retries(lambda: self._attempt(url, params), download=False)

    async def _with_retries[T](
        self, attempt_once: Callable[[], Awaitable[T]], *, download: bool
    ) -> T:
        failure: _Retryable | None = None
        for attempt in range(self._max_retries + 1):
            if failure is not None:
                delay = failure.retry_after
                if delay is None:
                    delay = (
                        self._base_backoff * 2 ** (attempt - 1)
                        + self._jitter() * self._base_backoff
                    )
                await self._sleep(delay)
                self.retries_made += 1
            try:
                return await attempt_once()
            except _Retryable as exc:
                failure = exc
        assert failure is not None
        if failure.status == 429:
            raise AppError(ErrorCode.HKEX_RATE_LIMITED, _RATE_LIMITED, {"status": 429})
        if download and failure.status == 200:
            raise AppError(
                ErrorCode.VERIFY_FAILED,
                "HKEXnews sent an incomplete file. Nothing was saved.",
                {"reason": "shorter than announced"},
            )
        if download:
            raise AppError(
                ErrorCode.DOWNLOAD_FAILED,
                "The file couldn't be downloaded (the connection failed). Nothing was saved.",
                {"status": failure.status},
            )
        raise AppError(ErrorCode.HKEX_UNAVAILABLE, _UNAVAILABLE, {"status": failure.status})
