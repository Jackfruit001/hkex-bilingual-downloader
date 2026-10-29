# CLAUDE.md

Instructions for Claude Code on this repository. Read this file at the start of every session, then the documents under "Source of truth".

## Mission

Build a small, polished web application for Regevio's practical assessment. A user enters a Hong Kong stock code and a publication date range, browses that company's HKEXnews announcements, and downloads the matching English (EN) and Traditional Chinese (TC) PDFs with correct filenames.

- Owner: Zarif Al Hossain (candidate). Reviewer: Dawid Kita, Regevio. Evaluator: a nontechnical colleague who will try a random stock code.
- Deadline: Monday 2 November 2026, Hong Kong time. Target: release candidate by Sunday 1 November evening.
- Delivery: a public GitHub repository with README, plus a hosted link (Render, Singapore region). The same app also runs locally with documented commands.
- Assessed on: functional correctness, language matching with visible uncertainty, usability for a nontechnical user, reliability on a random stock code, and engineering judgment (choices, reuse of existing work, testing, AI-assisted development).

The central requirement is language pairing. Each EN document is associated with its TC counterpart and shown as one announcement; anything missing or uncertain is visible. A wrong pairing shown as confirmed is the worst failure this app can have. Optimise for that.

## Source of truth

1. `docs/SPEC.md`: what to build and how it must behave. If code and spec disagree, raise it; don't silently pick one.
2. `docs/PLAN.md`: phases, tasks, exit criteria and gates. Keep checkboxes and the status line current.
3. `docs/research-notes.md`: what we know about HKEXnews, with evidence. Add findings here.
4. `docs/DECISIONS.md`: decision records. Add one for each significant choice.
5. `docs/AI_LOG.md`: how AI tools were used, and every AI mistake that was caught.

## Working rules

1. **Phases and gates.** Work through `docs/PLAN.md` one phase at a time. At each gate, stop and report: what was built, test results with numbers, deviations from the spec, open questions. Wait for Zarif's approval before starting the next phase.
2. **Plan before code.** Start each phase by proposing files, functions and tests. Wait for approval.
3. **Evidence over assumption.** HKEXnews has no public API documentation. Any behaviour the code relies on must be backed by a recorded fixture, a probe result or a cited HKEX document in `docs/research-notes.md`. If unsure, say so and propose a probe. Never invent endpoints, parameters or fields.
4. **Tests first for logic:** validation, parsing, pagination, pairing, filenames, download verification.
5. **Small commits** with conventional messages (`feat:`, `fix:`, `test:`, `docs:`, `chore:`, `refactor:`). Tests pass on every commit. The history is part of the submission and should read as research, then tests, then features.
6. **Log AI mistakes honestly.** When a test, probe or Zarif catches something you got wrong (an assumption, a bug, an API that doesn't exist), add an entry to `docs/AI_LOG.md` immediately. Never invent or embellish entries.
7. **Ask rather than guess** when the brief or spec is ambiguous.
8. **Scope discipline.** Required features first. Optional ones (keyword filter, filename editing, company-name search) come only after the core works end to end. Record anything cut in the README's limitations.
9. **Dependencies.** State the licence before adding one. Runtime dependencies must be permissive (MIT, BSD, Apache-2.0, ISC). Banned: PyMuPDF/fitz (AGPL) and any GPL/AGPL runtime dependency. Test-only MPL-2.0 (Hypothesis) is fine. Pin versions. Credit any reused code in `THIRD_PARTY_NOTICES.md` and the README.
10. **No secrets, credentials, personal data or unrelated files** in the repository. The app needs no API keys.
11. **Be polite to HKEXnews during development too.** Tests use recorded fixtures by default; live calls only when needed.

## Invariants (never break these)

- Never present an uncertain pairing as confirmed. Never substitute an EN document for a missing TC document, or the reverse.
- Never treat an HKEXnews "published in the other section" notice (a stub) as a language version.
- Downloads are the original published bytes. Never modify, regenerate or translate PDF content.
- Report a download as successful only after the file is fully received and verified. Offer a ZIP only when every file in it is verified.
- All dates and times are Hong Kong time (`Asia/Hong_Kong`): queries, filtering, display, filenames and "today" presets. Never use the server's or browser's local timezone for business logic.
- Stock codes are strings; leading zeros are preserved (5 digits).
- The server fetches only from the HKEXnews allowlist in SPEC §6. It never fetches an arbitrary URL supplied by a client.
- Be polite to HKEXnews: bounded concurrency, rate limiting, retries with backoff, caching, an identifying User-Agent, no background crawling.

## Architecture

- **Backend:** Python 3.12, FastAPI, httpx (async), Pydantic v2, pypdf, pathvalidate. Packaging with uv. Lint and types: ruff, mypy (strict on `app/`).
- **Frontend:** React + TypeScript (strict) + Vite + Tailwind CSS, TanStack Query, Radix UI primitives for accessible widgets. Built to static files and served by FastAPI, so one origin and no CORS.
- **Deployment:** one Docker image (multi-stage: Node build, then Python runtime) on Render, Singapore region. The same image runs locally.
- **Tests:** pytest, pytest-asyncio, respx, Hypothesis; Vitest with Testing Library; Playwright end to end.

Target layout:

```
backend/
  pyproject.toml
  app/
    main.py            FastAPI app, static frontend, health check
    config.py          settings, tunable thresholds, Title Case mode
    domain/            models, validation, HKT time helpers
    hkex/              HTTP client, reference data (stocks, categories), search, parsing
    pairing/           matcher, evidence text, content check
    naming/            Title Case, filename builder
    downloads/         fetcher, verification, jobs, ZIP builder
    api/               routes, schemas, error model
  tests/
    unit/  integration/
    fixtures/raw/      recorded HKEXnews responses from the probe
    golden/pairs.yaml  hand-verified EN/TC pairs
frontend/
  src/  e2e/
scripts/
  probe_hkex.py  golden_helper.py  audit_random.py
docs/
Dockerfile  render.yaml  README.md  TESTING.md  LICENSE  THIRD_PARTY_NOTICES.md
```

Each module has one clear responsibility. Business rules (pairing, naming, validation) are pure functions without I/O, so they can be tested exhaustively.

## Commands

Confirm these during Phase 0 and keep them current.

```
# backend
cd backend && uv sync
uv run pytest                  # offline tests (default)
uv run pytest -m live          # opt-in live HKEXnews smoke tests
uv run ruff check . && uv run mypy app
uv run uvicorn app.main:app --reload

# frontend
cd frontend && npm install && npm run dev
npm test && npx playwright test
```

## Style

- Python: typed; Pydantic models or dataclasses rather than loose dicts; no bare `except`; errors carry a code and a user-facing message (SPEC §9).
- TypeScript: no `any`; components named after what users see.
- User-facing copy: sentence case, plain words, active voice; errors say what happened and what to do next (SPEC §8).
- Docs: concise. Avoid excessive em-dashes; use commas, semicolons or full stops.
