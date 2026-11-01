# Research notes: HKEXnews

What we know about HKEXnews and how we know it. Every behaviour the code depends on should trace back to an entry here.

Status tags: **Verified** (probe, fixture or direct observation), **Documented** (HKEX publication), **Reported** (seen in third-party code, not yet verified), **Open**.

## 1. Sources consulted (29 to 30 Oct 2026)

- HKEX e-Submission FAQ, Submission Related Matters: https://www.hkex.com.hk/Global/Exchange/FAQ/ESS-All-FAQs/Submission-Related-Matters?sc_lang=en
- HKEXnews title search guide (GEM edition, same system): https://www2.hkexnews.hk/-/media/HKEXnews/Homepage/Listed-Company-Publications/Search-Guide/GEMTitleSearchGuide_e.pdf
- HKEX disclaimer and terms of use: https://www.hkex.com.hk/Global/Exchange/Disclaimer?sc_lang=en and https://www.hkex.com.hk/Global/Exchange/Terms-of-Use?sc_lang=en
- HKEX real-time datafeeds (Issuer Information feed Service): https://www.hkex.com.hk/Services/Market-Data-Services/Real-Time-Data-Services/Overview/Real_time-Datafeeds?sc_lang=en
- Five open-source HKEX clients, read in full (§7).
- Manual checks on hkexnews.hk by Zarif (§4).

The research sandbox could not reach hkexnews.hk, so everything tagged Reported must be confirmed by the Phase 0 probe.

## 2. Endpoints (Reported)

| Purpose | URL |
|---|---|
| Title search (JSON) | `https://www1.hkexnews.hk/search/titleSearchServlet.do` |
| Title search page (HTML, JSF) | `https://www1.hkexnews.hk/search/titlesearch.xhtml?lang=en` (and `lang=zh`) |
| Active securities | `https://www1.hkexnews.hk/ncms/script/eds/activestock_sehk_e.json` (`_c` for Chinese names) |
| Delisted securities | `https://www1.hkexnews.hk/ncms/script/eds/inactivestock_sehk_e.json` (`_c`) |
| Headline categories | `https://www1.hkexnews.hk/ncms/script/eds/tierone_e.json`, `tiertwogrp_e.json`, `tiertwo_e.json` (`_c`) |
| Document types | `https://www1.hkexnews.hk/ncms/script/eds/doc_e.json` |
| Stock prefix lookup (JSONP, active only) | `https://www1.hkexnews.hk/search/prefix.do?lang=EN&type=A&name=<code>&market=SEHK&callback=callback` |

Search parameters seen in the clients: `sortDir` (0 = newest first), `sortByOptions=DateTime`, `category` (0 = current securities, 1 = delisted), `market=SEHK` (Main Board and GEM), `stockId` (internal id, not the stock code), `documentType=-1`, `fromDate` and `toDate` (`YYYYMMDD`), `title`, `searchType`, `t1code`, `t2Gcode`, `t2code` (category tiers; `-2` = all), `rowRange`, `lang` (clients use `EN` or `E`; the Chinese value is unconfirmed).

Stock list entries are compact objects (reported keys: `i` id, `c` code, `n` name).

## 3. Response shape (Reported)

The servlet returns JSON whose `result` field is itself a JSON-encoded string (or the string `null`), plus `hasNextRow`, `recordCnt` and `loadedRecord`. Each row has `NEWS_ID`, `DATE_TIME` (`DD/MM/YYYY HH:MM`, HKT), `STOCK_CODE`, `STOCK_NAME`, `TITLE`, `LONG_TEXT` (headline category path, localised), `SHORT_TEXT`, `FILE_LINK` (relative path), `FILE_TYPE`, `FILE_INFO` (size label) and `TOTAL_COUNT`.

Gotchas reported by other clients:

- `STOCK_CODE` and `STOCK_NAME` can hold several values joined by `<br/>` (dual counters, joint announcements).
- Titles and categories contain HTML entities.
- Fields documented as strings can be null or numbers.
- Pagination is cumulative: `rowRange=N` returns rows 1 to N. One client (hkex-tools) appends every response and so duplicates rows; another (hkex-filing-scraper) slices off rows already seen. Clients have used `rowRange` values of 5,000 and 10,000.

## 4. File naming (Verified by Zarif, 30 Oct 2026)

Path: `/listedco/listconews/sehk/YYYY/MMDD/<stem>.<ext>`

- `MMDD` is the publication date folder, not an identifier: `2026/1028` means 28 October 2026.
- The stem `2026102801739` is the date `20261028` followed by a running sequence (`01739`) for that day. The sequence appears to be shared by every issuer that day, so it encodes publication order, not the company. The internal `stockId` does not appear in URLs.
- Chinese-section files add `_c`. Older files use `LTN<date><seq>` (for example `LTN20160728721.pdf`); the Chinese suffix in that era is unconfirmed. Older URLs also use upper-case `SEHK` path segments, and some old documents are `.doc` files.
- Multi-file documents can sit in a sub-folder (seen: `/listedco/listconews/sehk/2008/1120/00705_439528/EWP127.pdf`).

Observed pairs:

| Case | EN | TC | Note |
|---|---|---|---|
| Zai Lab (09688), Next Day Disclosure Return, 28/10/2026 22:52 | `2026/1028/2026102801739.pdf` | `2026/1028/2026102801740_c.pdf` | TC = EN + 1 |
| Overseas Regulatory Announcement, Form 8-K, 23/10/2026 | `2026/1023/2026102301070.pdf` | stub `2026/1023/2026102301071_c.htm` (1 KB) | English only; the stub also takes EN + 1. Issuer to confirm (probably 09688) |
| Another issuer's prospectus, 21/09/2026 (listed in the issuer's own notice) | `2026/0921/2026092100029.pdf` | `2026/0921/2026092100030_c.pdf` | TC = EN + 1 |

Zarif's observation: TC is "usually always" EN + 1. Treat this as strong evidence, not a rule; separate submissions and bilingual files are known exceptions (§6).

## 5. Stub notices (Documented and Verified)

When an issuer publishes in one language only, the other section gets a notice entry instead of a document.

- **English section:** the notice title contains a fragment such as "published by the issuer in the Chinese section". These notices exist as HTM files and also as small PDFs.
- **Chinese section:** the notice says that the issuer has just published an announcement in the English section, and a Chinese version may or may not be published. Verified title: `發行人剛在本網站英文版面發布一項公告，相應中文版本或會／或不會在本版面發布。` (probe, 30 Oct 2026). Verified English-section title: `An announcement has just been published by the issuer in the Chinese section of this website, a corresponding version of which may or may not be published in this section`. Both are `.htm` files of about 1 KB.
- **Detection:** title fragment match, with file type and size as supporting evidence. Never pair or offer a stub as a language version.

## 6. HKEX submission rules relevant to pairing (Documented, e-Submission FAQ)

- Where both languages are required, both versions are normally submitted together. Annual reports and listing documents may be submitted in each language separately, one after the other.
- Single-language publication is allowed where the Listing Rules permit: usually overseas regulatory announcements and structured products' trading and pre-listing reports.
- A bilingual document is submitted twice: once under the English title and once under the Chinese title.
- A headline correction leaves the original visible, marked as cancelled, and adds a "Headlines Revised" entry with identical documents and titles. Other corrections mark the original "Cancelled and Re-issued", and the replacement's title starts with "(Revised)".
- Chinese titles accept Traditional characters only. Document content may still be Simplified Chinese (for example some mainland regulatory announcements). Titles can be up to 500 characters.
- Joint announcements and multiple-counter issuers list several stock codes on one entry.

**Search guide (Documented):** a stock-code search covers documents from 1 April 1999; headline-category search applies only to documents published on or after 25 June 2007.

## 7. Existing projects

| Project | Licence | What we learned | Use |
|---|---|---|---|
| https://github.com/simonmak-ascent/hkex-filing-scraper | MIT | Handles cumulative pagination correctly; defensive field parsing; JSF session details | Reference; adapt small parts only with attribution |
| https://github.com/hc938456/ah-disclosure-kit | MIT | `prefix.do` lists active securities only, so it keeps a manual map for delisted ones; PDF validity check (HEAD plus a range read for `%PDF`) | Reference. Its EN-to-TC helper assumes "+1 and `_c`" without verification |
| https://github.com/alpenmilch411/filings-fetcher | MIT | Minimal servlet client; resolves `stockId` from a hidden field on the title search page | Reference |
| https://github.com/leofisG/hkex-tools | none found | Stock-list endpoints; the pagination duplication bug | Learn only; no licence means no reuse |
| https://github.com/frederick623/financestreet | none found | Category and document-type endpoints; `category` 0/1 for current/delisted; recursive date splitting when results exceed the cap | Learn only |
| Apify "HKEX News Announcements" actor | commercial | Pay per disclosure; needs an API token | Rejected: cost and credentials |

None of these pairs English and Chinese versions.

## 8. Open questions for the Phase 0 probe

| # | Question | Why it matters |
|---|---|---|
| Q1 | Which `lang` values does the servlet accept for EN and TC? | Basic access |
| Q2 | Does a direct servlet call work without a session cookie? | Client design |
| Q3 | Is `toDate` inclusive? | Inclusivity (we filter locally anyway) |
| Q4 | Is `rowRange` cumulative? Largest value honoured? Where is the total count? | Pagination |
| Q5 | Is `NEWS_ID` shared by the EN and TC versions? | Possible decisive signal |
| Q6 | Distribution of TC minus EN sequence numbers for pairs with the same time and category, across scenarios | Weight for S3 |
| Q7 | Stub formats and exact titles in both directions | Stub detection |
| Q8 | Category text formats (EN and TC), mapping to codes, multi-category entries | Signal S2 |
| Q9 | Format of multi-code `STOCK_CODE` values | Parsing |
| Q10 | CORS headers on the servlet | Architecture rationale |
| Q11 | Typical response times; any throttling | Timeouts and rate limits |
| Q12 | Delisted search (`category=1`) and examples of reused codes | Stock resolution |

## 9. Findings

Phase 0 probe, 30 Oct 2026 (HKT), run from Zarif's Mac with `scripts/probe_hkex.py` (about 57 live requests, sequential, at least 1 s apart, no throttling). Fixtures are under `backend/tests/fixtures/raw/`; raw probe output is in `scripts/probe_out/`. Q1 to Q13 below; "Open" items are listed at the end.

**Q1, language values (Verified).** `lang=ZH` (also `zh`) returns the Chinese section: the response echoes `lang: "C"` and every file link ends in `_c`. `EN` and `E` return English (echo `"E"`). `TC` and `C` are accepted with HTTP 200 but silently return English. The client must therefore assert the echoed `lang` and the `_c` suffix, never trust the parameter. Fixtures: `access-q1/{EN,E,ZH,TC,C,zh}_1.json`.

**Q2, session (Verified).** A plain GET to `titleSearchServlet.do` works with no prior page visit and no cookie. The response sets `JSESSIONID`, two `TS…` cookies and `bm_s` / `bm_so`, which look like bot-management cookies. The Render test (Gate 0) is the check that a cloud IP is not challenged.

**Q3, date bounds (Verified).** `fromDate=toDate=20261028` returned both 28 Oct documents, including one at 22:52, and nothing from other days. Both ends are inclusive for the whole day. Local filtering by HKT release time stays in the design. Fixture: `zai-lab-nddr/`.

**Q4, pagination (Verified, one part Open).** `rowRange=N` is cumulative (rows 1 to N); the first 5 rows of `rowRange=10` equal `rowRange=5`. The envelope carries `recordCnt` (total), `loadedRecord`, `hasNextRow`, and each row has `TOTAL_COUNT`. `rowRange` was honoured at 1,574 (00005, three years) and 1,687 (00013, 2014 to 2015) in a single call, and the server echoes the value. Whether a cap exists above that is **Open**: no single-stock range exceeded 1,687 rows, so the 5,000 limit in SPEC §3.3 is unverified. An empty result is `result: "null"` with `recordCnt: 0` (fixture `no-results/`). Fixtures: `access-q4/`, `large-range/`, `delisted/`.

**Q5, NEWS_ID (Verified).** `NEWS_ID` is not shared between languages. For same-minute single pairs, TC minus EN is +1 in 2,199 of 2,217 cases, -1 in 10, and +2, +3, +7 in 8. It tracks the file sequence but is weaker evidence than it, so S4 as written (decisive if shared) does not apply. Output: `scripts/probe_out/analysis.txt`.

**Q6, sequence delta (Verified).** For the same stock and minute with one document per language, TC file number minus EN file number is +1 in 2,197 of 2,216 cases, 0 in 16, and -1, +2, +3 once each. By era: modern files +1 in 1,526 of 1,529; `ltn` files from 2014 to 2015 are +1 in 671; the 16 zeros are all `ltn` files from 2005, where the Chinese file is `ltn20051128110_c.pdf` beside `ltn20051128110.pdf`. So "+1" is the rule for 2014 onwards and the same number plus `_c` applied in 2005. The cut-over year is **Open**. Same-minute pairs interleave: `listing-docs` has EN 684 with TC 685 and EN 694 with TC 695, same minute and same category, so time and category alone cannot pair them.

**Q6 correction, block layout (Verified on fixtures, 31 October, Phase 2 pre-analysis).** The Q6 figures above only count minutes with exactly one document per language, so they leave out the cases where pairing is hardest. Over every recorded scenario, same stock, same release minute and same date folder, with at least two non-stub documents per language, there are 528 such groups and two layouts:
- *Interleaved* (EN n, TC n+1, EN n+2, TC n+3...): 36 groups; 33 in 2023 to 2026 data (`large-range` 30, `results-day` 2, `listing-docs` 1) and 3 in `delisted`. The +1 rule holds inside them.
- *Block* (all English files first, then all Chinese files, for example 910, 911 EN and 912, 913 TC): 488 groups, all in `delisted` (00013, 2015), which are "Disclosure of Dealings under Rule 22 of the Takeovers Code" filings. In every one of the 488, all English titles are identical and every document, in both languages, has the same release minute and the same category codes; 475 groups are 2 + 2 documents, 11 are 3 + 3 and 2 are 4 + 4. Here the Chinese file is at +2 or +3, not +1. In total 507 of 1,687 English documents in that scenario have no Chinese file at +1, and every one of them has a Chinese file in the same minute.
- 2 further groups in `delisted` and 2 in `old-docs` follow neither pattern (for example E T E E T T).

So "TC = EN + 1" holds wherever one document per language is released per minute, and in modern interleaved batches, but **not** in block batches. Sequence number, minute, category and title cannot pair block documents; whether the i-th English file belongs with the i-th Chinese file is **Open** and is to be tested against PDF contents in Phase 2. Until it is, block groups must be `check`.

**Q7, stubs (Verified).** Both are `.htm` files of about 1 KB (700 to 800 bytes). A stub takes the number after the real document it stands in for, in either direction. **Correction (31 October, Phase 2 replay):** file numbers are one counter for the whole market on that day, so another issuer's files can sit between a document and its stub. In `large-range` (00005, three years) 788 of 790 Chinese stubs are at exactly +1, one at +2 and one at +3. The same applies to real pairs, which is why SPEC S3 gives +2 for numbers within 3.
- Chinese section stub (English-only original), 00005 and 09688: title `發行人剛在本網站英文版面發布一項公告，相應中文版本或會／或不會在本版面發布。`, body heading `上市公司訊息`. Example: EN `2026102301070.pdf`, stub `2026102301071_c.htm`.
- English section stub (Chinese-only original), 00939: title `An announcement has just been published by the issuer in the Chinese section of this website, a corresponding version of which may or may not be published in this section`, body heading `Listed Company Information`. Example: Chinese `2026103000898_c.pdf`, stub `2026103000899.htm`, category copied from the real document.
- Not every `.htm` is a stub: 00013 in 2014 to 2015 has real web-page entries titled `EXCHANGE NOTICE - TRADING HALT`. Stub detection must use the title, as in SPEC §4.4, not the extension.
Fixtures: `documents/2026102301071_c.htm`, `documents/2026103000899.htm`, `form-8k-en-only/`, `a-plus-h-30d/`.

**Q8, categories (Verified, with gaps).** `LONG_TEXT` has the form `Parent - [Child]` in English and `父類 - [子類]` in Chinese, HTML-escaped (`&#x2f;` for `/`). Some entries have no parent (`Monthly Returns`, `月報表`) and pre-2007 entries are empty (160 rows in the sample). The child name resolved to a tier code in 3,237 of 3,405 English rows (95%). Gaps: 93 names map to several codes, so resolution needs the parent too; multi-category entries join children with ` / ` (`Others / Share Buyback`); and corrections prefix `(Cancelled and Reissued)`. The category files are lists of `{code, name, count, t1code, t2Gcode}`. Fixtures: `reference/tier*.json`.

**Q9, multi-code (Verified).** Several codes are joined by `<br/>`, for example `00700<br/>80700` (HKD and RMB counters). Fixture: `annual-report-season/`.

**Q10, CORS (Verified).** The servlet sends `access-control-allow-origin: https://sc.hkexnews.hk`, so browsers on other origins cannot call it. Server-side fetching is required, which matches D-002.

**Q11, latency (Verified).** Servlet calls took 1.2 to 3.5 s from Zarif's Mac; PDF range requests 0.3 to 0.5 s; reference files 1.2 to 3.7 s (the active list is 1 MB). No throttling at roughly one request per 1 to 1.5 s. PDF host supports `Range` (HTTP 206, `%PDF-` header, `application/pdf`).

**Q12, delisted and reused codes (Verified).** `category=1` with an id from `inactivestock_sehk_e.json` searches delisted securities (00013 Hutchison, 2014 to 2015: 1,687 EN and 1,686 ZH rows). Code reuse is common: 00013 is HUTCHISON (delisted) and HUTCHMED (active); 03333 has three delisted entries (EVERGRANDE under two ids, SENYUAN INT'L). Searching is by internal id, so `AMBIGUOUS_STOCK_CODE` is a real case. Counts from the 30 October lists (17,948 codes): 250 codes have one active and at least one delisted holder, 55 have several delisted holders and no active one, none has two active securities (D-010). The active list holds 17,399 entries; codes starting 1 and 5 alone account for about 7,200 and their names look like structured products (for example `HS#HSI  RC2708A`), so random-stock testing must filter to ordinary shares. List entries are `{i, c, n, s}`; the meaning of `s` is **Open**. Fixtures: `delisted/`, `reused-code/`, `reference/`.

**Q13, folder date (Verified).** In 6,969 rows the folder date in `FILE_LINK` always matched the `DATE_TIME` date (0 mismatches). One entry has a non-standard path (`.../dod/en.html`).

**Hosting reachability (Verified, 30 Oct 2026 22:50 HKT).** The deployed Render service (Singapore, free plan) at `https://hkex-bilingual-downloader.onrender.com/api/probe` got the servlet search (HTTP 200, 2 rows, 1.14 s) and a PDF range request (HTTP 206, `%PDF-`, 0.02 s). No block or challenge page. Only `bm_s` and `bm_so` cookies were set there, against five cookies from the Mac; the difference is unexplained but did not affect results. Only one response was captured, so the cold-start timing is **Open**. A single successful probe does not rule out later throttling, so the audit in Phase 6 repeats this from Render over many requests.

**Phase 1 findings (30 Oct 2026, from the recorded fixtures and one live run).**
- **Row identity (Verified).** `NEWS_ID` was unique in every recorded result set (6,969 rows), and `FILE_LINK` was too, but `FILE_LINK` is not an identity in general: "Documents on Display" entries use the shared pages `/listedco/listconews/sehk/dod/en.html` and `.../dod/tc.html`, whose `FILE_INFO` still describes the real file (PDF, 323KB). The search layer therefore removes repeated rows by `NEWS_ID`, not by path. Fixture: `reused-code/`.
- **Slashes in categories (Verified).** In the raw text every slash is escaped as `&#x2f;`. The separator between categories is a spaced slash (`A / B`); slashes inside a name are unspaced (`Notice of EGM/SGM`). No tier-two name contains a spaced slash, so splitting on ` / ` after unescaping is safe.
- **Category prefixes (Verified in part).** `LONG_TEXT` can start with a bracketed marker: `(Cancelled and Reissued)`, `(Cancelled since Headlines Superseded and Replaced)`, `(Cancelled [Incorrect Submission])`, `(Headline Revised)`; Chinese: `(此文件已經作廢，經修訂文件已另行發出)`, `(取消 - 標題已被取代及更換)`. The parser maps the cancelled forms in both languages and the English headline-revised form to flags. The Chinese wording for a revised headline, `(修改後標題)`, was found in Phase 2.5 and is mapped (D-015); the raw prefix is kept on every document so unmapped markers stay visible to the matcher.
- **Category resolution (Verified).** Resolving by parent and child together gives a code for 3,403 of 3,405 English rows (99.94%) with no ambiguous names; resolving by child name alone left 93 ambiguous. English and Chinese rows released in the same minute have identical code sets in 1,486 of 1,486 single pairs, so S2 is reliable where codes exist. A stub carries the category of the real document it stands in for.
- **`FILE_TYPE` (Verified).** Values seen: `PDF` 6,066, `HTM` 842, `DOC` 53 and empty 8 (for example a 2005 "Multi-Files" interim report at an `.htm` path). The parser falls back to the file extension for the empty ones.
- **Code reuse (Verified).** 250 of 3,757 active ordinary codes (`0xxxx`) also exist in the delisted list, 6.7%; Tencent (00700) shares its code with YAOHAN INT'L. Under SPEC §3.1 these ask the user to choose; see the Gate 1 report.

**Phase 2.4 findings (31 Oct 2026, live, from `scripts/golden_helper.py`; commands in `scripts/golden_drafts.sh`).** 30 issuer windows (60 search responses) and 125 PDFs (71 MB), one request at a time at least a second apart; no 403, 429, block page or redirect. Result: 77 draft entries from 21 securities (the matcher proposed 51 matched, 12 check, 8 English only, 6 Chinese only); none is verified yet.
- **GEM files live under `/gem/` (Verified; a defect in the Phase 1 parser, fixed 31 Oct, see M-011 and D-013).** Paths look like `/listedco/listconews/gem/2026/0430/2026043004744.pdf`, the same scheme as `/sehk/`, but `parse_file_path` only accepts `/sehk/`, so every GEM document loses its folder date and file number and the matcher never sees the strongest signal. Five GEM issuers (08293, 08223, 08366, 08069, 08509, 15 March to 30 April 2026, 34 announcements): as shipped, 34 `check`, 0 `matched`; with `/gem/` accepted in memory only, 32 `matched` and 2 `check` (the two are a revised row and a cancelled row, correctly held back). Safe (nothing wrongly matched) but a random 08xxx code would show no confirmed pair. Fixed by accepting `/sehk/` and `/gem/`; nine GEM drafts (08223, 08293, 08069) are in the golden set and their searches are recorded under `tests/fixtures/golden/`.
- **A third of the Chinese PDFs have no decodable text (Verified; SPEC §4.5 updated, D-013).** Of 62 Chinese PDFs, 21 gave at most 2.8% Chinese characters (gibberish from an embedded font, with a few stray digits) and 41 gave at least 14.5%; all 21 reported status `ok` because they have more than 200 characters. They are not only e-forms: Next Day Disclosure Returns, monthly returns, a proxy form and a dividend election form, but also ordinary announcements (Tencent pricing supplements and a listing notice, Meituan notes, ICBC board resolutions, Ping An and China Mobile results, AIA highlights, two annual reports). The SPEC §4.5 content check would compare figures against gibberish, and low overlap there is not evidence against a pairing (for example HSBC's Second Interim Dividend: 20% in common, the pairing is structurally clear). The content check now treats such a file as unavailable (threshold 8%, in the gap; `content_check.readable`). A file that is only partly decodable (one at 62% Chinese still shows some odd lines) passes; accepted. Whether a CFF font library (pypdf logs "fontTools is required to fully parse the encoding of a CFF Type1 font") would help is **Open** and untested.
- **Block layout, first content evidence (Verified, two groups only).** Hutchison, 27 January 2015, 18:17 and 18:16, two English and two Chinese Rule 22 filings each. Figure overlap, English file against Chinese file, diagonal (file order) against off-diagonal: 18:17 group 100% and 100% against 73% and 73%; 18:16 group 100% and 100% against 78% and 78%. The i-th English file went with the i-th Chinese file in both, but the off-diagonal is high because the forms share dates and boilerplate, so this supports the tie-break order without proving it, and D-011 stays as it is.
- **Identical bytes exist (Verified).** Of 56 pairs with both files fetched, one is byte for byte the same in both sections: ICBC's Dividend Currency Election Form (01398, news ids 12377584 and its Chinese counterpart), 51 figures. HSBC's form of the same name on 4 August 2026 is two different files.
- **Pre-2007 singles carry no notice (Verified).** In 00005, 31 March to 7 April 2005, the six English-only and two Chinese-only announcements have no stub, so their reason is `not_found`, which a person can only check by searching HKEXnews.
- **Separately published annual report: not observed (accepted gap, README limitation).** Eight main-board small caps and five GEM issuers over 15 March to 30 April 2026: six annual reports in the windows read, all paired on the same day. The only separate publication found is HSBC's 2005 Annual Report and Annual Review (English 17:11 and 17:12, Chinese 17:45 and 17:49, multi-file entries); with no categories before 2007 it cannot be recognised as a separate submission and shows as `check`.
- **Sizes (Verified).** The English Form 8-K PDF (Zai Lab, 23 October 2026) is 20 MB; small-cap annual reports are listed as 10 to 11 MB. The helper skips files over a limit (`--max-mb`) and still drafts the entry, with a note, so the PDFs can be opened on HKEXnews.

**Phase 2.5 reading findings (31 Oct 2026, Claude read the 77 golden drafts; D-014).**
- **A wrong `matched` in 2005 (Verified by reading the documents).** HSBC, 31 March 2005, 11:22. English file 96 is the Form of Election (`ltn20050331096.pdf`); Chinese file 96 (`…096_c.pdf`) is the Entitlement Advice Form (應收代息股份通知書); the Chinese Form of Election (選擇表格) is file 95, left unpaired, and English file 97 (Entitlement Advice Form) was left unpaired too. The matcher called EN 96 with TC 96 `matched` (score 8, same minute, exact number plus `_c`, 92% figure overlap because the two forms share the scrip dividend figures). This is the pre-2007 rule of D-009 failing on its own validation: D-009 says any wrong `matched` among pre-2007 pairs reverts to (a), every pre-2007 pair stays `check`. The decision is for Gate 2.
- **2005 numbering is not the same number plus `_c` (Verified, one batch).** In that minute, English to Chinese file numbers are 90 to 90, 91 to 92, 94 to 94, 96 to 95, 97 to 96 and 100 to 93 (the last published two minutes earlier). Two single-language entries the matcher produced (EN 100 Letter to Shareholder and TC 93 致股東信函, the informal meeting of 24 May 2005) are one pair.
- **Chinese revision markers are not mapped (Verified).** `修改後標題` (headline revised, in the category prefix) and `(經修訂)` (revised, a title prefix) were seen on four correct pairs, which the matcher held at `check` because only the English side carried a flag. It is a miss, never a wrong `matched`. This closes the Open item about the Chinese wording.
- **The HKEXnews notice does not say "English only" (Verified).** The Chinese-section notice reads, in effect, "a Chinese version may or may not be published in this section". The evidence text and SPEC §4.1 wording "The issuer published this in English only" says more than the notice does; for the single-language entries here no Chinese version appeared within the searched window. Wording is for Gate 2.
- **A separately published annual report exists before 2007 (Verified, titles only).** HSBC 2005: English Annual Report and Annual Review at 17:11 and 17:12 on 7 April, Chinese 年報 and 年度回顧 at 17:45 and 17:49. With no categories it cannot be recognised as separate, so it shows as `check`. It could be tagged `separate_annual_report` by hand and would close the accepted gap.
- **Figure overlap can mislead among sibling documents (Verified).** Two forms about the same dividend overlap 92%; the review had to use titles and the documents themselves.
- **Phase 2.6 golden test run (31 Oct 2026, Verified by the run).** `backend/tests/integration/test_golden.py` judges the matcher against the 74 verified entries (21 issuers; 64 pairs and 10 single-language entries), offline, from the recorded searches. Structural run (rules plus identical bytes) and run with content check, in entries: confirmed and right 50 and 56; confirmed and WRONG 1 and 1; for checking with the right partner 12 and 6; a pair shown apart 1 and 1; single with the right reason 10 and 10; for checking with a wrong partner, for checking with no counterpart, single with another reason, and not in the search result 0 in both.
- **The one wrong `matched` is the known 2005 one (Verified).** `00005-303146` in both runs (M-014); the test marks it as an expected failure, strictly, until Gate 2 decides D-009. Precision of confirmed pairs is 98.0% (50 of 51) and 98.2% (56 of 57). The one pair shown apart is `00005-303690` (the informal meeting letter, a safe miss).
- **The content check cannot catch a wrong `matched` (Verified).** SPEC §4.5 runs it on `check` entries only, so the 2005 wrong pair stays confirmed in the content run. It upgraded 6 pairs from `check` to `matched`, all right: `00005-303144`, `00005-303127` and the four block-layout pairs of `00013`. Six stay `check`: the two 2005 annual-report pairs (no figures recorded, files over the size limit); `06909-12089411` (2 figures a side); `08223-12104235` (7 and 1); `08223-12110929` (Chinese text unreadable); `00013-2104022` (5 and 6, not conclusive). The run uses figures recorded from the first three pages of the files fetched for the golden set, not live downloads.
- **No weights or thresholds were changed in Phase 2.6.**
- **Gate 2 follow-up: stub evidence reworded (31 Oct 2026; D-015).** It now reads "No Chinese version found between [dates]. HKEXnews' Chinese section shows a notice instead, saying a Chinese version may or may not be published there." (and the English equivalent, "an English version"). The status label "English only" and the reason code `stub_in_other_section` are unchanged.
- **Gate 2 follow-up: the 2005 HSBC annual reports are not tagged `separate_annual_report` (31 Oct 2026; D-015).** The separate-submission rule is for documents filed on different days; the English and Chinese reports were 34 minutes apart. The case stays the accepted gap of D-013 and shows as `check`.
- **Gate 2 follow-up: the Chinese revision markers are mapped (31 Oct 2026, Verified by the run; D-015).** Category prefix `(修改後標題)` is `headlines_revised`; title prefix `(經修訂)` is `revised`, matched at the start of the title only: 經修訂 inside a title (`第三次經修訂及重列之組織章程大綱`, the 02372 circular) is not a flag, and the cancelled marker `(此文件已經作廢，經修訂文件已另行發出)` stays `cancelled`. Recorded forms: `(Headline Revised)` and `(Headlines Revised)` in English (2015 and 2026), `(Revised)` against `(經修訂)`. Four correct pairs are now confirmed in both runs (`00013-2104022`, `06909-12089411`, `08223-12110929`, `08223-12104235`). Golden test, structural run: confirmed and right 53 (was 49), WRONG 0, for checking with the right partner 9; with the content check: right 60 (was 56), WRONG 1 (M-015), for checking 2 (the two 2005 annual reports). Replay `delisted`: 1 pair moves from check to matched (23 Jan 2015, Hutchison, score 11).
- **Gate 2 follow-up: the D-009 fallback was applied (31 Oct 2026, Verified by the run; D-015).** Pairs with no category text on either side are never `matched` on structure. Golden test, structural run: confirmed and right 49 (was 50), WRONG 0 (was 1), for checking with the right partner 13 (was 12), for checking with a wrong partner 1 (`00005-303146`, now a `check`). With the content check: right 56, WRONG 1: the check runs on the now-`check` pair and confirms it, because the matcher lists no rival. The right partner, Chinese file 95, scores 3 against EN 96 (S1 only; in 2005 numbering a nearby number scores 0), below the minimum of 4 for a rival, so the content check compares a single candidate and a single candidate with 92% overlap is conclusive (best 0.92, no second). The scrip forms share their figures, so a rival would likely have made it inconclusive (not tested: no figures were compared against file 95 in that run). Replay `old-docs`: 22 matched and 11 check before, 0 and 33 after.
- **Two 2014 pairs rely on the lower threshold (Verified).** Hutchison, 14 Jan and 7 Jul 2014: category text `Announcements and Notices - [Share Option Scheme]`, a category that is not in the 2026 category lists, so no code resolves. They are matched at score 8 under the D-009 rule for a category text without codes (S1 and S3 both hold), as before. Not changed; flagged for Gate 3.

**Phase 3.1 title survey (31 Oct 2026, Verified by the run; D-016).**
- **The recordings (probe and golden calls) hold 7,225 distinct documents** (3,658 English, 3,567 Chinese); 6,316 are `.pdf` entries that are not stubs, from 22 stocks, with 940 distinct titles (524 English, 416 Chinese). Of the English titles 248 are at least 70% upper case and get Title Case; the rest are left as published.
- **Token shapes in the all-caps titles:** digit tokens (`1Q24`, `CNY4.5`, `US$1.8`, `13.51B(2)`, `Form 8-K`), hyphenated words (`NON-EXECUTIVE`, `RE-ELECTION`, `SPIN-OFF`), dotted initialisms (`L.P.`, `S.P.A.`, `A.S. WATSON`), bracketed numbers and letters (`(1)`, `(A)`), colons (`LETTER TO SHAREHOLDERS: 2015 ...`) and a spaced slash. Abbreviations not in the SPEC list: HSBC (22 titles), CKH, CK, CNY, AUD, MREL, GSK. No title uses an en or em dash as the separator.
- **File numbers are 3 or 4 digits in 2015 paths** (`ltn20150429999`, `ltn201504291381`), so ordering by path text puts 1000 before 999; the naming order compares them as numbers.
- **Filenames over the 6,316 PDFs:** all valid on the universal platform and within 120 characters and 180 bytes; 146 had to be cut; 3,036 need a number, 2,974 of them Hutchison (00013) in 2015, where hundreds of Rule 22 dealing disclosures share one title (highest number `-(37)` on a day). The longest names reach exactly 120 characters.

**Open after Phase 0**
- Q4 cap above 1,687 rows per call.
- Where the numbering changes from same-number-plus-`_c` to +1 (between 2005 and 2014).
- Whether, in block batches (EN, EN, TC, TC), the i-th English file belongs with the i-th Chinese file (see Q6 correction). Two groups checked against PDF contents on 31 October support it (Phase 2.4 findings); more are needed.
- Pre-2007 coverage differs by language: 00005 in 2005 has 125 EN and 35 ZH rows. The extra English rows are English-only documents without stubs, at least in the one week checked (Phase 2.4 findings).
- No separately submitted annual report was observed (00700 in March to May 2026, and eight small caps in 2026, see Phase 2.4 findings).
- An English-only issuer other than the Form 8-K case was not found; 40001 (a CCB note) has no documents.
- The meaning of `s` in the stock lists.

## 10. Access constraints

- No free official API. The official real-time route is HKEX's Issuer Information feed Service for licensed vendors, historically priced in tens of thousands of HKD per quarter. Out of scope; noted in the README as the production path.
- HKEX's terms restrict programmatic or scripted access to its websites without written consent (requests go to info@hkex.com.hk). Mitigation: user-initiated searches only, single-user volumes, rate limiting, caching, an identifying User-Agent, no crawling. The README says this plainly and recommends consent or a licensed feed for production use.
