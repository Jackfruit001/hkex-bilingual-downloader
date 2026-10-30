# HKEX bilingual downloader

Enter a Hong Kong stock code and a date range, browse that company's HKEXnews announcements,
and download the English and Traditional Chinese PDFs, correctly paired and named.

**Status:** Phase 1 done (HKEXnews client and search); the pairing engine is next. Not usable yet.

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

## Known limitations

Kept current as the build progresses.

- **Documents before 25 June 2007** have no headline categories, so pairing has less evidence.
  They can only be shown as "Matched" under a stricter rule (D-009 in `docs/DECISIONS.md`);
  otherwise they are shown as "Check pairing". If testing shows the rule is unsafe, all
  pre-2007 pairs will be "Check pairing" and this section will say so.
- **Reused stock codes** (for example 00700, once YAOHAN INT'L's) search the company that is
  listed today. The delisted earlier holders are shown as a switch, not hidden (D-010).
