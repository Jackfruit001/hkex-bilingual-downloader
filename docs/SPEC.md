# Specification

Version 1.5, 31 October 2026 (Gate 2 answers: D-015, pre-2007 fallback; Gate 0 changes: D-009, research notes §9; Gate 1 change: D-010, code reuse; Phase 2: D-011, same-minute batches; D-013, GEM paths and unreadable Chinese text). Owner: Zarif. Changes need Zarif's approval and an entry in `docs/DECISIONS.md`.

## 1. Users and the job to be done

The primary user is not a developer. Picture a compliance or operations analyst who needs the English and Traditional Chinese versions of a listed company's announcements, correctly paired and named, without comparing two result lists by hand.

Success looks like this: they open a link, enter a stock code, choose dates, and within a minute download the right EN and TC PDFs with filenames they never need to change. When the app is unsure, they can see that it is unsure and why.

## 2. Requirements traceability

Every requirement maps to at least one test. Fill the Tests column as tests are written; `TESTING.md` is built from this table.

| ID | Requirement (from the brief) | Notes | Tests |
|---|---|---|---|
| R1 | Enter a HK stock code, preserving leading zeros | Accept `700`, `0700`, `00700`, `700.HK`; normalise to `00700` | `tests/unit/test_validation.py` |
| R2 | Select a publication date range; inclusive; HKT | Both ends inclusive | `tests/unit/test_validation.py`, `tests/unit/test_timeutil.py`, `tests/unit/test_search.py` (HKT filtering) |
| R3 | Filter by headline category, with "All categories" | Categories exist only for documents from 25 Jun 2007 | |
| R4 | Search and browse results, including beyond the first page | All HKEX pages fetched server-side | `tests/unit/test_search.py`, `tests/integration/test_replay.py` (search layer only) |
| R5 | Title keyword filter (optional) | English or Chinese keyword | |
| R6 | Each EN document associated with its TC version, shown as one entry with per-language downloads | Central requirement | |
| R7 | Show code and company name, date and time, EN and TC titles, category, availability per language, links to source documents | | |
| R8 | Missing or uncertain matches communicated; never shown as confirmed; no substitution | | |
| R9 | Download EN PDF individually | | |
| R10 | Download TC PDF individually | | |
| R11 | Download both in one action (ZIP) | | |
| R12 | Files are the original published PDFs | Byte for byte | |
| R13 | Multiple attachments or non-PDF entries are made clear | | |
| R14 | Default filenames `LANG_YYYY-MM-DD-CODE-TITLE.pdf` | Title Case for EN (D-004) | |
| R15 | Windows-invalid characters, long titles and collisions handled | | |
| R16 | Edit proposed filenames (optional); defaults work with no edits | | |
| R17 | Invalid stock code or date range | | `tests/unit/test_validation.py` (domain layer; UI in Phase 5) |
| R18 | Search with no results | | |
| R19 | Several announcements from one company on one day | | |
| R20 | Missing or uncertain language matches | | |
| R21 | Results spanning multiple pages | | `tests/unit/test_search.py`, `tests/integration/test_replay.py::test_large_range_takes_two_calls_and_returns_every_row` |
| R22 | Failed or interrupted downloads | | |
| R23 | Repeated downloads and filename collisions | | |
| R24 | Progress, success and error messages; failures never shown as success | | |
| R25 | Runnable app plus source; hosted link plus reproducible setup | | |
| R26 | README: how to use, requirements, costs, limitations, reused projects, time spent | | |
| R27 | Testing evidence incl. pairing, same-day, missing results, failed downloads; how to run tests | | |
| R28 | AI usage: tools, key decisions, one AI mistake caught, how pairings and downloads were verified | | |

## 3. Search

### 3.1 Inputs and validation

- **Stock code:** trim; drop a trailing `.HK` (any case) and spaces; must be 1 to 5 digits; left-pad to 5. Resolve against the stock directory (active and delisted lists). Errors: `INVALID_STOCK_CODE`, `UNKNOWN_STOCK_CODE`. If a code maps to more than one security over time (code reuse), the one active security is used by default and the delisted holders of the code are returned as alternatives so the UI can offer a visible switch (D-010). Only a code with no single active security (for example three delisted companies) returns the choices and lets the user pick (`AMBIGUOUS_STOCK_CODE`). An explicit `stock_id` always wins.
- **Dates:** ISO `YYYY-MM-DD`. Start ≤ end; end ≤ today in HKT; start ≥ 1999-04-01 (earliest HKEXnews records). Error: `INVALID_DATE_RANGE` with the specific reason.
- **Category:** optional tier codes from the HKEX category tree. Default: all categories.
- **Keyword:** optional, 1 to 100 characters.

### 3.2 Query strategy: match first, filter after

1. Query the EN and TC sections concurrently for the resolved stock, with no category or keyword filter, over the requested range plus one day of buffer on each side.
2. Normalise all rows (§3.4), then keep only documents whose release time falls inside the requested range in HKT. Inclusivity then doesn't depend on how HKEX interprets `toDate`.
3. Pair (§4).
4. Apply category and keyword filters to the paired announcements. A keyword matches if it appears, case-insensitively, in the EN or the TC title.

Why: HKEX's keyword filter runs per language, so an English keyword would drop every Chinese counterpart; pairing results must not change with the user's filters; collision suffixes stay deterministic. Fallback: if an unfiltered range exceeds the row cap (§3.3), apply the same category codes to both languages server-side and tell the user.

### 3.3 Pagination and limits

HKEX's `rowRange` is reported to be cumulative (it returns rows 1 to N). Strategy, to be confirmed in Phase 0:

- First call with `rowRange=100` to learn the total count.
- If more rows exist, one call with `rowRange = min(total, 5000)`.
- If the total exceeds 5,000, split the date range in halves recursively and merge.
- Remove repeated rows by `NEWS_ID` (the file path is not an identity: shared `/dod/` pages). Guard against loops: if a call returns fewer rows than `recordCnt` reports, stop and add a warning instead of asking again.
- Hard limit of 20,000 rows per language per search; beyond it return `TOO_MANY_RESULTS` asking the user to narrow the range or choose a category.

### 3.4 Normalised document

| Field | Source and rule |
|---|---|
| `path` | `FILE_LINK`; used to fetch the file, not a unique key (shared `/dod/` pages) |
| `lang` | `en` or `tc` (the section it came from) |
| `release_at` | `DATE_TIME` (`DD/MM/YYYY HH:MM`) as HKT |
| `stock_codes`, `stock_names` | split on `<br/>`; codes zero-padded |
| `title` | HTML-unescaped, whitespace collapsed, NFC |
| `category_text` | `LONG_TEXT`, unescaped |
| `category_codes` | tier codes resolved from `category_text` via the EN or TC category maps. Parse `Parent - [Child]`; split multiple children on ` / `; strip a leading `(Cancelled and Reissued)` or similar prefix into `flags`; resolve by parent and child together because 93 child names map to several codes; empty if unresolved or pre-2007 |
| `file_type`, `size_label` | `FILE_TYPE`, `FILE_INFO` |
| `folder_date`, `seq` | parsed from the path (`/YYYY/MMDD/` under `/sehk/` or, for GEM issuers, `/gem/`, and the numeric stem; supports the older `LTN` prefix and sub-folders) |
| `is_stub` | title matches a stub fragment (research notes §5) |
| `flags`, `category_prefix` | `cancelled`, `headlines_revised`, `revised` from the bracketed category prefix (English `Headline(s) Revised`, Chinese `修改後標題`) or a title prefix (English `(Revised)`, Chinese `(經修訂)`); the raw prefix is always kept so an unmapped marker stays visible to the matcher |
| `news_id` | `NEWS_ID`; unique within a language, the key for removing repeated rows |
| `source_url` | absolute `https://www1.hkexnews.hk/...` |

Parsing must tolerate nulls and numbers in string fields.

### 3.5 Output

Announcements sorted newest first (toggle for oldest first), a summary (counts by status), warnings, and diagnostics (pages and rows fetched per language, duration, cache hits). All results are loaded; the UI paginates or virtualises long lists.

## 4. Pairing engine

### 4.1 Statuses

| Status | UI label | Meaning |
|---|---|---|
| `matched` | Matched | Confirmed by the rule in §4.3 |
| `check` | Check pairing | A likely counterpart exists, but the evidence isn't conclusive; rivals are shown |
| `en_only` | English only | No TC version; reason given |
| `tc_only` | Chinese only | No EN version; reason given |

Reasons for single-language entries: `stub_in_other_section` ("No Chinese version found between [dates]. HKEXnews' Chinese section shows a notice instead, saying a Chinese version may or may not be published there.") and `not_found` ("No Chinese version found between [dates]."). The notice never says the issuer published in one language only, so the evidence must not say it either (D-015).

Every announcement also has a `format`: `pdf`, `web_page`, `multi_file` or `other` (R13).

### 4.2 Signals

Initial weights; tune on the golden set and keep them in `config.py`.

| ID | Signal | Weight |
|---|---|---|
| S1 | Same release minute | +3; within 5 minutes +1 |
| S2 | Headline category codes | identical +3; overlapping +1; disjoint −4 |
| S3 | File sequence in the same date folder, numbering-aware | TC = EN + 1: +4; within ±3: +2. In folders numbered the 2005 way (the Chinese file has the English number plus `_c`, detected from the folder, and assumed before 25 June 2007): only the identical number counts, +4, and nearby numbers score 0. Evidence text says which relationship applied |
| S4 | `NEWS_ID` of the TC document is the EN one plus 1 | +1 (weak corroboration; `NEWS_ID` is not shared across languages, and the offset differs in about 1% of pairs) |
| S5 | Identical SHA-256 of the files | decisive (bilingual document submitted twice) |
| S6 | Numbers in titles (years, form numbers, amounts) | agree +1; conflict −2 |
| S7 | Content check (§4.5) | decisive when conclusive |

### 4.3 Algorithm

1. Remove stubs (§4.4) from both sides first, because a stub takes the number after the document it stands in for. Candidates for each EN document: TC documents in the same date folder within ±5 sequence numbers, or with the same release minute. Same minute and same category do not identify a pair on their own: documents interleave (EN 684 with TC 685, EN 694 with TC 695), so S3 is what separates them. For separate-submission categories (§4.4), also documents of the same category within ±14 days.
2. Score each candidate pair.
3. Split the candidate graph into connected components. Within each, find the best one-to-one assignment (exhaustive when a side has ≤ 8 documents, which covers real cases; greedy with ambiguity flags otherwise).
4. Classify an assigned pair as `matched` only if all of these hold:
   - mutual best: each is the other's top-scoring candidate;
   - score ≥ 9, or a decisive signal. A pair with no headline category on either side (no category text and no codes, as before 25 June 2007) is never `matched` on time and file numbers alone: it stays `check`, with a note saying why, unless a decisive signal confirms it (D-009 fallback, D-015). A category text that no code resolves to (a retired category) keeps the lower rule: score ≥ 7 (`MATCH_MIN_SCORE_NO_CATEGORY`) and both S1 (same release minute) and S3;
   - margin: the runner-up for either side scores at least 3 lower;
   - no hard conflict (disjoint categories, conflicting title numbers, differing cancelled or revised flags).
   - layout (D-011): if the pair sits in a same-minute group (same release minute and date folder, stubs and stub-claimed documents removed) that is not interleaved, it is never `matched` unless a decisive signal confirms it. A group is interleaved when no two documents of the same language have consecutive file numbers (2005 `_c` numbering: when every number occurs once per language). In a non-interleaved group S3 is scored +2 for every candidate, ties break by file order, and every pair is `check` with evidence that file order cannot identify the pair.
5. Otherwise, if the best candidate scores ≥ 4: status `check`, with up to two rivals listed.
6. Otherwise: single-language.

### 4.4 Special cases

- **Stubs.** A stub in the other section (a small `.htm` of about 1 KB, in either direction; exact titles in research notes §5) stands in for the document published at the same minute whose file number is just before it: +1 in 788 of 790 recorded cases, up to +3 when another issuer's files fall between (file numbers are one counter for the whole market). A stub claims its document at exactly +1, or the one unclaimed same-minute document within 5 numbers if exactly one qualifies and it has no real counterpart; shared pages without file numbers (`dod/en.html`) are claimed by NEWS_ID minus 1. A stub that claims nothing is ignored and counted in the diagnostics. The claimed document sets `en_only` or `tc_only` with reason `stub_in_other_section`. Stubs are never shown as their own announcement or offered as a language version; the notice is linked as a source.
- **Separate submissions.** HKEX allows annual reports and listing documents to be submitted in each language separately. For those categories, if no counterpart is found in range, search ±14 days. A counterpart found this way is `check` ("Chinese version published separately on 28 Apr 2026") unless a decisive signal confirms it.
- **Bilingual documents.** Identical bytes in both sections means one bilingual file published twice: `matched`, labelled "Bilingual document".
- **Headline revisions.** Exact duplicates (same path) collapse into one. Cancelled and revised entries pair within their own flag group and are flagged in the UI.
- **Multi-code documents** (dual counters, joint announcements): shown under the searched code; other codes listed.
- **Pre-2007 documents** have no categories; S2 contributes 0, and the 2005 file numbering is irregular (research notes, Phase 2.5 findings). Every pre-2007 pair is therefore `check` unless identical bytes (S5) or a conclusive content check (S7) confirm it (D-009 fallback, D-015), with the evidence line "Neither version has a headline category, so time and file numbers can't confirm the pair on their own." The README limitation says so.

### 4.5 Content check

Runs on demand for `check` entries (a "Check contents" button) and automatically in the audit script.

1. Download and verify both PDFs through the normal fetcher (cached).
2. Extract text from the first three pages with pypdf, 10 s limit per file. Under 200 characters means "Content check unavailable (scanned document)". A Chinese document whose text is under 8% Chinese characters (`content_min_chinese_share`) is also unavailable ("text can't be decoded"): many Chinese PDFs embed a font pypdf cannot decode, and their extracted text is gibberish (D-013).
3. Fingerprint: numeric tokens matching `\d[\d,]*(?:\.\d+)?%?`, commas removed, single digits dropped. English dates like "28 October 2026" also contribute `28`, `10`, `2026`, so they compare with "2026年10月28日".
4. Score: multiset containment, |EN ∩ TC| / min(|EN|, |TC|).
5. Conclusive if the best score ≥ 0.6, best minus second ≥ 0.2, and the EN fingerprint has ≥ 5 tokens. Then upgrade `check` to `matched` with evidence such as "Content check: 84% of figures match". Never downgrade a decisive match. Tune thresholds on the golden set and record them in the research notes.

### 4.6 Evidence text

Each announcement carries readable evidence, for example:

- "Published together at 22:52 HKT, same headline category, consecutive HKEX file numbers (01739 and 01740)."
- "Two Chinese documents were published at 16:30 with the same category. Best guess shown; compare before relying on it."
- "No Chinese version found between 28 Oct 2026 and 28 Oct 2026. HKEXnews' Chinese section shows a notice instead, saying a Chinese version may or may not be published there."

## 5. Filenames

Format: `{LANG}_{YYYY-MM-DD}-{CODE}-{TITLE}.pdf`

- `LANG`: `EN` or `TC`.
- Date: that document's own HKT publication date (a separately published TC annual report keeps its real date).
- `CODE`: the searched code, 5 digits.
- `TITLE`: from that language's title.

**English title pipeline**

1. HTML-unescape, NFC, collapse whitespace.
2. Title Case (`TITLE_CASE_MODE = "title"` by default; `"as_published"` keeps HKEX casing). Apply only when ≥ 70% of ASCII letters are upper case; mixed-case titles stay as published.
   - Keep upper case: an acronym list in config (AGM, EGM, SGM, ESG, CEO, CFO, INED, PRC, HK, HKD, RMB, USD, US, UK, EU, SEC, SFC, CSRC, HKEX, SEHK, GEM, IPO, ADS, ADR, ETF, REIT, CBBC, RSU, ESOP, PLC, LLC, NV, SA, AG, plus more found in fixtures); Roman numerals I to XXX; tokens containing digits (8-K, 10-Q, 20-F, Q3, H1, FY2025, 2026); single-letter share classes before "share(s)" (H Shares, A Shares).
   - Lower case: a, an, the, and, but, or, nor, as, at, by, for, from, in, into, of, off, on, onto, per, to, up, upon, via, vs, with; except as the first word, after an opening bracket, or after a " - " separator.
   - Everything else: first letter upper, rest lower, per hyphenated part (Non-Exempt) and keeping apostrophes (Shareholders').
3. Slug: replace `< > : " / \ | ? *` and control characters with a space; whitespace runs become `-`; collapse repeated `-`; strip `-`, `.`, `_` and spaces at both ends. Other punctuation (commas, brackets, apostrophes, ampersands) stays.

**Chinese title pipeline:** steps 1 and 3 only; also treat the ideographic space U+3000 as whitespace. Full-width punctuation stays (valid on Windows).

**Limits:** the whole filename is ≤ 180 UTF-8 bytes and ≤ 120 characters (fits Windows, macOS and typical download paths). Truncate the title at the last `-` boundary that fits; never cut inside a multi-byte character. An empty title becomes `Untitled`. Validate the final name with pathvalidate for the universal platform.

**Collisions:** compute names over the full unfiltered day for that stock. When two different files would get the same name, add `-(2)`, `-(3)` in publication order (release time, then sequence). The same document always gets the same name, whatever the filters.

**ZIP names:** pair `EN-TC_{date}-{code}-{EN title}.zip` (TC title if EN is missing); bulk `HKEX_{code}_{start}_to_{end}.zip`. Bulk ZIPs include `sources.csv`: announcement, language, filename, status, source URL, SHA-256, retrieved at (HKT). Missing versions appear as rows marked "not published".

**User edits:** the UI may edit a proposed name; the server re-sanitises it and says so if anything changed. Edits keep `.pdf`.

**HTTP header:** `Content-Disposition: attachment; filename="<ASCII fallback>"; filename*=UTF-8''<percent-encoded>`.

**Examples (each is a test):**

- `EN_2026-10-15-00700-Appointment-of-Director.pdf`
- `TC_2026-10-15-00700-委任董事.pdf`
- `OVERSEAS REGULATORY ANNOUNCEMENT - FORM 8-K` → `Overseas-Regulatory-Announcement-Form-8-K`

## 6. Downloads

- **Allowlist:** host `www1.hkexnews.hk` or `www.hkexnews.hk`; https; path matching `^/listedco/listconews/[A-Za-z]+/\d{4}/\d{4}/(?:[A-Za-z0-9_]+/)?[A-Za-z0-9_]+\.(?:pdf|htm|html)$`, case-insensitive extension. Adjust only with evidence from Phase 0. Clients send document paths; the server validates them. Redirects off the allowlist are refused.
- **Two-phase flow:** the client creates a job; the server fetches and verifies each file and reports progress; only then does the client request the finished file.
- **Fetch:** stream to a temporary file; connect timeout 10 s, read timeout 30 s; up to 3 retries with exponential backoff and jitter on network errors, 429 and 5xx; respect `Retry-After`.
- **Verify, in order:** HTTP 200; body starts with `%PDF-`; bytes received equal `Content-Length` when present; not an HTML page; pypdf opens it (non-strict) with ≥ 1 page. Record SHA-256 and page count. Any failure is `VERIFY_FAILED` with the reason; nothing is offered for download.
- **Cache** verified files by path for 1 hour (disk, LRU, 1 GB cap). Repeated downloads reuse the cache and get the same filename.
- **Jobs:** id, items (path, filename, state `queued | fetching | verifying | done | failed`, bytes, error), overall state. Kept in memory, expire after 1 hour. The client polls every 500 ms.
- **ZIP:** built from verified files only; UTF-8 entry names; stored without compression (PDFs are already compressed). If any item fails, the job fails with per-item reasons and offers "Retry failed files"; no partial ZIP is offered as complete.
- **Limits:** 50 announcements or 500 MB per bulk ZIP; at most 3 concurrent HKEX downloads per job and 6 globally.
- **Hosted hygiene:** per-IP rate limits on search and download endpoints; `X-Robots-Tag: noindex`; request bodies are not logged.

## 7. API sketch (refine in Phase 4)

- `GET /api/health`
- `GET /api/stocks?q=` → matching securities (code, internal id, EN and TC names, active or delisted). Code prefixes; name search optional.
- `GET /api/categories` → category tree with codes and EN and TC names.
- `POST /api/search` `{stock_code, stock_id?, start, end, category?, keyword?}` → `{company, announcements[], summary, warnings[], diagnostics}`
- `POST /api/content-check` `{en_path, tc_paths[]}` → scores, verdict, evidence
- `POST /api/downloads` `{mode: single | pair_zip | bulk_zip, items[{path, filename}], zip_name?}` → `{job_id}`
- `GET /api/downloads/{id}` → job progress
- `GET /api/downloads/{id}/file` → the file with `Content-Disposition`

All errors share one shape: `{code, message, details?}` with codes from §9.

## 8. UX and visual design

**Audience and job:** a nontechnical analyst who needs the right bilingual pair and needs to trust the result. The interface should feel calm, document-centred and precise.

**Required states and elements**

- Search: stock field with live lookup (for example "00700 Tencent Holdings 騰訊控股"), a delisted badge; a reused code opens its active company directly, with a note such as "00013 was also used by HUTCHISON (delisted). Switch"; a chooser only when no single active company holds the code; date range with presets (Today, Last 7 days, Last 30 days, This year, Custom) computed in HKT and labelled "Hong Kong time"; category picker defaulting to All categories; optional keyword.
- Progress: plain step text ("Searching the English section", "Searching the Chinese section", "Pairing versions"), announced to screen readers.
- Results: a summary line ("28 announcements: 25 matched, 2 to check, 1 English only") with filter chips by status; newest first.
- Announcement entry: status (icon plus word, never colour alone); date and time in HKT; category; code and company; an EN row and a TC row, each with title, size, format, source link, download button and editable proposed filename; "Download both (ZIP)", disabled with a reason when a version is missing; expandable "Why this pairing" evidence; rivals and "Check contents" for `check` entries.
- Bulk: selection checkboxes and "Download selected as ZIP".
- Download feedback: per-file progress, then "Sent to your downloads"; failures state the reason and offer Retry.
- Empty, error and too-many-results states that say what to do next.
- A short "How pairing works" panel explaining the four statuses.
- A small diagnostics panel for technical reviewers.

**Design process (Phase 5):** first write a compact design plan (4 to 6 named colours with hex values, typefaces and their roles, layout with ASCII wireframes, principles), review it against the generic defaults below, and get Zarif's approval before writing UI code.

**Avoid generic defaults unless chosen deliberately:** cream background with terracotta accent; near-black with a single acid accent; identical rounded cards with the same soft shadow everywhere; gradient washes; all-caps eyebrow labels; middle-dot metadata strings; arrows appended to buttons; decorative numbering. Spend boldness in one place (for example, how the EN and TC versions visibly sit together as one unit) and keep the rest quiet. Zarif prefers minimalist, accessible UI.

**Typography:** one or two families with good Latin, plus a proper Traditional Chinese fallback stack (Noto Sans TC, PingFang TC, Microsoft JhengHei). Mark Chinese text with `lang="zh-Hant"`. Keep prose lines under 80 characters.

**Quality floor:** responsive to mobile; visible keyboard focus; WCAG AA contrast; `prefers-reduced-motion` respected; motion only in response to user actions.

**Copy rules:** sentence case; words users understand ("Chinese version", not "TC document"); buttons say exactly what happens ("Download English PDF"); an action keeps the same name throughout; errors never apologise and are never vague.

## 9. Error catalogue

| Code | Example message |
|---|---|
| `INVALID_STOCK_CODE` | Enter a stock code of up to 5 digits, for example 00700. |
| `UNKNOWN_STOCK_CODE` | No HKEX security uses code {code}. Check the code and try again. |
| `AMBIGUOUS_STOCK_CODE` | Code {code} has belonged to more than one company, and none is listed today. Choose the one you mean. |
| `INVALID_DATE_RANGE` | The start date is after the end date. / The end date is in the future; today in Hong Kong is {date}. / HKEXnews records start on 1 April 1999. |
| `NO_RESULTS` | No announcements for {code} between {start} and {end} (Hong Kong time). Try a wider range. |
| `TOO_MANY_RESULTS` | This search returns more than 20,000 documents. Narrow the dates or choose a category. |
| `HKEX_UNAVAILABLE` | HKEXnews didn't respond. Try again in a minute. |
| `HKEX_RATE_LIMITED` | HKEXnews is limiting requests. Retrying shortly. |
| `NOT_A_PDF` | This entry is a web page on HKEXnews, not a PDF. Open it on HKEXnews. |
| `DOWNLOAD_FAILED` | The Chinese PDF couldn't be downloaded (connection timed out). Nothing was saved. |
| `VERIFY_FAILED` | HKEXnews sent an incomplete file (2.1 of 4.8 MB). Nothing was saved. |
| `ZIP_INCOMPLETE` | The ZIP wasn't created because 1 of 6 files failed. Retry the failed file. |

## 10. Testing strategy

1. **Unit (pure logic):** validation, HKT helpers, row parsing, pagination merging, pairing rules, Title Case, filenames, verification.
2. **Property-based (Hypothesis):** any title yields a filename that is non-empty, valid on Windows (no reserved characters, no trailing dot or space), within byte and character limits, deterministic, and keeps the `LANG_YYYY-MM-DD-CODE-` prefix.
3. **Recorded fixtures:** real EN and TC responses captured by the Phase 0 probe (`tests/fixtures/raw/`), used to test search, normalisation and pairing offline and deterministically.
4. **Golden pairing set** (`tests/golden/pairs.yaml`): at least 50 announcements from at least 12 issuers, each verified by Zarif (both PDFs opened; same stock code, dates and figures; Claude used to read Chinese where needed). Must cover: ordinary pairs; several on one day; several in the same minute; English only with stub; Chinese only with stub; separately published annual report; bilingual identical file; revised or cancelled headline; multi-file listing document; web-page entry; pre-2007 document; delisted company. Required result: zero wrong `matched`. Report counts per status and per case type. Deviation (D-014): verified by AI reading of the documents, confirmed by Zarif, not by Zarif opening every pair; the README says so. Accepted gap (Zarif, 31 October 2026): no separately published annual report was found in real data, so that case is tested with synthetic documents only and is a README limitation; `golden_helper.py coverage` lists it as accepted, not as a failure.
5. **Fault injection (respx):** timeouts; connection reset mid-body; 500 then success; 429 with `Retry-After`; truncated body versus `Content-Length`; HTML error page with status 200; non-PDF bytes; redirect off the allowlist.
6. **API tests** with FastAPI's TestClient against fixtures.
7. **Frontend:** Vitest for state logic; Playwright end to end against the backend in fixture mode (search, view pairs, download single, download ZIP, failure and retry, invalid inputs).
8. **Live, opt-in** (`pytest -m live`, `scripts/audit_random.py`): random active stocks over recent ranges; pairs everything, runs content checks on a sample, verifies downloads, writes `docs/audit-report.md`. Failures found here and their fixes go into `TESTING.md`.

CI (GitHub Actions): offline tests and lint on Ubuntu, macOS and Windows runners. Windows matters for filenames and ZIP entry names.

## 11. Non-goals

Accounts, saved searches, alerts or monitoring, crawling across companies, translation, OCR, editing PDFs, native mobile apps.
