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
- **Gate 2 (31 October 2026):** the golden set found a wrong `matched` among pre-2007 pairs (M-014), so the fallback above was applied, narrowed to pairs with no category text at all (D-015). The lower threshold stays only for a category text that no code resolves to.
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

## D-012 How the golden set is drafted

- **Context:** the golden set (SPEC §10.4) is the test of the matcher, and the helper that drafts it uses the matcher. A set that merely records what the matcher says would pass whatever the matcher does.
- **Decision:** (1) A draft entry's `truth` is a claim for Zarif to confirm or correct with both PDFs open; the matcher's view is kept apart as `proposal`, which the golden test ignores, and entries start with `verified: false`. The helper shows evidence against a pairing (rivals, figure overlap, file hashes) as well as for it, and warns when too few figures were compared. (2) Rows are chosen by a stratified sample (every case type and status once, rarest first, then busy days) or by explicit row numbers, so easy pairs cannot crowd out the hard ones. (3) Search responses used by a written entry are kept under `tests/fixtures/golden/<scenario>/calls/` and replayed through the real search code by a client with a budget of zero live requests; they stay out of `fixtures/raw/`, which the replay tests enumerate. (4) PDFs are never committed: only their SHA-256, size and the content-check figure fingerprint are kept in `tests/golden/fingerprints.json`, which lets the golden test exercise the identical-bytes and content signals offline. (5) Live access is sequential, at least a second apart, with no retries: the first 403, 429, challenge page, redirect, truncated or non-PDF body ends the run, and a per-run budget caps live requests. (6) `pairs.yaml` is append-only: entries already in it are never rewritten, so Zarif's edits and comments survive, and an unknown field (for example a misspelt `verified`) is an error. (7) A Chinese PDF whose text is under 8% Chinese characters is shown as unusable for comparison, with the reason; the product's content check is not changed here (see research notes, Phase 2.4 findings).
- **Reasons:** (1) and (2) keep the set independent of the code under test. (3) and (4) keep the repository small and free of other people's documents while keeping the test deterministic. (5) follows the politeness invariants. (6) protects the human work, which is the scarce part. (7) is a display rule for the helper only; changing the product is a Gate 2 decision.
- **Status:** plan approved by Zarif 31 October 2026; live calls approved the same day (about 30 searches and up to 200 PDFs). Used: 30 searches (60 responses) and 125 PDFs.

## D-013 GEM file paths, unreadable Chinese text, and an accepted gap

- **Context:** the live runs of Phase 2.4 found three things (research notes, Phase 2.4 findings; M-011, M-012). (1) The parser only accepted `/sehk/` file paths, so every GEM issuer (08xxx) lost its file numbers and was shown only as `check`. (2) 21 of 62 Chinese PDFs have undecodable text that still passes the 200-character test. (3) No separately published annual report exists in the data found.
- **Decision:** Zarif delegated all three on 31 October 2026. (1) `parse_file_path` accepts `/sehk/` and `/gem/`; GEM drafts are in the golden set. (2) `content_check.readable` marks a Chinese document with under 8% Chinese characters as unavailable (`content_min_chinese_share`, in the gap between the 2.8% and 14.5% measured); SPEC §4.5 updated; the helper uses the same function. Not extended to edge cases such as partly decodable files (one with 62% Chinese still shows odd lines; accepted). (3) The separate-annual-report case is an accepted gap: README limitation, SPEC §10.4 note, and `coverage` lists it as accepted.
- **Reasons:** (1) is safe and evidence-based: 34 GEM announcements went from 0 to 32 `matched`, the other 2 stay `check` because one is revised. (2) stops the product from presenting a figure comparison made of gibberish; a clear gap in the measurements means the exact threshold matters little. (3) hunting further costs live calls for a case real data has not shown.
- **Consequence:** the golden set gains GEM entries. If a separate annual report is ever seen, tag it and the gap closes by itself.
- **Status:** accepted 31 October 2026; SPEC v1.4.

## D-014 How the golden entries were verified (a deviation from SPEC §10.4)

- **Context:** SPEC §10.4 says Zarif opens both PDFs for at least 50 entries. Zarif did not have the time to do that for 77 drafts.
- **Decision (Zarif, 31 October 2026):** Claude reads the documents and Zarif spot-checks. First an offline triage ranked the 77 drafts by evidence the matcher did not use; it found only 19 strong, so it did not save work. Claude then read all 77, as follows: 20 pairs, the English text and the Chinese first page rendered as an image (pypdf cannot decode those files); 27 pairs, the first-page text of both documents (10 with weak figure overlap, 17 that the triage had called strong); 4 block-layout pairs, the table headings of all eight documents; 4 revised pairs, the titles and revision markers; 7 entries, titles only (web pages, multi-file entries and annual reports over the size limit); 10 single-language entries, the HKEXnews notice context in the listing, without reading the notices themselves; 4 entries from 2005, the documents themselves; and 1 entry (a `.doc`) that could not be checked. Zarif opens a short list (the 2005 correction below, plus about 10 across the entry kinds), then confirms. Only then are entries marked `verified: true`, with Claude's finding in `notes`.
- **Result of the reading:** 72 entries agree with the matcher, 2 are corrected (one wrong `matched`, one pair the matcher left as two single-language entries), 2 are duplicates of those, 1 cannot be verified.
- **Limits, stated plainly:** Claude's reading can be wrong too, and it is not independent of the AI that wrote the matcher, so the "zero wrong `matched`" claim rests on AI reading that Zarif confirmed, not on a person opening every pair. The first triage rule (figure overlap) was itself fooled once, by the two 2005 scrip forms that share their figures, which is why all 77 were read. The README says how the golden set was verified.
- **Applied (31 October 2026):** Zarif confirmed the result after receiving the short list. The number of PDFs he opened was not recorded, so no count is claimed. `pairs.yaml` now has 75 entries: 74 `verified: true` (72 that agree, 2 corrected, each with Claude's finding in `notes`), the 2 duplicates deleted, and the `.doc` entry left unverified. `coverage` reports 74 verified entries from 21 issuers and no gaps except the accepted one (D-013). Not in the set: English file 97 with Chinese file 96 (the Entitlement Advice Form pair, 2005), which the reading found but nobody drafted.
- **Status:** accepted route; done.

## D-015 Gate 2 answers: pre-2007 fallback, Chinese revision markers, stub wording, 2005 annual report

- **Context:** four Gate 2 items were open after the golden test (research notes, Phase 2.5 and 2.6 findings; M-014).
- **Decision (Zarif, 31 October 2026):** (1) apply the D-009 fallback: a pair with no headline category on either side stays `check` unless identical bytes or a conclusive content check confirm it; (2) map the Chinese revision markers `(修改後標題)` and `(經修訂)` as revised flags; (3) reword the stub evidence to what the HKEXnews notice supports; (4) do not tag the 2005 HSBC annual report `separate_annual_report`: that rule is for submissions on different days, and these two were 34 minutes apart, so it stays the accepted gap of D-013.
- **Applied, (1):** `_can_match` returns false when neither document has a category text or code; the check pair carries the note "Neither version has a headline category, ..." (`NO_CATEGORY_NOTE`). It is keyed on category *text*, not on resolved codes: a first version keyed on codes also held back two 2014 Hutchison pairs whose category ("Share Option Scheme") is retired and resolves to no code (M-016), and they keep the lower threshold of D-009. Golden test, structural run: confirmed and right 49 (was 50), WRONG 0 (was 1), for checking 13 (was 12) plus 1 wrong partner offered for checking. The `old-docs` replay goes from 22 matched and 11 check to 0 and 33.
- **Applied, (2):** `_flags` in `hkex/parse.py` maps the category prefix starting `修改後標題` to `headlines_revised` and a title starting `(經修訂)` to `revised`, at the start only (經修訂 inside a title, as in the 02372 circular, is not a flag; the cancelled marker stays `cancelled`). The four recorded pairs are confirmed, two per marker; the `delisted` replay moves one pair from check to matched. A mutant that accepts the marker anywhere in the prefix survives, because no recorded prefix has that shape.
- **Applied, (3):** the stub reason now gives the search result and then what the notice says: "No Chinese version found between [dates]. HKEXnews' Chinese section shows a notice instead, saying a Chinese version may or may not be published there." (English version: "an English version"). SPEC §4.1 and §4.6 updated. The status label "English only" and the reason code are unchanged; the label is a separate question.
- **Applied, (4):** nothing changed in the code or the golden set. The 2005 HSBC annual reports stay `check` (no categories), and the missing real example of a separate submission stays the accepted gap of D-013 and a README limitation.
- **Open:** in the run with the content check, `00005-303146` is still confirmed wrongly (M-015). It is now a `check`, so "Check contents" runs, but the matcher lists no rival (the right partner, Chinese file 95, scores 3 against a minimum of 4), so the content check compares one candidate and calls 92% conclusive. The test keeps a strict expected failure for that run only. Options are for Zarif.
