# Research notes: HKEXnews

What we learned about HKEXnews before building, and how we know it. HKEX publishes no API
documentation, so these findings come from a live probe (30 October 2026, about 57 polite requests,
recordings kept in `backend/tests/fixtures/`) and from HKEX's own published guides.

## 1. Sources

- HKEX e-Submission FAQ, HKEXnews title search guide, HKEX terms of use (hkex.com.hk, hkexnews.hk).
- A live probe of the real site, plus manual checks of document links.
- Five open-source HKEX clients, read for ideas (section 7).

## 2. How the search works

- A JSON search endpoint (`titleSearchServlet.do`) works without a login or cookie. It returns one
  row per document with a time, title, headline category, file link, file type and size.
- **Language:** `lang=EN` gives English, `lang=ZH` gives Chinese. Other values (`TC`, `C`) quietly
  return English, so the app checks the language in the reply, not the request.
- **Dates:** both ends are inclusive, whole days, Hong Kong time.
- **Paging:** `rowRange=N` returns rows 1 to N. Up to 1,687 rows came back in one call; above that is untested.
- **No results:** an empty list, not an error.
- **Stock codes:** searches use an internal id, not the code. Codes are reused (about 7% of
  ordinary codes, for example 00700 was once YAOHAN INT'L), so the app lists the company active today first.
- **Speed:** searches take 1 to 4 seconds; no throttling at about one request a second, also from Render.
- The search endpoint refuses other websites' browsers (CORS), so the app fetches on the server.

## 3. File names and pairing evidence

- Files live at `/listedco/listconews/sehk/YYYY/MMDD/<number>.pdf`. GEM stocks (08xxx) use `/gem/`.
- The Chinese file adds `_c`. The number is one counter for the whole market each day.
- **From about 2014, the Chinese file is the English number plus 1** (2,197 of 2,216 single pairs).
- **In 2005 the Chinese file has the same number plus `_c`**, and even there it was not always the
  right partner (HSBC, 31 March 2005). So every document before 25 June 2007 is "Check pairing".
- **Batches in one minute** come in two layouts: interleaved (EN, TC, EN, TC), where +1 holds, and
  blocks (EN, EN, TC, TC), where it does not (488 groups, all Hutchison 2015 dealing disclosures).
  Blocks are never "Matched".
- English and Chinese rows of one announcement have the same release minute and the same headline category.
- `NEWS_ID` is not shared between languages, so it is weak evidence.
- The folder date always matched the publication date (6,969 rows).

## 4. Notices in the other section ("stubs")

When an issuer publishes in one language, the other section may show a small notice, for example
"…a corresponding version of which may or may not be published in this section". The notice says a
version *may or may not* exist, so the app says "No Chinese version found" and links the notice. It
never treats a notice as a document. It is found by its title, not by the `.htm` ending, because
some real web pages are also `.htm`. A notice sits right after the document it stands in for, but
other companies' files can fall between (2 of 790 at +2 or +3).

## 5. Other things the parser handles

- Several stock codes in one entry are joined by `<br/>`; titles contain HTML entities.
- Headline categories look like `Parent - [Child]`; corrections start with markers such as
  `(Cancelled and Reissued)`, `(Headline Revised)` or, in Chinese, `(修改後標題)` and `(經修訂)`.
- `FILE_TYPE` cannot be trusted alone: some entries are shared web pages (`/dod/en.html`) listed as
  PDFs. The path ending decides whether something is downloadable.
- About a third of Chinese PDFs have text that cannot be read (an embedded font), so the content check says so.
- Files can be large (a 20 MB Form 8-K).

## 6. HKEX rules that matter for pairing (e-Submission FAQ)

- Both languages are normally submitted together; annual reports and listing documents may be
  submitted separately, one after the other.
- Single-language publication is allowed in some cases (overseas regulatory announcements, structured products).
- A bilingual document is submitted twice, once under each title.
- Corrections leave the original visible, marked cancelled or revised.
- A stock-code search covers documents from 1 April 1999; headline categories exist only from 25 June 2007.

## 7. Existing projects (read for ideas, no code copied)

| Project | Licence | What we learned |
|---|---|---|
| hkex-filing-scraper (simonmak-ascent) | MIT | Cumulative paging; defensive field parsing |
| ah-disclosure-kit (hc938456) | MIT | The prefix lookup lists active stocks only; a PDF validity check |
| filings-fetcher (alpenmilch411) | MIT | A minimal search client |
| hkex-tools (leofisG), financestreet (frederick623) | none found | Stock list and category endpoints; learned from only, no reuse |
| Apify "HKEX News Announcements" | commercial | Rejected: costs money and needs a token |

None of them pairs English and Chinese versions.

## 8. Access and terms

- There is no free official API. HKEX's paid real-time feed is for licensed vendors and out of scope.
- HKEX's terms restrict scripted access without written consent. The app only runs user-initiated
  searches at single-user volume, with rate limiting, caching, an identifying User-Agent and no
  crawling. Production use should get HKEX's consent or a licensed feed.

## 9. Not known

- Rows per call above 1,687.
- The year the Chinese numbering changed from "same number plus `_c`" to "plus 1".
- Whether the i-th English file of an EN, EN, TC, TC block always belongs with the i-th Chinese file
  (two groups checked against the PDFs support it; blocks stay "Check pairing" anyway).
- A separately published annual report in real data (only HSBC's 2005 report was found).
