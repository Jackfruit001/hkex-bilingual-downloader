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

- **Documents before 25 June 2007** have no headline categories, and their file numbers are
  irregular, so time and file numbers cannot confirm a pairing. Every such pair is shown as
  "Check pairing" unless the two files are identical or "Check contents" is conclusive (D-009
  and D-015 in `docs/DECISIONS.md`).
- **Reused stock codes** (for example 00700, once YAOHAN INT'L's) search the company that is
  listed today. The delisted earlier holders are shown as a switch, not hidden (D-010).
- **Annual reports published in each language separately** (HKEX allows it) are handled by a
  rule that looks for the other language up to 14 days away and shows the result as "Check
  pairing". That rule is tested with synthetic documents only: no real example was found in the
  annual-report seasons of 13 issuers, so it has not been verified against HKEXnews.
- **The golden pairing set** (the hand-checked test of the matcher) was verified by AI reading of
  both documents and confirmed by a person, not by a person opening every PDF (D-014).
- **Checking contents** compares figures in the two PDFs. About a third of the Chinese PDFs
  sampled (21 of 62) have text that cannot be read, so for those the check says it is
  unavailable and the pairing stays "Check pairing" unless other evidence confirms it (D-013).
  Two documents that share their figures can fool it: in the golden set, two 2005 HSBC scrip
  dividend forms matched at 92% and the check confirmed the wrong one (M-015, open).
