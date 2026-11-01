# Testing

## Run the tests

```
cd backend
uv run pytest                  # all offline tests (about 25 seconds, no internet needed)
uv run pytest -m live          # optional: two tests that call the real HKEXnews
uv run ruff check . && uv run mypy app

cd frontend
npm test                       # unit tests (Vitest)
npm run e2e                    # browser tests (Playwright), run on recorded data
```

The offline tests use responses recorded from the real HKEXnews, so they give the same result every
time. GitHub Actions is set up to run them on Ubuntu, macOS and Windows (`.github/workflows/ci.yml`).

| Suite | Result |
|---|---|
| Backend, offline | 991 passed, 1 expected failure (a known limit of "Check contents", see below) |
| Frontend unit tests | 13 passed |
| Browser tests | 10 passed |
| Code checks (ruff, mypy strict) | clean |

## Language pairing

HKEXnews lists English and Chinese documents separately and does not say which belong together,
so the app pairs them by comparing publication minute, file numbers, headline category and numbers
in the titles. A pair is "Matched" only when the evidence is strong and nothing competes for either
document; otherwise it is "Check pairing" with the candidates listed.

**How it was tested**

- Unit tests for every rule (`test_matcher.py`, `test_signals.py`), including the cases that must
  never be "Matched": a close rival, conflicting numbers, a cancelled document, documents far apart.
- Real HKEXnews responses replayed through the matcher (Tencent, an A+H company, a company with
  English-only notices, a delisted company, documents from 2005, a three-year range, an empty result).
- A **hand-checked set of 74 announcements from 21 issuers** (`backend/tests/golden/pairs.yaml`).
  Each entry says which English and Chinese files truly belong together. The test fails if the app
  shows a wrong pair as "Matched".

**Result on the 74 hand-checked announcements**

| What the app showed | Count |
|---|---|
| "Matched", and the pair is right | 53 |
| "Matched", and the pair is wrong | **0** |
| "Check pairing", right partner among the candidates | 9 |
| "Check pairing", but the listed partner is wrong (flagged as uncertain, so the user is warned) | 1 |
| Two files that belong together, shown apart rather than guessed | 1 |
| Only one language exists, and the reason is right | 10 |

The hand-checked set was verified by AI reading both documents and a person confirming; the person
did not open every PDF. It shows the rules do not confirm wrong pairs on these 74 cases, not that
they never will.

**"Check contents"** compares the figures inside the two PDFs and is shown as extra evidence only.
It never changes a status, because it can be wrong: in one 2005 case two scrip dividend forms share
their figures and it favours the wrong partner. The tests model what would happen if it did confirm
pairs, and in that model this one case is confirmed wrongly; that is the one expected failure above,
and the reason the app does not do it. About a third of the Chinese PDFs sampled cannot be read at
all, and then the app says so.

## Several announcements on the same day

Busy days are where pairing can go wrong, so they were tested hardest: 62 of the 74 hand-checked
announcements come from days with several announcements, and 18 were published in the same minute.

| Case | Announcements | "Matched", right | "Matched", wrong | "Check pairing" | Single-language or shown apart |
|---|---|---|---|---|---|
| Several on one day | 62 | 43 | 0 | 10 | 9 |
| Several in the same minute | 18 | 9 | 0 | 8 | 1 |
| Batches filed as EN, EN, TC, TC | 4 | 0 | 0 | 4 | 0 |

When the file order cannot show which Chinese file belongs to which English file, the app does not
guess: the announcement stays "Check pairing" and the evidence says why.

Same title on the same day (for example a company filing many identical disclosure forms) gives
filenames that would clash. They are numbered (`...-(2).pdf`, `...-(3).pdf`). Tests name every
recorded PDF (more than 5,000) and check each name is valid on Windows, macOS and Linux and within
the length limits, and that the PDFs of one stock never share a name.

## Missing results

| Situation | What the user sees | Tested in |
|---|---|---|
| Only an English (or only a Chinese) version exists | "English only" or "Chinese only" with the reason. The other language is never substituted | matcher tests; 10 of 10 hand-checked cases right |
| HKEXnews shows a notice in the other section ("published in the Chinese section") | The notice is linked as a source, never offered as a version | matcher tests (`test_a_stub_is_never_offered...`) |
| No announcements in the dates | "No announcements for 00700 between ... Try a wider range." | API test and browser test |
| Unknown stock code | "No HKEX security uses code 99999. Check the code and try again." | API test and browser test |
| Start date after end date, a future date, a wrongly typed date | A plain message saying what to fix | API test and browser test |
| Entry that is a web page, not a PDF | Linked on HKEXnews, no download button | download and parser tests |
| More than 20,000 documents | Asks the user to narrow the dates | search tests |
| HKEXnews slow or refusing | Retried with waits; if it keeps failing the page says so and offers nothing partial | client tests |

## Failed or interrupted downloads

The server fetches each file from HKEXnews and checks it before the browser gets it: it must be a
complete PDF (right start, full length, pages that open). Only then does the page say
"Sent to your downloads". Faults were injected on purpose (`test_downloads.py`, `test_api.py`):

| Fault | Result |
|---|---|
| Server error, then success | Retried; the file is delivered |
| Connection reset, then success | Retried; the file is delivered |
| "Too many requests" with a wait time | Waits as told, then succeeds |
| Timeout that keeps happening | Fails with a clear message |
| File shorter than announced (cut off) | Refused, never offered |
| An HTML error page sent with a "success" code | Refused |
| Bytes that are not a PDF | Refused |
| Redirect to another address | Never followed |
| File not found | Fails at once, no pointless retries |
| One file of a pair fails | No ZIP is offered. "Retry failed files" fetches only the failed file, then the ZIP |
| Another site's address, or a path with `..`, sent to the server | Refused before anything is fetched |
| Asking for a file before its job finished, or an unknown job | A clear message, no file |

While a download runs the page shows progress ("Downloading and checking 1 of 2 files…"); a failure
shows what happened and what to do next.

**Repeated downloads:** a file fetched again within an hour comes from the server's cache, with the
same name; your browser adds its own "(1)" if the file already exists. Two files with the same name
in one ZIP are numbered, never overwritten.

## Checked against the real HKEXnews

- An automated live test downloaded a real pair (English and Chinese) from HKEXnews, checked
  both files and zipped them.
- **30 random stocks, last 90 days** (`scripts/audit_random.py --stocks 30 --seed 1`, run on
  1 November 2026): 00707, 03639, 09839, 00315, 01388, 00620, 02837, 09807, 02527, 02655, 07262,
  02120, 01129, 00488, 02803, 00135, 02176, 02423, 06138, 09820, 09878, 00012, 08283, 02508,
  01458, 63950, 68165, 17228, 57337, 14308 (mostly ordinary shares, a few funds and warrants).
  - All 30 searches worked; 760 announcements: 759 "Matched", 1 "Check pairing", none single-language.
  - For each of the 25 stocks with a confirmed pair, both PDFs were downloaded, verified and
    zipped: 25 of 25 worked. The other 5 had no announcements in the period.
  - The one "Check pairing" entry was a shared web page listed as a PDF (00135): it is linked, not downloaded.
  - This run counts statuses. It cannot show that each "Matched" is right; the hand-checked set does that.
- The hosted app was tried by hand with three stock codes, including a download.

## Try it yourself (5 minutes)

On the hosted app (the first load can take a minute):

1. Search `700` for "This year". Most announcements show **Matched**; open "Why this pairing" on one.
2. On a Matched announcement press **Download both (ZIP)**. The ZIP holds `EN_...pdf` and
   `TC_...pdf` plus `sources.csv`; open both PDFs and check they are the same announcement.
3. Search `5` (HSBC) for 1 January to 31 December 2005. Documents from before June 2007 carry no
   headline categories, so every pair shows **Check pairing**, with the candidates listed.
4. Search `99999`: a message says no security uses that code.
5. Search one stock for a single day with no filings (for example a Sunday): a message says there
   are no announcements.

## Not tested

- A person trying it on Windows (Chrome, Edge, unzipping in File Explorer). The automated tests are
  set up to run on Windows in CI.
- The failure messages in a real browser (they are tested at the server and API level).
- Heavy use: the hosted app is one free instance.
