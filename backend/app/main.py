"""FastAPI application: health check and temporary probe now; API and frontend in later phases."""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import VERSION, settings

app = FastAPI(title="HKEX bilingual downloader", version=VERSION)

HKEX = "https://www1.hkexnews.hk"
# TEMPORARY (Phase 0, task 0.4): fixed targets only, no client input reaches a URL.
# Remove after Gate 0.
PROBE_SEARCH: dict[str, str | int] = {
    "sortDir": 0, "sortByOptions": "DateTime", "category": 0, "market": "SEHK",
    "stockId": 1000057951, "documentType": -1, "fromDate": "20261028", "toDate": "20261028",
    "title": "", "searchType": 0, "t1code": -2, "t2Gcode": -2, "t2code": -2,
    "rowRange": 100, "lang": "ZH",
}
PROBE_PDF = "/listedco/listconews/sehk/2026/1028/2026102801740_c.pdf"


@app.get("/api/health")
def health() -> dict[str, str]:
    now = datetime.now(ZoneInfo(settings.timezone))
    return {"status": "ok", "version": VERSION, "time_hkt": now.isoformat(timespec="seconds")}


@app.get("/api/probe")
async def probe() -> dict[str, Any]:
    """Reachability check from the hosting environment: one search and one PDF range request."""
    out: dict[str, Any] = {"user_agent": settings.user_agent}
    timeout = httpx.Timeout(settings.read_timeout_s, connect=settings.connect_timeout_s)
    async with httpx.AsyncClient(headers={"User-Agent": settings.user_agent}, timeout=timeout) as c:
        started = time.monotonic()
        try:
            r = await c.get(f"{HKEX}/search/titleSearchServlet.do", params=PROBE_SEARCH)
            ok = r.status_code == 200
            rows = json.loads(json.loads(r.text).get("result") or "[]") if ok else []
            cookies = sorted({k.split("=")[0] for k in r.headers.get_list("set-cookie")})
            out["search"] = {
                "status": r.status_code,
                "seconds": round(time.monotonic() - started, 2),
                "content_type": r.headers.get("content-type"),
                "rows": len(rows),
                "set_cookie_names": cookies,
            }
        except (httpx.HTTPError, ValueError) as exc:
            out["search"] = {"error": type(exc).__name__, "detail": str(exc)[:200]}
        started = time.monotonic()
        try:
            r = await c.get(f"{HKEX}{PROBE_PDF}", headers={"Range": "bytes=0-1023"})
            out["pdf"] = {"status": r.status_code, "seconds": round(time.monotonic() - started, 2),
                          "content_type": r.headers.get("content-type"),
                          "starts_with_pdf_magic": r.content[:5] == b"%PDF-"}
        except httpx.HTTPError as exc:
            out["pdf"] = {"error": type(exc).__name__, "detail": str(exc)[:200]}
    out["time_hkt"] = datetime.now(ZoneInfo(settings.timezone)).isoformat(timespec="seconds")
    return out


_frontend = Path(__file__).resolve().parent.parent / "static"
if _frontend.is_dir():
    app.mount("/", StaticFiles(directory=_frontend, html=True), name="frontend")
