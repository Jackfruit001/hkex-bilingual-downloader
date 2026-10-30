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
- **Chinese section:** the notice says (Zarif's translation) that the issuer has published an announcement in the English version, and a Chinese version may or may not be published. Exact Chinese wording from the probe: `TBC`.
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

**Q7, stubs (Verified).** Both are `.htm` files of about 1 KB (700 to 800 bytes). A stub takes the number after the real document it stands in for, in either direction.
- Chinese section stub (English-only original), 00005 and 09688: title `發行人剛在本網站英文版面發布一項公告，相應中文版本或會／或不會在本版面發布。`, body heading `上市公司訊息`. Example: EN `2026102301070.pdf`, stub `2026102301071_c.htm`.
- English section stub (Chinese-only original), 00939: title `An announcement has just been published by the issuer in the Chinese section of this website, a corresponding version of which may or may not be published in this section`, body heading `Listed Company Information`. Example: Chinese `2026103000898_c.pdf`, stub `2026103000899.htm`, category copied from the real document.
- Not every `.htm` is a stub: 00013 in 2014 to 2015 has real web-page entries titled `EXCHANGE NOTICE - TRADING HALT`. Stub detection must use the title, as in SPEC §4.4, not the extension.
Fixtures: `documents/2026102301071_c.htm`, `documents/2026103000899.htm`, `form-8k-en-only/`, `a-plus-h-30d/`.

**Q8, categories (Verified, with gaps).** `LONG_TEXT` has the form `Parent - [Child]` in English and `父類 - [子類]` in Chinese, HTML-escaped (`&#x2f;` for `/`). Some entries have no parent (`Monthly Returns`, `月報表`) and pre-2007 entries are empty (160 rows in the sample). The child name resolved to a tier code in 3,237 of 3,405 English rows (95%). Gaps: 93 names map to several codes, so resolution needs the parent too; multi-category entries join children with ` / ` (`Others / Share Buyback`); and corrections prefix `(Cancelled and Reissued)`. The category files are lists of `{code, name, count, t1code, t2Gcode}`. Fixtures: `reference/tier*.json`.

**Q9, multi-code (Verified).** Several codes are joined by `<br/>`, for example `00700<br/>80700` (HKD and RMB counters). Fixture: `annual-report-season/`.

**Q10, CORS (Verified).** The servlet sends `access-control-allow-origin: https://sc.hkexnews.hk`, so browsers on other origins cannot call it. Server-side fetching is required, which matches D-002.

**Q11, latency (Verified).** Servlet calls took 1.2 to 3.5 s from Zarif's Mac; PDF range requests 0.3 to 0.5 s; reference files 1.2 to 3.7 s (the active list is 1 MB). No throttling at roughly one request per 1 to 1.5 s. PDF host supports `Range` (HTTP 206, `%PDF-` header, `application/pdf`).

**Q12, delisted and reused codes (Verified).** `category=1` with an id from `inactivestock_sehk_e.json` searches delisted securities (00013 Hutchison, 2014 to 2015: 1,687 EN and 1,686 ZH rows). Code reuse is common: 00013 is HUTCHISON (delisted) and HUTCHMED (active); 03333 has three delisted entries (EVERGRANDE under two ids, SENYUAN INT'L). Searching is by internal id, so `AMBIGUOUS_STOCK_CODE` is a real case. The active list holds 17,399 entries; codes starting 1 and 5 alone account for about 7,200 and their names look like structured products (for example `HS#HSI  RC2708A`), so random-stock testing must filter to ordinary shares. List entries are `{i, c, n, s}`; the meaning of `s` is **Open**. Fixtures: `delisted/`, `reused-code/`, `reference/`.

**Q13, folder date (Verified).** In 6,969 rows the folder date in `FILE_LINK` always matched the `DATE_TIME` date (0 mismatches). One entry has a non-standard path (`.../dod/en.html`).

**Open after Phase 0**
- Q4 cap above 1,687 rows per call.
- Where the numbering changes from same-number-plus-`_c` to +1 (between 2005 and 2014).
- Pre-2007 coverage differs by language: 00005 in 2005 has 125 EN and 35 ZH rows. Whether the extra English rows are English-only documents without stubs is not yet checked.
- No separately submitted annual report was observed (00700 in March to May 2026: EN annual report `…01231.pdf`, TC `…01232_c.pdf`, same day).
- An English-only issuer other than the Form 8-K case was not found; 40001 (a CCB note) has no documents.
- The meaning of `s` in the stock lists.

## 10. Access constraints

- No free official API. The official real-time route is HKEX's Issuer Information feed Service for licensed vendors, historically priced in tens of thousands of HKD per quarter. Out of scope; noted in the README as the production path.
- HKEX's terms restrict programmatic or scripted access to its websites without written consent (requests go to info@hkex.com.hk). Mitigation: user-initiated searches only, single-user volumes, rate limiting, caching, an identifying User-Agent, no crawling. The README says this plainly and recommends consent or a licensed feed for production use.
