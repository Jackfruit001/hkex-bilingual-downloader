# Decisions

One short record per significant choice, with the reason. IDs are cited in the code and the spec,
so they never change; a later decision supersedes an earlier one. The longer reasoning for each is
in the git history.

| ID | Decision | Why |
|---|---|---|
| D-001 | **Hosted web app first** (Render, Singapore), the same Docker image runs locally. | A link needs no install; unsigned local apps hit macOS and Windows warnings; serverless hosts can cap file sizes. HKEXnews answered from Render, so the local-app Plan B was not needed. |
| D-002 | **FastAPI + React** (Python 3.12, httpx, Pydantic; TypeScript, Vite, Tailwind). The backend serves the built frontend. | Fits Zarif's experience; async fetching of both languages; one origin, so no CORS. |
| D-003 | **Match first, filter after.** Both languages are fetched unfiltered, paired, then category and keyword filters apply. | HKEX's keyword filter works per language and would hide counterparts. |
| D-004 | **English filenames in Title Case** when a title is mostly capitals; mixed-case and Chinese titles stay as published. One setting restores HKEX casing. | HKEX titles are often ALL CAPS; the brief's example is Title Case. |
| D-005 | **No AI in the running app.** Pairing uses fixed, explainable signals. | No API keys or paid services; results are testable and auditable. |
| D-006 | **Permissive licences only** for runtime dependencies (no GPL or AGPL; PyMuPDF excluded, pypdf used). | Licence safety. |
| D-007 | **Verified two-step downloads.** The server fetches and checks each file before the browser gets it; ZIPs are all or nothing. | A failed or cut-off download is never shown as a success. |
| D-008 | **Each file uses its own publication date** in its name. | A Chinese annual report published on another day keeps its real date. |
| D-009 | **Pre-2007 pairs.** First allowed a lower score threshold; Gate 2 found a wrong match (M-014), so the fallback applies (see D-015). | Documents before 25 June 2007 have no headline categories and different file numbering. |
| D-010 | **Reused stock codes default to the active company**, with the earlier holders one click away ("Switch"). Ask only when no single active company exists. | 250 codes (7% of ordinary codes, including 00700) are reused; a chooser for Tencent would be friction. |
| D-011 | **Same-minute batches** can be "Matched" only when the file order is interleaved (EN, TC, EN, TC). Block layouts (EN, EN, TC, TC) stay "Check pairing". | In blocks, file order points to the wrong partner; 488 such groups in the recordings. |
| D-012 | **How the golden set is drafted:** the matcher's view is kept apart from the human-confirmed truth; PDFs are never committed (only hashes); live access is one request at a time and stops at the first refusal. | A test set that records what the matcher says would pass whatever the matcher does. |
| D-013 | **GEM paths, unreadable Chinese text, one accepted gap.** File paths under `/gem/` are accepted; a Chinese PDF with under 8% Chinese characters is "unavailable" for the content check; a separately published annual report was never seen in real data, so it is a README limitation. | Without the first, every GEM stock (08xxx) showed no confirmed pair; 21 of 62 Chinese PDFs decode to gibberish. |
| D-014 | **Golden entries were verified by Claude and Zarif by reading both documents** | Zarif had no time for 77 entries so went through 10-12 entries.|
| D-015 | **Gate 2 answers:** every pre-2007 pair with no headline category stays "Check pairing"; Chinese revision markers are mapped; stub wording follows what the HKEXnews notice actually says; the 2005 annual report is not tagged as separate. | The golden set found a wrong "Matched" (M-014); the stub notice only says a version "may or may not" exist (M-017). |
| D-016 | **Filename rules the spec left open:** words joined by `-`, `/`, `&` etc. are capitalised part by part; acronym list extended; a long title is cut at a hyphen to fit 120 characters; only PDFs are named; the server cleans any name a client sends. | Checked on 6,316 recorded PDFs: every name valid on Windows, macOS and Linux. |
| D-017 | **Finishing in one day (1 Nov).** Fewer modules; disk cache (1 hour, 1 GB); in-memory rate limits; every ZIP has a `sources.csv`; the content check is shown as extra evidence and **does not change a status**; no TanStack Query or Radix. | Zarif asked for a web app format instead of my suggested desktop app. The content check stays advisory because of M-015. |
| D-018 | **Render free plan.** The first request after a quiet spell takes about a minute. | No cost for a two-day review; the submission email says so. |
| D-019 | **A richer visual design** (navy header, gradients, status colours with icons and words, light motion that stops under reduced-motion, dark mode). | Zarif found the first version static. No backend change. |
| D-020 | **Filename editing, paging and a readable details panel.** A pencil edits a name (cleaned like the server does); results come 10, 20 or 50 per page; the search details are a table, not JSON. | Zarif's request; reverses the D-017 cut of filename editing. |
