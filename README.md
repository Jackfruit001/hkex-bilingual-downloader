# HKEX bilingual downloader

Enter a Hong Kong stock code and a date range, browse that company's HKEXnews announcements,
and download the English and Traditional Chinese PDFs together, paired and named correctly.

![The search page and a matched announcement](docs/screenshot.png)

**Hosted app:** _link added at submission_ · **Needs:** a modern browser. Nothing to install, no
account, no cost.

## How to use it

1. **Search.** Type a stock code (`700`, `00700` or `700.HK`) or part of a company name, pick a
   date range (all dates are Hong Kong time), and press "Search announcements".
2. **Read the pairs.** Each announcement shows its English and Chinese version side by side, with
   a status: **Matched**, **Check pairing**, **English only** or **Chinese only**. "Why this
   pairing" explains the evidence. Nothing uncertain is shown as matched.
3. **Download.** One PDF, both as a ZIP, or tick several announcements and download them as one
   ZIP. Files are the original PDFs from HKEXnews, saved as `EN_2026-10-15-00700-Title.pdf` and
   `TC_2026-10-15-00700-標題.pdf`. A ZIP is offered only when every file in it was fully received
   and checked.

## Run it locally

Needs Python 3.12 with [uv](https://docs.astral.sh/uv/), and Node 22.

```
# one process, one address (what the hosted app does)
cd frontend && npm install && npm run build && cp -r dist ../backend/static
cd ../backend && uv sync && uv run uvicorn app.main:app      # http://127.0.0.1:8000

# or with Docker
docker build -t hkex-bd . && docker run -p 8000:8000 hkex-bd

# development: backend on :8000, frontend with hot reload on :5173
cd backend && uv run uvicorn app.main:app --reload
cd frontend && npm run dev

# no network: recorded HKEXnews responses (try 700, 30 Sep to 30 Oct 2026)
cd backend && HKEX_MODE=fixtures uv run uvicorn app.main:app
```

Tests: see [TESTING.md](TESTING.md).

## How pairing works

HKEXnews lists English and Chinese documents separately and says nothing about which belong
together. The app compares publication minute, HKEX file numbers, headline categories and numbers
in the titles. A pair is **Matched** only when the evidence is strong, nothing else competes for
either document, and nothing conflicts. If a likely counterpart exists but the evidence is not
enough, it is **Check pairing** and the competing candidates are listed. A missing version is
never replaced by the other language. "Notice" stubs that HKEXnews publishes in the other
section are linked as sources and never offered as a version. Full rules: `docs/SPEC.md` §4.

On a hand-checked set of 74 announcements from 21 issuers (`backend/tests/golden/`), the rules
alone confirm 53 correctly and 0 wrongly. With the optional content check one wrong confirmation
remains (see limitations).

## The Title Case decision

HKEXnews titles are often ALL CAPS. English filenames use Title Case when at least 70% of the
letters are upper case (`OVERSEAS REGULATORY ANNOUNCEMENT - FORM 8-K` becomes
`Overseas-Regulatory-Announcement-Form-8-K`), keeping acronyms such as HSBC and Roman numerals.
Mixed-case titles and all Chinese titles stay as published. Rules and reasons: `docs/SPEC.md` §5
and D-004, D-016. The list of acronyms is in `backend/app/config.py`.

## Known limitations

Rare cases are listed here instead of being built around.

- **Before 25 June 2007** documents have no headline categories and irregular file numbers, so
  every pair there is "Check pairing" unless the two files are identical (D-009, D-015).
- **Check contents** compares figures in the two PDFs and is shown as extra evidence only: it does
  not change a status (D-017). About a third of the Chinese PDFs sampled have text that cannot be
  read, so the check is unavailable for them. Two documents that share their figures can fool it:
  in the golden set, two 2005 HSBC scrip dividend forms matched at 92% and the wrong one looked
  confirmed (M-015, open; the fix is to compare against every candidate the matcher considered).
- **Reused stock codes** (00700 was once YAOHAN INT'L's) search the company listed today. Earlier
  holders appear as a "Switch" link (D-010).
- **Annual reports published separately in each language** are looked for up to 14 days apart and
  shown as "Check pairing". Tested with synthetic documents only; no real example was found.
- **Web pages and multi-file entries** on HKEXnews are linked, not downloaded (they are not PDFs).
- **No filename editing** in the page. Names follow the rules above; the server cleans any name it
  is sent. Very long titles are cut at a word boundary to fit 120 characters.
- **Searches over 20,000 documents** per language ask you to narrow the dates or pick a category.
- **A bulk ZIP** is limited to 50 announcements and 500 MB.
- **HKEXnews outages and rate limiting** are retried with backoff; if it keeps failing the page
  says so and nothing partial is offered.
- **The golden set** was verified by AI reading of both documents and confirmed by a person, not by
  a person opening every PDF (D-014).
- **Hosting:** a free Render instance sleeps when idle, so the first request can take about a
  minute. Rate limits are per address and kept in memory.

## HKEXnews use

The app fetches public documents from HKEXnews only, one at a time at a low rate, with an
identifying User-Agent, caching, and no background crawling. It never fetches a URL supplied by a
browser: it accepts only HKEXnews document paths and checks them first. Documents belong to their
issuers and HKEX; the app saves them unchanged. Read HKEXnews' terms of use before heavy use.

## Reused projects and libraries

Licences are in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Backend: FastAPI, httpx,
Pydantic, pypdf, pathvalidate. Frontend: React, Tailwind CSS, Vite. Open-source HKEX clients were
read for reference only and no code was copied (`docs/research-notes.md` §7).

## How AI was used

Built with Claude Code (Claude Sonnet 5.5) under Zarif's direction, in phases with written gates:
research and probes of HKEXnews first, then tests, then features.

- **Decisions** are in `docs/DECISIONS.md`; the specification and plan are in `docs/`.
- **Pairing was verified** against a golden set and against recorded real responses, not by
  trusting the code. Downloads are verified by content (PDF header, length, page count) before
  anything is offered.
- **AI mistakes are logged** in `docs/AI_LOG.md` (20 entries). One example, M-015: a content check
  that looked conclusive confirmed a wrong pair because it compared against only one candidate.
  Others were caught by mutation testing (M-018), by an API test (M-019) and by a browser test
  (M-020).
- **Time spent:** _to be filled in by Zarif_.
