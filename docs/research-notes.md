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

(Phase 0 appends dated findings here, each linked to its fixture files.)

## 10. Access constraints

- No free official API. The official real-time route is HKEX's Issuer Information feed Service for licensed vendors, historically priced in tens of thousands of HKD per quarter. Out of scope; noted in the README as the production path.
- HKEX's terms restrict programmatic or scripted access to its websites without written consent (requests go to info@hkex.com.hk). Mitigation: user-initiated searches only, single-user volumes, rate limiting, caching, an identifying User-Agent, no crawling. The README says this plainly and recommends consent or a licensed feed for production use.
