"""FastAPI application: the API, and the built frontend when it is present."""

from collections.abc import Awaitable, Callable
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles

from app.api.routes import app_error_handler, lifespan, router
from app.config import VERSION, settings
from app.domain.errors import AppError

app = FastAPI(title="HKEX bilingual downloader", version=VERSION, lifespan=lifespan)
app.add_exception_handler(AppError, app_error_handler)
app.include_router(router)


@app.middleware("http")
async def noindex(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    response = await call_next(request)
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response


@app.get("/api/health")
def health() -> dict[str, str]:
    now = datetime.now(ZoneInfo(settings.timezone))
    return {"status": "ok", "version": VERSION, "time_hkt": now.isoformat(timespec="seconds")}


_frontend = Path(__file__).resolve().parent.parent / "static"
if _frontend.is_dir():
    app.mount("/", StaticFiles(directory=_frontend, html=True), name="frontend")
