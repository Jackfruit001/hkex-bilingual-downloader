"""FastAPI application: health check now; API and static frontend in later phases."""

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import VERSION, settings

app = FastAPI(title="HKEX bilingual downloader", version=VERSION)


@app.get("/api/health")
def health() -> dict[str, str]:
    now = datetime.now(ZoneInfo(settings.timezone))
    return {"status": "ok", "version": VERSION, "time_hkt": now.isoformat(timespec="seconds")}


_frontend = Path(__file__).resolve().parent.parent / "static"
if _frontend.is_dir():
    app.mount("/", StaticFiles(directory=_frontend, html=True), name="frontend")
