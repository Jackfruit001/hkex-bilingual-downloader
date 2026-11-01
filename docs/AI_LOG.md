# AI log

How AI tools were used, and the mistakes they made that were caught. Entries are factual and written at the time; nothing is added later to look better.

## Tools

- **Claude (claude.ai chat):** research, planning, specification, and reading Chinese text during verification.
- **Claude Code (VS Code):** implementation, tests, scripts, refactoring.

## Usage log

| Date (HKT) | Tool | Task | Outcome |
|---|---|---|---|
| 2026-10-30 | Claude chat | Researched HKEXnews: HKEX e-Submission FAQ, search guide, terms of use, official datafeed; cloned and read five open-source HKEX clients | Research notes, decisions D-001 to D-008, spec and plan. The chat sandbox could not reach hkexnews.hk, so API details stay "Reported" until the probe confirms them |
| 2026-10-30 | Manual (Zarif) | Checked document URLs on hkexnews.hk | Confirmed the `_c` suffix and EN + 1 numbering (Zai Lab, 28 Oct); found a Chinese-section stub for a Form 8-K at EN + 1 |
| 2026-10-30 | Claude Code | Phase 0: backend and frontend scaffold, `scripts/probe_hkex.py`, live probe of HKEXnews (about 57 requests), findings in research notes §9 | Q1 to Q13 answered with fixtures; several spec assumptions corrected (see M-002, M-003) |
| 2026-10-30 | Claude Code | Phase 1: domain validation and HKT helpers, HKEX client, parser, reference data with snapshot, search with pagination; tests first throughout | 175 offline tests and 1 live smoke test; five assumptions corrected (M-004 to M-006) |

## Mistakes caught

### M-001: plan anchored to the wrong start day

- **Date and tool:** 2026-10-30, Claude chat.
- **What the AI produced:** a build timeline that treated the start day as Thursday 29 October.
- **What was wrong:** work started on Friday 30 October, so the plan assumed one more day than was available.
- **How it was caught:** re-planning against the deadline before the build started.
- **Fix:** timeline in `docs/PLAN.md` rebuilt for Friday to Monday.
- **Guard:** plans state explicit dates, checked against the actual date.

### M-002: spec assumed the Chinese file number is always the English number plus 1

- **Date and tool:** 2026-10-30, Claude chat (SPEC §4.2 S3, research notes §4); found by Claude Code in Phase 0.
- **What the AI proposed or produced:** signal S3 and the pre-2007 reasoning treated "TC = EN + 1" as the file-number rule for every era.
- **What was wrong:** in the 2005 `ltn` files the Chinese file has the same number as the English one with `_c` added (16 of 16 same-minute pairs in the sample). From 2014 on, `ltn` and modern files are +1 (2,197 of 2,216 pairs overall). The Phase 0 kickoff review had also assumed pre-2007 pairs could score at most 8 using a +4 sequence signal; that no longer holds as written.
- **How it was caught:** the analysis stage of the probe printed a delta histogram with 16 zeros; inspecting them showed they were all 2005 files.
- **Fix and commit:** finding recorded in research notes §9 (Q6); SPEC change proposed at Gate 0, not yet applied.
- **Guard added:** S3 will be defined per era from fixtures, with golden-set cases for 2005 files.

### M-003: three small assumptions in my own probe code and picks

- **Date and tool:** 2026-10-30, Claude Code.
- **What the AI produced:** (1) a stub heuristic that flagged any file whose size label ended in "B" but not "KB", which also flagged 17 MB annual reports; (2) a cookie-name list built by splitting `Set-Cookie` on commas, which broke on cookie dates; (3) 40001 (a CCB note) chosen as an "English-only issuer" without checking it had any documents.
- **What was wrong:** (1) false stubs in the analysis output; (2) a garbled evidence line for Q2; (3) the scenario returned zero rows.
- **How it was caught:** reading the probe output before writing anything into the research notes.
- **Fix and commit:** (1) and (2) fixed in `scripts/probe_hkex.py` and re-run from cache; (3) left as an Open item in research notes §9 rather than guessing another code.
- **Guard added:** findings are written into the research notes by hand after reading the output, not generated.

### M-004: stock-code normaliser accepted a superscript digit

- **Date and tool:** 2026-10-30, Claude Code.
- **What the AI produced:** `normalise_stock_code` applied Unicode NFKC so that full-width digits typed on a Chinese keyboard would work.
- **What was wrong:** NFKC also folds `²` to `2`, so the input `²` became stock `00002`.
- **How it was caught:** my own unit test listed `²` as an input that must be rejected.
- **Fix and commit:** only the ten full-width digits (U+FF10 to U+FF19) are folded now; test kept.
- **Guard added:** the Hypothesis property that any accepted code is exactly five ASCII digits.

### M-005: test assumed Tencent has one directory entry

- **Date and tool:** 2026-10-30, Claude Code.
- **What the AI produced:** a test expecting `lookup("00700")` to return one security.
- **What was wrong:** 00700 is also the code of YAOHAN INT'L (delisted), so with SPEC §3.1 as written even Tencent would show a "choose the company" prompt. About 6.7% of ordinary `0xxxx` codes (250 of 3,757) have a delisted twin.
- **How it was caught:** the test failed against the recorded stock lists.
- **Fix and commit:** test now asserts the real data (active entry listed first); the UX consequence is raised at Gate 1 rather than silently changed.
- **Guard added:** directory tests run against the recorded lists, not hand-made ones.

### M-006: a one-line edit overwrote the wrong line

- **Date and tool:** 2026-10-30, Claude Code.
- **What the AI produced:** a `sed` command to shorten a docstring that replaced line 17 of `reference.py`, which was the `class CategoryIndex:` line, because I misread the line numbers of the listing I was working from.
- **What was wrong:** the file no longer parsed; `ruff` reported syntax errors.
- **How it was caught:** `ruff check` ran straight after the edit.
- **Fix and commit:** restored the class line and shortened the docstring on the right line; all tests green again.
- **Guard added:** line-number edits are checked against the file (a `sed -n` with numbers) before running, and the lint run follows every edit.

### M-007: the sequence-delta statistic left out the hardest cases

- **Date and tool:** 2026-10-31, Claude Code.
- **What the AI produced:** research notes Q6, "TC file number minus EN file number is +1 in 2,197 of 2,216 cases", which SPEC S3 and D-009 then treated as the rule for 2014 onwards.
- **What was wrong:** the statistic only counted minutes with exactly one document per language, which excludes same-minute batches. It was never measured how many English documents have no Chinese file at +1. In the `delisted` fixture (00013, 2014 to 2015) 507 of 1,687 do: 488 same-minute groups are laid out as English files first, then Chinese files, so the Chinese file is at +2 or +3.
- **How it was caught:** a read-only structural check of every recorded scenario, run before proposing the Phase 2 plan, not a failing test. Nothing wrong had reached the matcher or the UI, because the matcher is not built yet.
- **Fix and commit:** research notes Q6 correction and open question added; Phase 2 plan adds a block-layout case and a rule that block groups stay `check` until contents support a pairing.
- **Guard added:** when a statistic is used as the basis of a rule, the notes state the filter used to select the cases, and the rule's complement (how many cases fall outside it) is reported alongside.

### Template

### M-008: "a stub is always at the real document's number + 1"

- **Date and tool:** 2026-10-31, Claude Code.
- **What the AI produced:** research notes Q7 and SPEC §4.4 stated a stub is "always at the real document's sequence +1", and the first matcher draft claimed stubs only at exactly +1.
- **What was wrong:** file numbers are one counter for the whole market, so other issuers' files can fall between. The replay of the 00005 three-year scenario found 2 of 790 stubs at +2 and +3; those two English documents were reported as "No Chinese version found" although HKEXnews showed a notice for them.
- **How it was caught:** replaying every recorded scenario through the matcher and checking the unclaimed English documents one by one, not a failing test.
- **Fix and commit:** a second claim pass (one unclaimed same-minute document within 5 numbers, only if exactly one qualifies and it has no real counterpart), four tests, SPEC §4.4 and research notes Q7 corrected.
- **Guard added:** the replay test asserts that every stub in every recorded scenario is attached to an announcement or counted as an orphan, and that none is silently dropped.

### M-009: two numbering-scheme errors in the first matcher draft

- **Date and tool:** 2026-10-31, Claude Code.
- **What the AI produced:** (a) a numbering-scheme detector that decided "same number plus `_c`" only from pairs inside the same folder, so a lone pre-2007 pair (EN 110, TC 111_c) was read as the modern "+1" scheme and reached `matched`; (b) the ±3 "nearby number" score and the D-011 neutral layout applied in folders numbered the 2005 way, where numbers are unique within a language.
- **What was wrong:** (a) the cut-over year between the schemes is Open, so assuming the modern one could turn a wrong pair into `matched`; (b) the extra rivals produced wrong guesses, for example EN 97 shown with TC 96_c instead of EN 96, and held back pairs that are structurally unambiguous (16 matched in `old-docs` where 22 are).
- **How it was caught:** (a) a unit test I wrote for the pre-2007 rule failed on first run; (b) reading the `old-docs` replay output line by line, not a failing test.
- **Fix and commit:** pre-2007 folders default to the old scheme (config `same_number_before`); in that scheme only an exact number counts and the layout rule is not applied; D-009 and D-011 updated.
- **Guard added:** tests for the lone pair, for consecutive 2005 pairs, and for a Chinese file that must not be pulled to a neighbour; the golden set must include 2005 pairs (SPEC §10.4).

### M-010: a mutation check that reported false "killed" results

- **Date and tool:** 2026-10-31, Claude Code.
- **What the AI produced:** a throwaway harness that mutates one line of the golden helper, runs its tests, and restores the file, to show the tests would notice a broken budget, allowlist, append rule or case tag. It reported all 21 mutants killed.
- **What was wrong:** the harness restored each file within the same second as the mutation, and some mutants had the same file size as the original (`1.0` and `0.0`). Python reused the compiled mutant, so the working tree behaved as if the code were broken after the harness finished, and some "killed" verdicts came from stale bytecode. Run properly, two mutants survived: a document on 1 January 2007 was never tested against the pre-2007 rule, and the coverage test only asserted that some gap existed, which the missing case types guarantee, so counting drafts as verified went unnoticed.
- **How it was caught:** the next full test run failed one test that had passed (`test_live_requests_are_at_least_a_second_apart`), and a small debug script printed the client's spacing as 0.0 although the source said 1.0. I cleared the cache and reran with bytecode writing off.
- **Fix and commit:** two tests added (the 2007 boundary on both sides; totals count verified entries only, with exact gap messages); all 21 mutants are killed on a clean run. Nothing in the helper's code changed.
- **Guard added:** the harness now sets `PYTHONDONTWRITEBYTECODE=1` and clears the cache before each run, and a mutation result only counts after a clean full run of the suite.

### M-011: "every HKEXnews file lives under `/sehk/`"

- **Date and tool:** 2026-10-31, Claude Code (written in Phase 1.4, found in Phase 2.4).
- **What the AI produced:** `parse_file_path` (Phase 1) accepts only `/listedco/listconews/sehk/YYYY/MMDD/...`; SPEC §3.4 describes the folder date and file number without saying the folder name can differ.
- **What was wrong:** GEM issuers' files live under `/listedco/listconews/gem/...` with the same numbering. Every GEM announcement lost its folder date and file number, so the sequence signal never applied: five GEM issuers (34 announcements) came out 34 `check` and 0 `matched`; with the folder accepted, 32 `matched` and 2 `check`. A random 08xxx code (305 active securities) would show no confirmed pair.
- **How it was caught:** the live table runs of Phase 2.4 on small-cap issuers, a probe, not a test. None of the 12 recorded scenarios had a GEM issuer, so no test could see it. Nothing wrong reached a user: the failure is on the safe side (`check`, never a wrong `matched`).
- **Fix and commit:** raised for Zarif rather than fixed in Phase 1 unasked; Zarif delegated it on 31 October. The pattern now accepts `sehk|gem` (D-013), with three new parser cases; nine GEM drafts are in the golden set.
- **Guard added:** GEM path cases in the parser test, and GEM issuers in the golden set and its fixtures.

### M-012: the content check treats any 200 characters as readable text

- **Date and tool:** 2026-10-31, Claude Code (SPEC §4.5 and Phase 2.3).
- **What the AI produced:** SPEC §4.5 step 2 says text under 200 characters means "unavailable (scanned document)"; `content_check.extract_text` implements exactly that.
- **What was wrong:** 21 of 62 real Chinese PDFs yield more than 200 characters of gibberish (an embedded font pypdf cannot decode, 2.8% Chinese characters at most), so they count as readable. The content check would compare figures against noise and could report "X% of figures match" or a false "conclusive". The other 41 files are at 14.5% or more, a clear gap.
- **How it was caught:** the side-by-side first-page output of the golden helper showed unreadable Chinese for HSBC's Second Interim Dividend with a 20% overlap; measuring every cached Chinese PDF followed.
- **Fix and commit:** first in the helper only (D-012), then in the product after Zarif delegated the decision: `content_check.readable` and `content_min_chinese_share = 0.08` (D-013, SPEC §4.5), used by the helper too.
- **Guard added:** tests for the rule and a test that the threshold sits inside the measured gap (2.8% against 14.5%).

### M-013: a scripted edit that matched nothing

- **Date and tool:** 2026-10-31, Claude Code.
- **What the AI produced:** a Python string replacement in `draft.py` to pass the new `status` and `note` into `FileView`; the target text had been reformatted by `ruff format` earlier, so the replacement silently did nothing.
- **What was wrong:** the new "undecodable text" rule was not applied, while the rest of the change was.
- **How it was caught:** the new integration test failed on first run.
- **Fix and commit:** edited with the Edit tool; the full suite passed.
- **Guard added:** scripted replacements assert that their target exists before writing. A later scripted multi-line cut removed a neighbouring constant as well; the suite failed at once, and the lesson is to make small edits with the Edit tool and run the tests straight after.

### M-014: the pre-2007 "same number plus `_c`" rule produced a wrong `matched`

- **Date and tool:** 2026-10-31, Claude Code (matcher, Phase 2.2, D-009).
- **What the AI produced:** a rule that, before 25 June 2007, treats an exact file number plus `_c` in the same minute as strong evidence, enough for `matched` at a lower score threshold (D-009), validated only on the 2005 pairs in the recordings.
- **What was wrong:** in HSBC's 31 March 2005 batch the Chinese files are not at the English number: English 96 (Form of Election) was matched with Chinese 96 (Entitlement Advice Form) while the real counterpart, Chinese 95, stayed unpaired. Figure overlap (92%) agreed, because the two forms share their figures.
- **How it was caught:** reading the documents for the golden set (Phase 2.5); a triage that trusted figure overlap had classed the entry as strong.
- **Fix and commit:** at Gate 2 (31 October 2026) Zarif chose the fallback named in D-009 (every pre-2007 pair stays `check`); applied in D-015 and the commit that follows it. It fixes the structural run only; see M-015.
- **Guard added:** the corrected entry and the two single-language entries that are really a pair go into the golden set, so the golden test (2.6) fails on this case until the rule is changed.

### M-015: predicted that the fallback would clear the strict expected failure

- **Date and tool:** 2026-10-31, Claude Code (Gate 2 follow-up).
- **What the AI produced:** the recommendation put to Zarif said the D-009 fallback "removes the `KNOWN_WRONG` xfail for 00005-303146", and the Gate 2 report and the hand-off prompt repeated it. Nothing had been run.
- **What was wrong:** the fallback makes the pair a `check`, so the content check now runs on it, and in the golden test's second run it confirms the wrong pair (92% of figures match, no rival listed, so a single candidate is conclusive). The xfail goes in the structural run and stays in the run with the content check.
- **How it was caught:** the full suite after the change: the with-content case of `00005-303146` failed.
- **Fix and commit:** the strict marker is kept for that run only, with the reason. The content-check weakness is open and is Zarif's decision (D-015).
- **Guard added:** the expected failure is keyed on (run, entry) and is strict, so it fails the day it is fixed.

### M-016: first version of the fallback keyed on resolved category codes

- **Date and tool:** 2026-10-31, Claude Code (Gate 2 follow-up).
- **What the AI produced:** `_can_match` returned false when neither document had category *codes*, and the new note said "Neither version has a headline category".
- **What was wrong:** the codes come from resolving the category text against the current category lists. Two 2014 Hutchison announcements with a retired category ("Share Option Scheme") have text but no code, so two correct `matched` pairs became `check` with a note that was false.
- **How it was caught:** the `delisted` replay count test (676 matched became 674); I then listed the two pairs.
- **Fix and commit:** the rule is keyed on category text and codes both being absent; the lower threshold stays for text without codes, with a unit test.
- **Guard added:** `test_a_category_text_the_directory_cannot_resolve_keeps_the_lower_threshold`; five mutants of the new rule and note were killed.

### M-017: stub evidence said more than the HKEXnews notice

- **Date and tool:** 2026-10-31, Claude Code (matcher evidence, Phase 2.2).
- **What the AI produced:** the evidence text "The issuer published this in English only. HKEXnews' Chinese section shows a notice instead." for a document with a stub in the other section (taken from the spec's wording).
- **What was wrong:** the notice says a Chinese version "may or may not" be published in that section. It does not say the issuer published in one language only.
- **How it was caught:** reading the notice titles while checking the golden entries (Phase 2.5); recorded in research notes, wording decided at Gate 2.
- **Fix and commit:** reworded to the search result plus what the notice says; SPEC §4.1 and §4.6 updated (D-015).
- **Guard added:** unit tests assert the exact evidence in both directions.

### M-018: first drafts of the Phase 3.1 tests were weaker than they looked

- **Date and tool:** 2026-10-31, Claude Code (tests for Title Case and filenames).
- **What the AI produced:** 196 tests that all passed on the first run against the new code. Among them: a header test whose regex could not see a stray quote; no test that a longer word before "shares" (`NEW SHARES`) is not kept upper case; no test that same-minute files are ordered by file number as a number (3 and 4 digit numbers in 2015 paths); a property with a vacuous `or True`; two hand-written expectations that were wrong ("AND SO ON" cannot give "And so On" when "on" is a small word, and an all-caps filler string that Title Case rightly changes). I also added an en and em dash as separators, which the SPEC does not ask for and no recorded title uses.
- **What was wrong:** green meant little. Several tests could not fail for the mistakes they were written for.
- **How it was caught:** mutation testing (20 mutants of `titlecase.py`, 36 of `filenames.py`, with `__pycache__` cleared between runs): 6 real survivors, plus 2 equivalent ones (the number suffix is pure ASCII, and a slug never starts with a hyphen). The `or True` on re-reading before the first run; the two wrong expectations on the first run.
- **Fix and commit:** tests added for each survivor; the cut property replaced by an independent statement of the SPEC rule; the dash extension removed.
- **Guard added:** every non-equivalent mutant is killed. The habit stays: mutate new rules before calling them done.

### M-019: the first fixture-mode server returned the wrong rows

- **Date and tool:** 2026-11-01, Claude Code (API, Phase 4.2).
- **What the AI produced:** a fixture transport that answered every search for a stock with the first recording found for it, whatever dates were asked for.
- **What was wrong:** the recordings for one stock cover different windows, so the Chinese side returned 33 rows from another window and every English document looked English only (10 of 10).
- **How it was caught:** the first API test (it expected confirmed pairs) failed; printing the search diagnostics showed 33 rows fetched and all outside the range.
- **Fix and commit:** the transport now merges all recorded rows for a stock and filters them by the requested dates, which is what the real servlet does. The same search then gives 17 of 17 matched.
- **Guard added:** API tests assert pairs, sorting, filenames and ZIP downloads against the fixtures.

### M-020: the suggestion list covered the date buttons

- **Date and tool:** 2026-11-01, Claude Code (frontend, Phase 5.2).
- **What the AI produced:** a stock search box whose suggestion list stayed open after the user moved on, and could be re-filled by a late reply. I also ran the formatter over the whole `scripts/` folder, which rewrote two older scripts that were not part of the task.
- **What was wrong:** the open list covered the date presets, so a real user could not click "Custom" (a Playwright run timed out); the formatter changes were unrelated to the work.
- **How it was caught:** the end-to-end test failed once, then passed on a re-run, which showed a timing problem; a screenshot confirmed the list was still open after the search. `git status` showed the two modified scripts.
- **Fix and commit:** the list is shown only while the box has focus and closes on Escape; the two scripts were restored.
- **Guard added:** the Playwright journeys click the date presets right after typing a code.

### M-00X: short title

- **Date and tool:**
- **What the AI proposed or produced:**
- **What was wrong:**
- **How it was caught (test, probe, review):**
- **Fix and commit:**
- **Guard added (test, rule in CLAUDE.md):**
