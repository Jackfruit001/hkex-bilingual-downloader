# Testing

Filled in as tests are written. Built from the requirements table in `docs/SPEC.md` section 2.

## Run the tests

```
cd backend
uv run pytest              # offline tests (default)
uv run pytest -m live      # opt-in live HKEXnews tests (a smoke test and a real pair ZIP)
uv run ruff check . && uv run mypy app

cd frontend
npm test                   # Vitest: date logic
npm run e2e                # Playwright: browser journeys against the app in fixture mode
```

CI runs the backend on Ubuntu, macOS and Windows and the frontend on Ubuntu (`.github/workflows/ci.yml`).

## Results (1 November 2026)

| Suite | Result |
|---|---|
| Backend, offline | 991 passed, 1 expected failure (the open M-015 case), 2 live tests not run |
| Frontend unit (Vitest) | 4 passed |
| Browser journeys (Playwright, fixture mode) | 5 passed |
| Ruff, mypy strict on `backend/app` | clean |

What each area covers:

- **Pairing:** unit tests for every signal and rule; 11 recorded scenarios replayed; a golden set of
  74 hand-verified announcements from 21 issuers (same-minute batches, interleaved numbers, stubs
  in both directions, revised headlines, identical bilingual files, pre-2007 files, a delisted
  company, a web-page entry). Zero wrong confirmations from the rules alone. Hypothesis checks the
  invariants.
- **Same-day announcements:** the Tencent and Zai Lab scenarios hold several announcements in one
  minute; the layout rule keeps them as "Check pairing" when file order cannot tell them apart.
- **Missing results:** English-only and Chinese-only entries, stubs, and the empty range (a 404
  with a message) are in the matcher, API and browser tests.
- **Filenames:** 196 tests: 41 real titles, Hypothesis properties, and every one of the 6,316
  recorded PDFs checked for validity on Windows, macOS and Linux, length, and unique names.
  Mutation testing killed every non-equivalent mutant (M-018).
- **Failed downloads (fault injection with respx):** timeout; connection reset then success; 500
  then success; 429 with `Retry-After`; body shorter than `Content-Length`; HTML page with status
  200; non-PDF bytes; redirect to another site (never followed); 404. A failed file never produces
  a ZIP, and "Retry failed files" fetches only what failed.
- **Security:** a client sending another site's URL or a path with `..` is refused before any fetch.
- **API:** every error carries a code and a message; unknown fields are rejected; rate limiting.

### Not yet run

- The live Gate 3 test (`uv run pytest -m live`) and `scripts/audit_random.py` need approval for
  live HKEXnews calls. Audit results will be added here as `docs/audit-report.md`.
- Windows check by hand (Chrome and Edge downloads, Chinese filenames, ZIP in File Explorer).
- The hosted app's smoke test.

## The golden pairing set (SPEC section 10.4)

`backend/tests/golden/pairs.yaml` holds hand-verified English and Chinese pairs. Drafts are made by `scripts/golden_helper.py`; an entry counts only once it is `verified: true`. Claude read both documents of each entry and Zarif confirmed the result; Zarif did not open every PDF (D-014). Design and limits: `docs/DECISIONS.md` D-012.

```
uv run --project backend python scripts/golden_helper.py coverage                       # what is still missing
uv run --project backend python scripts/golden_helper.py show 09688-12386841            # evidence and PDF paths for one entry
uv run --project backend python scripts/golden_helper.py draft 00700 2026-10-01 2026-10-30   # table only
uv run --project backend python scripts/golden_helper.py draft 00700 2026-10-01 2026-10-30 --pick 3,7
uv run --project backend python scripts/golden_helper.py draft 00700 2026-10-01 2026-10-30 --offline --pick 3   # cache only
scripts/golden_drafts.sh --offline                                                      # the first 68 drafts, from the cache
```

The golden test judges the matcher against the verified entries, offline, and prints a metrics table with `-s`. Each entry is a test in two runs (rules plus identical bytes; and with the content check), and a wrong `matched` fails it. A known open failure is marked as a strict expected failure with its reason (`KNOWN_WRONG` in the test); fixing it makes the marker fail until it is removed.

```
cd backend && uv run pytest tests/integration/test_golden.py -s
```

Live runs are one request at a time, at least a second apart, and stop at the first refusal. Everything is cached under `scripts/.golden_cache/` (not committed, PDFs included). A run that writes entries also records the search responses it used under `backend/tests/fixtures/golden/`; PDFs are never committed, only their hashes and figure fingerprints (`backend/tests/golden/fingerprints.json`).

## Audit on random stocks (1 November 2026)

`scripts/audit_random.py --stocks 30 --seed 1`: 30 random active securities (25 ordinary shares or
funds, 5 warrants and other products), last 90 days, live HKEXnews. Full table: `docs/audit-report.md`.

- 30 of 30 searches worked; 760 announcements, 759 "Matched", 1 "Check pairing", none single-language.
- 25 stocks had a confirmed pair: both PDFs downloaded, verified and zipped; 0 failures. The other 5
  had no announcements in the period.
- **One failure found and fixed.** For 00135 the only "Check pairing" entry is a shared HKEXnews web
  page (`/dod/en.html`) listed as a PDF. The app handled it correctly (not downloadable, linked to
  HKEXnews), but the audit script tried to content-check it and the page offered "Check contents".
  Both now skip entries that are not downloadable PDFs.
- **What the audit cannot show:** it counts statuses, not whether each "Matched" is right. That is
  what the golden set is for. A very high "Matched" share is expected here because many securities
  are funds and structured products that publish in both languages at once.
