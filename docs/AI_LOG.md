# AI log

How AI tools were used, and every mistake they made that was caught. Entries were written when
the mistake was found; nothing is added later to look better. Full detail for each is in the git history.

## Tools

- **Claude (claude.ai chat):** research, planning, specification, and reading Chinese text while verifying pairs.
- **Claude Code (VS Code):** implementation, tests, scripts, refactoring. Zarif approved each phase before it started.

## What was done with them

| Date (HKT) | Tool | Task | Outcome |
|---|---|---|---|
| 30 Oct | Claude chat | Researched HKEXnews (e-Submission FAQ, search guide, terms of use) and read five open-source HKEX clients | Research notes, decisions D-001 to D-008, spec and plan. The chat could not reach hkexnews.hk, so API details stayed unconfirmed until the probe |
| 30 Oct | Zarif | Checked document URLs by hand on hkexnews.hk | Confirmed the `_c` suffix and EN + 1 numbering; found a Chinese-section stub for a Form 8-K |
| 30 Oct | Claude Code | Phase 0: scaffold and live probe of HKEXnews (about 57 requests) | Questions answered with recorded fixtures; spec assumptions corrected (M-002, M-003) |
| 30 Oct | Claude Code | Phase 1: validation, HKEX client, parser, stock lists, search; tests first | 175 offline tests; five assumptions corrected (M-004 to M-006) |
| 31 Oct | Claude Code | Phase 2: pairing engine, content check, golden set (Claude read 77 draft pairs, Zarif confirmed) | 74 verified entries; mistakes M-007 to M-017 |
| 31 Oct to 1 Nov | Claude Code | Phases 3 to 5: filenames, downloads, ZIP, API, frontend, CI, audit | 991 backend tests, 13 unit tests, 10 browser journeys; mistakes M-018 to M-022 |

## Mistakes caught

Format: **ID (date, what went wrong)** then how it was caught, then the fix.

- **M-001:** the build timeline assumed work started on Thursday 29 October; it started Friday 30. *Caught:* re-planning against the deadline. *Fix:* timeline rebuilt.
- **M-002:** the spec assumed the Chinese file number is always the English number plus 1. In 2005 files it is the same number with `_c` added (16 of 16 same-minute pairs); from 2014 it is plus 1. *Caught:* the probe's number-difference histogram showed 16 zeros. *Fix:* the rule is defined per era.
- **M-003:** three small errors in the probe code and choices: a stub test that flagged 17 MB annual reports, a cookie parser that broke on dates, and an "English-only issuer" picked without checking it had documents. *Caught:* reading the probe output before writing notes. *Fix:* two fixed, one left open rather than guessed.
- **M-004:** the stock-code cleaner folded `²` into `2`, so `²` became stock 00002. *Caught:* my own unit test. *Fix:* only full-width digits are folded; a Hypothesis property checks that every accepted code is five ASCII digits.
- **M-005:** a test assumed Tencent has one directory entry; 00700 is also YAOHAN INT'L (delisted), and about 6.7% of ordinary codes have such a twin. *Caught:* the test failed against the recorded stock lists. *Fix:* the test uses the real data; the design question went to Zarif (D-010).
- **M-006:** a one-line `sed` edit overwrote the wrong line (a class definition). *Caught:* the linter ran straight after. *Fix:* restored; line-number edits are now checked first.
- **M-007:** the statistic "Chinese file is +1 in 2,197 of 2,216 cases" left out same-minute batches. In one recorded set, 507 of 1,687 English documents have no Chinese file at +1. *Caught:* a structural check of every recording before planning Phase 2. *Fix:* notes corrected; a rule for block layouts (D-011).
- **M-008:** "a stub notice is always at the real document's number + 1" was wrong: 2 of 790 stubs sat at +2 and +3, so two English documents were shown as having no Chinese version. *Caught:* replaying every recording through the matcher. *Fix:* a second claim pass and tests.
- **M-009:** two numbering errors in the first matcher draft: a lone 2005 pair was read as the modern scheme and reached "Matched", and extra rivals were applied to 2005-style folders. *Caught:* a unit test, and reading the replay output line by line. *Fix:* pre-2007 folders default to the old scheme.
- **M-010:** my mutation-testing script reported all 21 mutants killed because of stale compiled code; run properly, two survived. *Caught:* a test that had passed failed on the next full run. *Fix:* two tests added; the script now clears the cache.
- **M-011:** I assumed every HKEXnews file is under `/sehk/`. GEM issuers (08xxx) use `/gem/`, so their announcements were never confirmed (0 of 34 matched; 32 after the fix). *Caught:* live runs on small-cap issuers, not a test. It failed on the safe side ("Check pairing"). *Fix:* both folders accepted (D-013).
- **M-012:** the content check treated any 200 characters as readable text; 21 of 62 real Chinese PDFs decode to gibberish. *Caught:* side-by-side output showing unreadable Chinese. *Fix:* a minimum share of Chinese characters (D-013).
- **M-013:** a scripted edit matched nothing, and a later one removed a neighbouring constant. *Caught:* failing tests. *Fix:* the Edit tool; scripted replacements now check their target exists.
- **M-014:** the pre-2007 "same number plus `_c`" rule produced a wrong "Matched" in HSBC's 31 March 2005 batch (English 96 with Chinese 96 instead of 95; the two forms share their figures). *Caught:* reading the documents for the golden set. *Fix:* every pre-2007 pair with no headline category stays "Check pairing" (D-015).
- **M-015:** I said the fallback would clear the one expected test failure without running it. With the content check on, that pair is still confirmed wrongly (92% of figures match and no rival is listed). *Caught:* the full test run. *Fix:* the expected failure is kept, marked strict. **Still open**; the content check never changes a status (D-017) and the README lists it.
- **M-016:** the first fallback keyed on category codes, so two correct 2014 Hutchison pairs with a retired category became "Check pairing" with a false note. *Caught:* the replay count dropped from 676 to 674. *Fix:* keyed on category text.
- **M-017:** the stub wording said the issuer published in one language only; the HKEXnews notice only says a version "may or may not" exist. *Caught:* reading the notice titles. *Fix:* reworded (D-015).
- **M-018:** 196 first-draft filename tests all passed but several could not fail (one contained `or True`), two expectations were wrong, and I added a dash rule nobody asked for. *Caught:* mutation testing found 6 real survivors. *Fix:* tests added, the extra rule removed.
- **M-019:** the first fixture-mode server answered every search with one recording whatever the dates, so every announcement looked English only. *Caught:* the first API test. *Fix:* merge all recordings for the stock and filter by date.
- **M-020:** the stock suggestion list stayed open and covered the date buttons, and I ran the formatter over two unrelated scripts. *Caught:* a browser test timed out; `git status` showed the scripts. *Fix:* the list shows only while the box has focus; the scripts were restored.
- **M-021:** a live smoke test written in Phase 1 passed the wrong object and had never run, because live tests are opt-in. *Caught:* the first live run. *Fix:* corrected; live tests run once before each gate that needs them.
- **M-022:** the redesign had a logo with a half-hidden character, one status tile stretched across the page, and a logo that shrank on phones. Nothing failed in the tests. *Caught:* screenshots. *Fix:* layout corrected; the README screenshot comes from the final build.