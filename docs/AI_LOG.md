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

### Template

### M-00X: short title

- **Date and tool:**
- **What the AI proposed or produced:**
- **What was wrong:**
- **How it was caught (test, probe, review):**
- **Fix and commit:**
- **Guard added (test, rule in CLAUDE.md):**
