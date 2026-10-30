# Testing

Filled in as tests are written. Built from the requirements table in `docs/SPEC.md` section 2.

## Run the tests

```
cd backend
uv run pytest              # offline tests (default)
uv run pytest -m live      # opt-in live HKEXnews smoke tests
uv run ruff check . && uv run mypy
```

## The golden pairing set (SPEC section 10.4)

`backend/tests/golden/pairs.yaml` holds hand-verified English and Chinese pairs. Drafts are made by `scripts/golden_helper.py`; an entry counts only after Zarif sets `verified: true` with both PDFs open. Design and limits: `docs/DECISIONS.md` D-012.

```
uv run --project backend python scripts/golden_helper.py coverage                       # what is still missing
uv run --project backend python scripts/golden_helper.py show 09688-12386841            # evidence and PDF paths for one entry
uv run --project backend python scripts/golden_helper.py draft 00700 2026-10-01 2026-10-30   # table only
uv run --project backend python scripts/golden_helper.py draft 00700 2026-10-01 2026-10-30 --pick 3,7
uv run --project backend python scripts/golden_helper.py draft 00700 2026-10-01 2026-10-30 --offline --pick 3   # cache only
scripts/golden_drafts.sh --offline                                                      # the first 68 drafts, from the cache
```

Live runs are one request at a time, at least a second apart, and stop at the first refusal. Everything is cached under `scripts/.golden_cache/` (not committed, PDFs included). A run that writes entries also records the search responses it used under `backend/tests/fixtures/golden/`; PDFs are never committed, only their hashes and figure fingerprints (`backend/tests/golden/fingerprints.json`).
