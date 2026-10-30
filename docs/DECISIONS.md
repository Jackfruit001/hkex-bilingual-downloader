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
- **Phase 2 refinements (31 October 2026):** (1) Before 25 June 2007 the numbering is assumed to be the 2005 kind unless the folder shows otherwise, because the cut-over year is Open and the cautious reading can only turn a `matched` into a `check`. (2) In that scheme only an exact number counts for S3; a nearby number scores 0, not +2, because other numbers belong to other documents. (3) Both are tested on the 125 + 35 recorded 2005 documents; the golden set decides whether the rule stays (see above).

## D-010 Reused stock codes: default to the active security

- **Context:** HKEX reuses stock codes. In the 30 October reference lists (17,948 codes), 250 have one active security and at least one delisted earlier holder (00700 TENCENT and YAOHAN INT'L; 00013 HUTCHMED and HUTCHISON), 55 have several delisted holders and no active one (03333), and none has two active securities. SPEC v1.1 §3.1 made every reused code return `AMBIGUOUS_STOCK_CODE`, so typing Tencent's code would show a chooser first.
- **Options:** (a) as written: always ask; (b) default to the active security when exactly one is active, offer the delisted holders as a visible switch, and ask only when there is no single active security; (c) default to the active security and hide the others.
- **Decision:** (b). `StockDirectory.resolve` returns the chosen security plus `alternatives`; an explicit `stock_id` always wins; zero or several active candidates still raise `AMBIGUOUS_STOCK_CODE`.
- **Reasons:** an evaluator who types a well-known code expects its current company, and a chooser on 7% of codes (including the most famous ones) is friction for no gain. The switch keeps the other holders one click away, so nothing is hidden (rejects c). The rule is evidence-based: it depends on no code having two active securities, and a test fails if that ever changes.
- **Consequence:** the UI must show which company was searched (name, EN and TC) and the alternatives note on every result, so a user looking for the older company notices at once.
- **Status:** accepted at Gate 1 (31 October 2026); SPEC §3.1, §8 and §9 updated (v1.2).

## D-011 Same-minute batches: pair as `matched` only when the layout is interleaved

- **Context:** research notes Q6 correction (M-007). Documents released in the same minute come in two layouts: interleaved (EN n, TC n+1, EN n+2, TC n+3), 36 groups, and block (EN, EN, TC, TC), 488 groups, all 2015 Rule 22 dealing disclosures with identical titles, minute and categories. In a block, sequence adjacency pairs the wrong files: with SPEC v1.2 weights the second English file scores 11 against its +1 neighbour and 8 against the other Chinese file, which passes the margin of 3, so a likely-wrong pair would be shown as `matched`.
- **Options:** (a) rely on the margin rule; (b) a layout rule: inside a same-minute group a pair can be `matched` only if the group is interleaved, otherwise every document in it is `check`; (c) never match when more than one document per language shares a minute.
- **Decision:** (b). A *group* is the non-stub, unclaimed documents of both languages with the same release minute and date folder. It is *interleaved* when no two documents of the same language have consecutive file numbers (in 2005 `_c` numbering: when every number appears once as English and once as Chinese). In a group that is not interleaved the sequence signal (S3) is scored at its proximity level (+2) and the weak NEWS_ID signal (S4) is dropped for every candidate in the group, so adjacency does not favour one pair, ties break by file order (first English file with first Chinese file), and no pair is `matched`. The rule does not apply in folders numbered the 2005 way (Chinese file = English number plus `_c`): numbers are unique within a language there, so an exact match identifies the pair whatever else was released in the minute. Decisive signals (identical bytes, a conclusive content check) override the rule. The evidence text says why: "N English and N Chinese documents were published at HH:MM; file order cannot show which Chinese file belongs to which English file."
- **Reasons:** (a) fails on the recorded data; (c) would also downgrade the 36 interleaved groups where +1 holds. The tie-break order is a hint, not evidence; whether it is right is **Open** (research notes) and is tested against PDF contents.
- **Status:** accepted 31 October 2026; SPEC §4.3 updated (v1.3).
