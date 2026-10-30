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
- **Annual reports published in each language separately** (HKEX allows it) are handled by a
  rule that looks for the other language up to 14 days away and shows the result as "Check
  pairing". That rule is tested with synthetic documents only: no real example was found in the
  annual-report seasons of 13 issuers, so it has not been verified against HKEXnews.
- **Checking contents** compares figures in the two PDFs. About a third of the Chinese PDFs
  sampled (21 of 62) have text that cannot be read, so for those the check says it is
  unavailable and the pairing stays "Check pairing" unless other evidence confirms it (D-013).
