# Decisions

Each record: context, options, decision, reasons, status. Add new records at the end; never rewrite history, supersede instead.

## D-001 Delivery: hosted web app first, local run as backup

- **Context:** the evaluator is not technical and will test a random stock code. The brief allows local or hosted delivery.
- **Options:** packaged local app (.exe / .app); browser extension; hosted web app; native desktop app.
- **Decision:** a hosted web app on Render (Singapore region, Starter plan so it never sleeps). The same Docker image runs locally, documented in the README.
- **Reasons:** a link needs no installation. Unsigned local apps hit macOS Gatekeeper and Windows SmartScreen prompts and can be blocked outright on managed work laptops. An extension needs developer mode, and store review would not finish in time. Serverless platforms can cap response sizes, which breaks large annual-report PDFs and ZIPs, so a container host fits better.
- **Risks:** HKEXnews may throttle or block cloud IPs (tested at Gate 0; Plan B is the packaged local app); uptime during evaluation; about USD 7 a month, paid by Zarif, nothing for the user.
- **Status:** accepted, pending the Gate 0 reachability test.

## D-002 Stack: FastAPI and React

- **Decision:** Python 3.12, FastAPI, httpx, Pydantic; React, TypeScript, Vite, Tailwind.
- **Reasons:** matches Zarif's experience (Flask, React). Async httpx runs English and Chinese searches in parallel and streams downloads. Pydantic gives validated schemas. Serving the frontend from the backend keeps one origin, so no CORS.
- **Status:** accepted.

## D-003 Match first, filter after

- **Decision:** fetch both languages unfiltered for the range, pair them, then apply category and keyword filters.
- **Reasons:** HKEX's keyword filter works per language, so an English keyword would hide the Chinese counterparts. Pairing should not depend on filters, and collision suffixes stay deterministic.
- **Status:** accepted.

## D-004 English filenames in Title Case

- **Context:** many HKEX English titles are published in capitals; the brief's example uses Title Case (`Appointment-of-Director`).
- **Decision:** Title Case by default, preserving acronyms and form numbers; mixed-case titles kept as published; a single config switch (`TITLE_CASE_MODE`) restores HKEX casing.
- **Status:** accepted; Zarif is confirming the preference with Dawid. Explain in the README.

## D-005 No AI in the running app

- **Decision:** pairing uses deterministic, explainable signals; no LLM calls at runtime.
- **Reasons:** the brief rules out assuming API keys or paid subscriptions. Deterministic evidence is free, fast, auditable and testable. AI is used during development and verification instead.
- **Status:** accepted.

## D-006 Permissive runtime dependencies only

- **Decision:** no GPL or AGPL runtime dependencies. PyMuPDF is excluded (AGPL); pypdf handles PDF checks; pathvalidate handles filename validation.
- **Status:** accepted.

## D-007 Verified two-phase downloads

- **Decision:** the server fetches and verifies each file before the browser receives it; ZIPs are all or nothing.
- **Reasons:** a failed or truncated download can never be presented as a success, and the user sees real progress.
- **Status:** accepted.

## D-008 Each file uses its own publication date

- **Decision:** each filename uses that document's own HKT publication date, so a separately published Chinese annual report keeps its real date.
- **Status:** accepted.

## D-009 Pre-2007 pairing: lower threshold, require two structural signals

- **Context:** documents before 25 June 2007 have no headline categories, so signal S2 (up to +3) is unavailable. With the SPEC §4.3 threshold of 9 they could never be `matched`. The probe (research notes §9, Q6) found the 2005 Chinese file shares the English file number with `_c` added (16 of 16 same-minute pairs), whereas 2014 onwards is +1.
- **Options:** (a) leave the threshold at 9, so every pre-2007 pair is `check`; (b) lower the threshold when no category exists, with extra conditions; (c) always run the content check for pre-2007 pairs.
- **Decision:** (b). When neither document has categories, `matched` needs a score of at least 7 (config `MATCH_MIN_SCORE_NO_CATEGORY`) and both S1 (same release minute) and S3 (adjacent or identical file number for that era) must hold, plus the existing mutual-best, margin and no-conflict rules. Anything else stays `check`. The content check (S7) remains available for `check` entries.
- **Reasons:** 7 is the 9 threshold minus the 3 points the category signal would have contributed. Requiring two independent structural signals keeps the rule explainable.
- **Validation and fallback:** the golden set must include pre-2007 pairs (SPEC §10.4). If it shows any wrong `matched` among them, revert to (a), keep every pre-2007 pair as `check`, and say so in the README limitations.
- **Status:** accepted provisionally; SPEC §4.3 and §4.4 to be updated at Gate 0 approval.
