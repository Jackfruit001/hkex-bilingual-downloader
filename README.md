# HKEX bilingual downloader

Enter a Hong Kong stock code and a date range, browse that company's HKEXnews announcements,
and download the English and Traditional Chinese PDFs, correctly paired and named.

**Status:** Phase 0 (scaffold and HKEXnews probe). Not usable yet.

## Run locally (backend)

```
cd backend && uv sync
uv run pytest
uv run uvicorn app.main:app --reload
```

## Run locally (frontend)

```
cd frontend && npm install && npm run dev
```

Full usage, limitations and reused projects are added in Phase 7.
