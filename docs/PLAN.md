# Plan

**Status (1 Nov 2026):** Phases 3 to 5 built in one day on Zarif's instruction (D-017): 991 backend tests pass plus 1 expected failure (2 live tests are opt-in), 4 Vitest tests, 5 Playwright journeys, ruff and strict mypy clean. Open: Zarif's review of the 30 sample filenames (3.1), a hosted deploy and smoke test (6.1, 6.2), the live Gate 3 pair test and the random audit (6.3), which need live-call approval, the Windows check (6.4) and the README time spent. Earlier status: Phase 2 done, Gate 2 approved by Zarif (31 October 2026): 2.1 to 2.6 done (matcher, evidence, content check, golden helper, golden set, golden test; D-011 to D-014). The 2.4 findings were settled on 31 October (D-013): GEM paths fixed, unreadable Chinese text rule added to the content check, separate annual report an accepted README limitation. 2.5 done (D-014): Claude read the drafts and Zarif confirmed; 74 of 75 entries verified from 21 issuers (72 agreed, 2 corrected including one wrong `matched`, M-014; 2 duplicates deleted; 1 `.doc` left unverified). 2.6 done (74 verified entries judged offline: 50 confirmed and right, 1 wrong `matched` expected and open (M-014), 12 for checking, 1 pair shown apart, 10 single; with the content check 56 confirmed and 6 for checking; 717 tests passed, 2 expected failures). The four Gate 2 items were answered and applied on 31 October (D-015): the D-009 fallback (pre-2007 pairs stay `check`), the Chinese revision markers mapped, the stub wording changed, and the 2005 annual report not tagged. One expected failure remains in the golden test, in the run with the content check (`00005-303146`, M-015), open for Zarif; 740 backend tests pass plus 1 expected failure. Phase 3 plan awaits approval. Update this line at every gate.

**Timeline (HKT):** Fri 30 Oct, Phases 0 to 2. Sat 31 Oct, Phases 3 and 4. Sun 1 Nov, Phases 5 and 6. Mon 2 Nov, Phase 7 and submit. Update, 31 Oct: the reviewer allowed one extra day, so submission can slip to Tue 3 Nov. Phases run strictly in order, each gate approved before the next starts; no phase is skipped or reopened to save time.

Tasks marked [Zarif] need Zarif. Everything else is for Claude Code, after Zarif approves the phase plan. Never start a phase before the previous gate is approved.

## Phase 0: Scaffold and HKEXnews probe (about 2 to 3 h)

Goal: confirm how HKEXnews really behaves before designing around it.

- [x] 0.1 [Zarif] Create the public GitHub repo `hkex-bilingual-downloader`; add `CLAUDE.md` and `docs/`; first commit.
- [x] 0.2 Scaffold: `backend/` uv project (Python 3.12) with FastAPI, ruff, mypy, pytest config and a `live` marker; `frontend/` with Vite, React, TypeScript and Tailwind; root `.gitignore`, MIT `LICENSE`, README stub, `THIRD_PARTY_NOTICES.md`, `TESTING.md` stub. Confirm the Commands section in CLAUDE.md.
- [x] 0.3 `scripts/probe_hkex.py`. It must be polite (at most 1 request per second, identifying User-Agent, responses cached to disk) and must:
  - download the stock lists (active and inactive, EN and TC) and category files (EN and TC) into `backend/tests/fixtures/raw/reference/`;
  - resolve each scenario's code to its internal id;
  - run EN and TC searches per scenario, saving raw responses as `backend/tests/fixtures/raw/<scenario>/{en,tc}_<n>.json` with the request parameters alongside;
  - answer Q1 to Q12 (research notes §8) with evidence, and append dated findings to research notes §9.
- Scenarios (swap in better examples if the probe finds them):
  1. `zai-lab-nddr`: 09688 on 2026-10-28 (known pair 01739 and 01740_c).
  2. `form-8k-en-only`: the issuer of `2026/1023/2026102301070.pdf` (probably 09688, confirm) on 2026-10-23; TC stub at `01071_c.htm`.
  3. `tencent-30d`: 00700, last 30 days (many same-day filings).
  4. `a-plus-h-30d`: an A+H issuer such as 00939 or 01398, last 30 days (Chinese-only regulatory announcements with English stubs).
  5. `results-day`: 00005 on its most recent results day (several documents in the same minute).
  6. `annual-report-season`: 00700, March to May 2026 (separate-language submissions, if any).
  7. `large-range`: 00005, last 3 years (pagination; more than 1,000 rows).
  8. `old-docs`: 00005 during 2005 (LTN naming, no categories).
  9. `listing-docs`: a recent IPO's prospectus period (multi-file and web-page entries).
  10. `delisted`: a delisted code from the inactive list.
  11. `no-results`: a valid code and a range with no documents.
  12. `english-only-issuer`: a debt or structured-product issuer found by the probe.
- [x] 0.4 Hosting reachability: a minimal FastAPI app with `/api/health` and a temporary `/api/probe` that runs one HKEX search and one PDF request and returns status codes and timings; `Dockerfile`; `render.yaml` (Singapore region). [Zarif] Create the Render web service from the repo (free plan is fine for this test) and open `/api/probe` on the deployed URL. Remove the probe route after the gate (done).
- **GATE 0:** answers to Q1 to Q12 with evidence; hosting result; proposed SPEC changes (signal weights, stub fragments, allowlist, pagination). Decide: hosted (continue) or blocked (Plan B).

## Phase 1: HKEX client and domain model (about 3 h)

- [x] 1.1 `domain/`: models (`Document`, `Stock`, `Category`; `Announcement` moves to Phase 2 where its shape is settled by pairing), validation (stock code, date range), HKT helpers. Tests first.
- [x] 1.2 `hkex/client.py`: httpx AsyncClient, headers, timeouts, retries with backoff and jitter, `Retry-After`, concurrency limit, rate limit; session warm-up only if Phase 0 shows it is needed.
- [x] 1.3 `hkex/reference.py`: stock directory (active and delisted, EN and TC names) and category tree with code-to-name maps in both languages; TTL cache; bundled snapshot fallback from the probe fixtures.
- [x] 1.4 `hkex/search.py` and `hkex/parse.py`: per-language search with cumulative pagination, dedupe, loop guard, range splitting and caps (SPEC §3.3); normalisation (SPEC §3.4) including stub and flag detection.
- [x] 1.5 Tests: unit tests, fixture-based tests for every Phase 0 scenario, one `live` smoke test.
- **GATE 1:** test summary; sample normalised output for `zai-lab-nddr` and `form-8k-en-only`.

## Phase 2: Pairing engine and golden set (about 4 h)

- [x] 2.1 Synthetic fixtures for hard cases: same-minute pairs, interleaved sequence numbers, stubs in both directions, revised headlines, identical-hash bilingual file, separately submitted annual report. (`tests/support.py` `make_doc` and `make_pdf`; cases in `tests/unit/test_matcher.py`.)
- [x] 2.2 `pairing/matcher.py` per SPEC §4, with evidence text in `evidence.py`. Tests first. (D-011 layout rule; stub claims; 2005 numbering; replay of all 11 recorded scenarios; Hypothesis invariants; mutation-checked.)
- [x] 2.3 `pairing/content_check.py` per SPEC §4.5. Pure fingerprint, containment and verdict functions plus text extraction in a worker process with a 10 s limit; fetching the PDFs stays in Phase 3. Done before 2.4 because the golden helper prints first-page figures with it.
- [x] 2.4 `scripts/golden_helper.py`: for a scenario, print proposed pairs side by side (titles, times, categories, sequence numbers, first-page figures) and write draft `pairs.yaml` entries for Zarif to confirm or correct. (Pure logic and tests in `backend/tests/golden/` and `tests/unit/test_golden_*.py`; D-012; drafts reproducible with `scripts/golden_drafts.sh`; `coverage` shows what SPEC §10.4 still lacks. 77 drafts from 21 securities including GEM; no separately published annual report found, an accepted gap, D-013.)
- [x] 2.5 [Zarif] Verify and finalise at least 50 golden entries (SPEC §10.4). Open both PDFs per entry (`golden_helper.py show <entry-id>` reprints the evidence and the cached file paths, free); set `verified: true`, or correct `truth` first. Run `coverage` to see the gaps; every required case type needs a verified entry.
- [x] 2.6 Golden test: zero wrong `matched`; print a metrics table. Tune weights and thresholds only with evidence, and record changes in the research notes. (`tests/golden/outcome.py`, `tests/integration/test_golden.py`: one test per entry and run, structural and with content check; the known 2005 failure is a strict xfail until Gate 2; nothing tuned; run with `-s` to see the table.)
- **GATE 2:** metrics table; every `check` and single-language case with its reason; any weight changes.

## Phase 3: Filenames, downloads and ZIP (about 3 h)

- [ ] 3.1 `naming/titlecase.py` and `naming/filenames.py` per SPEC §5. Unit tests with at least 30 real titles from the fixtures; Hypothesis properties. [Zarif] Review 30 sample filenames. (Built 31 Oct: 936 tests pass plus 1 expected failure, D-016; the review of the 30 samples is pending, so the box stays open.)
- [x] 3.2 `downloads/fetcher.py` and `verify.py`: allowlist, streaming, retries, verification, cache.
- [x] 3.3 `downloads/jobs.py` and `zipper.py`: jobs, progress, all-or-nothing ZIP, `sources.csv`, limits.
- [x] 3.4 Fault-injection tests (SPEC §10.5).
- **GATE 3:** test summary; a real pair ZIP downloaded from HKEX and opened on macOS.

## Phase 4: API (about 2 h)

- [x] 4.1 Routes and schemas per SPEC §7; error model per §9; per-IP rate limiting; noindex header.
- [x] 4.2 Fixture mode (`HKEX_MODE=fixtures`) so the frontend and Playwright run without calling HKEXnews.
- [x] 4.3 API tests.
- **GATE 4:** example request and response for each endpoint.

## Phase 5: Frontend (about 5 h)

- [x] 5.1 Design plan per SPEC §8: palette, type, wireframes, principles, and copy for every state. **GATE 5a:** Zarif approves before any UI code.
- [x] 5.2 Build: search, progress, results, announcement entries, evidence, filename editing, downloads with progress, bulk ZIP, empty and error states, help panel and diagnostics.
- [x] 5.3 Accessibility pass (keyboard, focus, screen-reader announcements, contrast) and responsive pass.
- [x] 5.4 Vitest and Playwright journeys (SPEC §10.7).
- **GATE 5b:** screenshots of every state; Playwright results.

## Phase 6: Deploy and harden (about 3 h)

- [ ] 6.1 Production Docker image, Render config, health check. [Zarif] Switch the Render service to the Starter plan so it never sleeps.
- [ ] 6.2 Smoke-test the hosted app with three stock codes.
- [ ] 6.3 `scripts/audit_random.py`: at least 30 random active stocks (mostly ordinary shares, a few other securities) over the last 90 days; writes `docs/audit-report.md`. Fix what it finds; write up the failures and fixes for TESTING.md.
- [ ] 6.4 [Zarif] Windows check on a real PC: downloads in Chrome and Edge, Chinese filenames, ZIP extraction in File Explorer, long names.
- [x] 6.5 CI workflow on Ubuntu, macOS and Windows.
- **GATE 6:** audit report, Windows results, CI green.

## Phase 7: Submission (about 2 h)

- [ ] 7.1 README: what it does; how to open and use it (three steps with a screenshot); requirements (a modern browser, nothing to install); costs (none for the user); how to run locally; known limitations; reused projects and libraries with licences; the Title Case decision; HKEX terms-of-use note; approximate time spent (honest). Optional: a short demo GIF.
- [ ] 7.2 TESTING.md: cases tested and results; how pairing, same-day announcements, missing results and failed downloads were tested; automated test commands; audit results; failures found and how they were fixed.
- [ ] 7.3 AI section (README, summarising `docs/AI_LOG.md`): tools and how they were used, key decisions, one AI mistake caught and corrected, how downloads and pairings were verified.
- [ ] 7.4 Final checks: setup from a fresh clone works; hosted link works in a private window; no secrets; tag `v1.0.0`.
- [ ] 7.5 [Zarif] Send the link to Dawid.

## Plan B: if HKEXnews blocks the hosted server

Package the same app as a local application: PyInstaller builds for macOS and Windows via GitHub Actions, a launcher that opens the browser, and README steps covering the Gatekeeper and SmartScreen prompts. Decide at Gate 0.

## Stretch (only after Phase 7 is done)

Company-name search; expanding multi-file listing documents into their parts; a Simplified versus Traditional script hint for Chinese-section documents.
