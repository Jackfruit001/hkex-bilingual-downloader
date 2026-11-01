"""HTTP routes (SPEC §7). Thin: validation, then the domain code, then the response shape."""

import asyncio
import os
import time
from collections import defaultdict, deque
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import httpx
from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse

from app.api.schemas import (
    AnnouncementOut,
    ContentCheckRequest,
    DocumentOut,
    DownloadRequest,
    RivalOut,
    SearchRequest,
    SearchResponse,
    StockOut,
)
from app.domain.errors import AppError, ErrorCode
from app.domain.models import Document, Lang, Stock
from app.domain.timeutil import today_hkt
from app.domain.validation import normalise_stock_code, parse_iso_date, validate_date_range
from app.downloads.fetcher import Fetcher
from app.downloads.jobs import JobManager
from app.hkex.client import HkexClient
from app.hkex.reference import ReferenceData, ReferenceService
from app.hkex.search import search_both
from app.naming.filenames import content_disposition, name_documents, pair_zip_name
from app.pairing.content_check import (
    TextStatus,
    best_match,
    extract_text_async,
    fingerprint,
    readable,
)
from app.pairing.matcher import pair_documents
from app.pairing.models import Announcement

STATUS_HTTP = {
    ErrorCode.INVALID_STOCK_CODE: 400,
    ErrorCode.INVALID_DATE_RANGE: 400,
    ErrorCode.INVALID_DOCUMENT_PATH: 400,
    ErrorCode.UNKNOWN_STOCK_CODE: 404,
    ErrorCode.NO_RESULTS: 404,
    ErrorCode.AMBIGUOUS_STOCK_CODE: 409,
    ErrorCode.NOT_A_PDF: 422,
    ErrorCode.TOO_MANY_RESULTS: 413,
    ErrorCode.DOWNLOAD_LIMIT_EXCEEDED: 413,
    ErrorCode.HKEX_RATE_LIMITED: 503,
    ErrorCode.HKEX_UNAVAILABLE: 502,
    ErrorCode.DOWNLOAD_FAILED: 502,
    ErrorCode.VERIFY_FAILED: 502,
    ErrorCode.ZIP_INCOMPLETE: 502,
}


@dataclass
class AppState:
    client: HkexClient
    reference: ReferenceService
    fetcher: Fetcher
    jobs: JobManager


def build_state() -> AppState:
    if os.environ.get("HKEX_MODE") == "fixtures":
        from app.api.fixtures import fixture_transport

        http = httpx.AsyncClient(transport=fixture_transport(), headers={"User-Agent": "fixtures"})
        client = HkexClient(http=http, min_interval_s=0.0)
    else:
        client = HkexClient()
    fetcher = Fetcher(client)
    return AppState(client, ReferenceService(client), fetcher, JobManager(fetcher))


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.hkex = build_state()
    yield
    await app.state.hkex.client.aclose()


class RateLimiter:
    """At most `limit` calls per client address per minute, kept in memory."""

    def __init__(self, limit: int, window_s: float = 60.0) -> None:
        self._limit, self._window = limit, window_s
        self._calls: dict[str, deque[float]] = defaultdict(deque)

    def check(self, request: Request) -> None:
        forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        who = forwarded or (request.client.host if request.client else "unknown")
        now, calls = time.monotonic(), self._calls[who]
        while calls and now - calls[0] > self._window:
            calls.popleft()
        if len(calls) >= self._limit:
            raise AppError(
                ErrorCode.HKEX_RATE_LIMITED,
                "Too many requests from your connection. Wait a minute and try again.",
            )
        calls.append(now)


search_limit = RateLimiter(20)
download_limit = RateLimiter(30)
router = APIRouter(prefix="/api")


def state_of(request: Request) -> AppState:
    state: AppState = request.app.state.hkex
    return state


async def app_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)
    return JSONResponse(exc.to_dict(), status_code=STATUS_HTTP.get(exc.code, 500))


# --- stocks and categories -----------------------------------------------------------------------


def _stock_out(s: Stock) -> StockOut:
    return StockOut(
        stock_id=s.stock_id, code=s.code, name_en=s.name_en, name_tc=s.name_tc, active=s.active
    )


@router.get("/stocks")
async def stocks(request: Request, q: str = "") -> list[StockOut]:
    ref = await state_of(request).reference.get()
    return [_stock_out(s) for s in ref.stocks.search(q[:40])]


@router.get("/categories")
async def categories(request: Request) -> list[dict[str, str]]:
    ref = await state_of(request).reference.get()
    return [
        {"code": code, "name_en": en, "name_tc": tc} for code, en, tc in ref.categories.top_level()
    ]


# --- search --------------------------------------------------------------------------------------


def _document_out(doc: Document, names: dict[str, str]) -> DocumentOut:
    return DocumentOut(
        path=doc.path,
        title=doc.title,
        file_type=doc.file_type,
        size_label=doc.size_label,
        source_url=doc.source_url,
        filename=names.get(doc.path),
        downloadable=doc.path in names,
    )


def _announcement_out(a: Announcement, names: dict[str, str], code: str) -> AnnouncementOut:
    en, tc = a.en, a.tc
    primary = en or tc
    zip_ready = en is not None and tc is not None and en.path in names and tc.path in names
    return AnnouncementOut(
        id=a.id,
        status=a.status.value,
        release_at=a.release_at.isoformat(timespec="minutes"),
        category=primary.category_text if primary else "",
        en=_document_out(en, names) if en else None,
        tc=_document_out(tc, names) if tc else None,
        evidence=list(a.evidence),
        notice_url=a.stub.source_url if a.stub else None,
        rivals=[
            RivalOut(
                lang=r.document.lang.value,
                title=r.document.title,
                path=r.document.path,
                score=r.score,
            )
            for r in a.rivals
        ],
        format=a.format.value,
        bilingual=a.bilingual,
        separate=a.separate,
        pair_zip_name=pair_zip_name(a.release_at, code, en.title) if zip_ready and en else None,
        pair_zip_downloadable=zip_ready,
    )


def _wanted(a: Announcement, req: SearchRequest, ref: ReferenceData) -> bool:
    if req.keyword:
        needle = req.keyword.casefold()
        if not any(d and needle in d.title.casefold() for d in (a.en, a.tc)):
            return False
    if req.categories:
        codes = {c for d in (a.en, a.tc) if d for c in d.category_codes}
        tops = {ref.categories.parent_of(c) for c in codes}
        if not tops & set(req.categories):
            return False
    return True


async def run_search(state: AppState, req: SearchRequest) -> SearchResponse:
    code = normalise_stock_code(req.stock_code)
    start, end = parse_iso_date(req.start), parse_iso_date(req.end)
    validate_date_range(start, end, today_hkt())
    ref = await state.reference.get()
    resolution = ref.stocks.resolve(code, req.stock_id)
    found = await search_both(state.client, resolution.stock, start, end, ref.categories)
    if not found.english and not found.chinese:
        raise AppError(
            ErrorCode.NO_RESULTS,
            f"No announcements for {code} between {start:%d %b %Y} and {end:%d %b %Y} "
            "(Hong Kong time). Try a wider range.",
            {"code": code},
        )
    paired = pair_documents(found.english, found.chinese, searched=(start, end))
    names = name_documents([*found.english, *found.chinese], code)
    shown = [a for a in paired.announcements if _wanted(a, req, ref)]
    shown.sort(key=lambda a: a.release_at, reverse=True)
    summary = {"total": len(shown)}
    for a in shown:
        summary[a.status.value] = summary.get(a.status.value, 0) + 1
    return SearchResponse(
        company=_stock_out(resolution.stock),
        alternatives=[_stock_out(s) for s in resolution.alternatives],
        start=start.isoformat(),
        end=end.isoformat(),
        announcements=[_announcement_out(a, names, code) for a in shown],
        summary=summary,
        warnings=[*found.diagnostics.warnings, *paired.diagnostics.warnings],
        diagnostics={
            "english": found.diagnostics.english.__dict__,
            "chinese": found.diagnostics.chinese.__dict__,
            "outside_range": found.diagnostics.outside_range,
            "seconds": found.diagnostics.duration_s,
            "pairing": paired.diagnostics.by_status,
            "reference": ref.source,
        },
    )


@router.post("/search")
async def search(request: Request, req: SearchRequest) -> SearchResponse:
    search_limit.check(request)
    return await run_search(state_of(request), req)


# --- content check -------------------------------------------------------------------------------


@router.post("/content-check")
async def content_check(request: Request, req: ContentCheckRequest) -> dict[str, object]:
    """Compare the figures in an English PDF with each candidate Chinese PDF (SPEC §4.5)."""
    search_limit.check(request)
    state = state_of(request)
    paths = [req.en_path, *req.tc_paths]
    files = await asyncio.gather(*(state.fetcher.fetch(p) for p in paths))
    texts = []
    for lang, verified in zip(["en", *["tc"] * len(req.tc_paths)], files, strict=True):
        extracted = await extract_text_async(verified.file.read_bytes())
        texts.append(readable(Lang(lang), extracted))
    unreadable = [t for t in texts if t.status is not TextStatus.OK]
    if unreadable:
        detail = unreadable[0].detail or "there is too little text to compare"
        return {"available": False, "message": f"Content check unavailable: {detail}."}
    prints = [fingerprint(t.text) for t in texts]
    verdict = best_match(req.en_path, prints[0], dict(zip(req.tc_paths, prints[1:], strict=True)))
    assert verdict is not None
    pct = round(verdict.score * 100)
    message = (
        f"Content check: {pct}% of the figures in the English file appear in the Chinese file."
    )
    return {
        "available": True,
        "conclusive": verdict.conclusive,
        "best_path": verdict.tc_news_id,
        "score": verdict.score,
        "runner_up": verdict.runner_up,
        "message": message,
    }


# --- downloads -----------------------------------------------------------------------------------


@router.post("/downloads", status_code=202)
async def create_download(request: Request, req: DownloadRequest) -> dict[str, object]:
    download_limit.check(request)
    job = state_of(request).jobs.create(
        req.mode, [(i.path, i.filename) for i in req.items], req.zip_name
    )
    return job.to_dict()


@router.get("/downloads/{job_id}")
async def download_progress(request: Request, job_id: str) -> JSONResponse:
    job = state_of(request).jobs.get(job_id)
    if job is None:
        return JSONResponse(
            {"code": "DOWNLOAD_FAILED", "message": "This download has expired. Start it again."},
            status_code=404,
        )
    return JSONResponse(job.to_dict())


@router.post("/downloads/{job_id}/retry")
async def retry_download(request: Request, job_id: str) -> JSONResponse:
    job = state_of(request).jobs.retry(job_id)
    if job is None:
        return JSONResponse(
            {"code": "DOWNLOAD_FAILED", "message": "This download has expired. Start it again."},
            status_code=404,
        )
    return JSONResponse(job.to_dict())


@router.get("/downloads/{job_id}/file", response_model=None)
async def download_file(request: Request, job_id: str) -> FileResponse | JSONResponse:
    job = state_of(request).jobs.get(job_id)
    if job is None or job.result is None or job.state.value != "done":
        return JSONResponse(
            {
                "code": "DOWNLOAD_FAILED",
                "message": "This file isn't ready. Start the download again.",
            },
            status_code=409,
        )
    media = "application/pdf" if job.mode.value == "single" else "application/zip"
    return FileResponse(
        job.result,
        media_type=media,
        headers={"Content-Disposition": content_disposition(job.download_name)},
    )
