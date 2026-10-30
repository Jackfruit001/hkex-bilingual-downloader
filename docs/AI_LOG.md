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

### M-00X: short title

- **Date and tool:**
- **What the AI proposed or produced:**
- **What was wrong:**
- **How it was caught (test, probe, review):**
- **Fix and commit:**
- **Guard added (test, rule in CLAUDE.md):**
