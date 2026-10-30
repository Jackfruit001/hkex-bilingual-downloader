"""Live access for the golden helper (Phase 2.4): cached, paced, budgeted, and it stops at a block.

One class, built on the app's `HkexClient`, so searches go through the same allowlist, header
and pacing code as the product. Differences, all on the side of being gentler:

- every answer is kept on disk, so a repeat costs nothing;
- one request at a time, at least a second apart, search and PDF requests sharing one clock;
- a hard budget of live requests per run (zero means offline: a cache miss is an error);
- no retries. The first 403, 429, challenge page, redirect or other failure ends the run.

This is not the product's download path. Verified downloads are Phase 3; here a PDF is only
read for its hash and the first pages' text, and is never offered to anyone.
"""

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from app.hkex.client import HkexClient, check_allowed_url

MIN_INTERVAL_S = 1.0
DEFAULT_BUDGET = 150
DEFAULT_MAX_BYTES = 30 * 1024 * 1024
_UNITS = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3}
_SIZE = re.compile(r"^\s*([\d.]+)\s*(B|KB|MB|GB)\s*$", re.IGNORECASE)


class HelperStopped(Exception):
    """HKEXnews did something unexpected; the run must end instead of asking again."""


class BudgetReached(HelperStopped):
    """The run has used its live requests (or was started offline)."""


class FileTooLarge(Exception):
    """One file is over the size cap. Skip it; the run can go on."""


@dataclass(frozen=True)
class RecordedCall:
    key: str
    url: str
    params: dict[str, Any]
    body: Any


def size_label_bytes(label: str) -> int | None:
    """Bytes from a listing label such as "84KB" or "1.5MB"; None for "Multi-Files" and blanks."""
    m = _SIZE.match(label)
    return int(float(m.group(1)) * _UNITS[m.group(2).upper()]) if m else None


def cache_key(url: str, params: Mapping[str, Any] | None) -> str:
    canon = json.dumps([url, sorted((str(k), str(v)) for k, v in (params or {}).items())])
    return hashlib.sha256(canon.encode()).hexdigest()


def write_call(folder: Path, call: RecordedCall) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    text = json.dumps(
        {"url": call.url, "params": call.params, "body": call.body}, ensure_ascii=False
    )
    (folder / f"{call.key}.json").write_text(text, encoding="utf-8")


class GoldenClient(HkexClient):
    def __init__(
        self,
        *,
        json_dir: Path,
        pdf_dir: Path,
        budget: int = DEFAULT_BUDGET,
        max_bytes: int = DEFAULT_MAX_BYTES,
        **kwargs: Any,
    ) -> None:
        super().__init__(max_concurrency=1, min_interval_s=MIN_INTERVAL_S, max_retries=0, **kwargs)
        self._json_dir = json_dir
        self._pdf_dir = pdf_dir
        self._budget = budget
        self._max_bytes = max_bytes
        self.calls: list[RecordedCall] = []

    def pdf_path(self, name: str) -> Path:
        return self._pdf_dir / name

    def _spend(self) -> None:
        if self.requests_made >= self._budget:
            raise BudgetReached(
                f"the budget of {self._budget} live requests is used"
                if self._budget
                else "offline: this is not in the cache and live requests are off"
            )

    async def get_json(self, url: str, params: Mapping[str, Any] | None = None) -> Any:
        key = cache_key(url, params)
        file = self._json_dir / f"{key}.json"
        body: Any = None
        if file.exists():
            try:
                body = json.loads(file.read_text(encoding="utf-8"))["body"]
            except (ValueError, KeyError):
                body = None  # a damaged cache file is a miss
        if body is None:
            self._spend()
            body = await super().get_json(url, params)
            write_call(self._json_dir, RecordedCall(key, url, dict(params or {}), body))
        self.calls.append(RecordedCall(key, url, dict(params or {}), body))
        return body

    async def get_pdf(self, url: str, name: str) -> bytes:
        check_allowed_url(url)
        if not name or name != Path(name).name or name.startswith("."):
            raise ValueError(f"Unsafe cache name: {name!r}")
        file = self._pdf_dir / name
        if file.exists():
            cached = file.read_bytes()
            if cached.startswith(b"%PDF-"):  # a cached file is only trusted if it looks like one
                return cached
        self._spend()
        data = await self._download(url)
        self._pdf_dir.mkdir(parents=True, exist_ok=True)
        partial = file.with_name(file.name + ".part")
        partial.write_bytes(data)
        partial.replace(file)
        return data

    async def _download(self, url: str) -> bytes:
        async with self._semaphore:
            await self._pace()
            self.requests_made += 1
            try:
                async with self._http.stream("GET", url) as response:
                    if response.status_code != 200:
                        raise HelperStopped(f"HKEXnews answered {response.status_code} for {url}")
                    declared = response.headers.get("content-length")
                    if declared and int(declared) > self._max_bytes:
                        raise FileTooLarge(f"{url} is {declared} bytes")
                    data = bytearray()
                    async for chunk in response.aiter_bytes():
                        data += chunk
                        if len(data) > self._max_bytes:
                            raise FileTooLarge(f"{url} is over {self._max_bytes} bytes")
                    received = response.num_bytes_downloaded
            except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as exc:
                raise HelperStopped(f"{type(exc).__name__} fetching {url}") from exc
        if declared and received != int(declared):
            raise HelperStopped(f"incomplete download of {url}: {received} of {declared} bytes")
        if not data.startswith(b"%PDF-"):
            raise HelperStopped(f"{url} is not a PDF (a block or error page?)")
        return bytes(data)
