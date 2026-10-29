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

## Mistakes caught

### M-001: plan anchored to the wrong start day

- **Date and tool:** 2026-10-30, Claude chat.
- **What the AI produced:** a build timeline that treated the start day as Thursday 29 October.
- **What was wrong:** work started on Friday 30 October, so the plan assumed one more day than was available.
- **How it was caught:** re-planning against the deadline before the build started.
- **Fix:** timeline in `docs/PLAN.md` rebuilt for Friday to Monday.
- **Guard:** plans state explicit dates, checked against the actual date.

### Template

### M-00X: short title

- **Date and tool:**
- **What the AI proposed or produced:**
- **What was wrong:**
- **How it was caught (test, probe, review):**
- **Fix and commit:**
- **Guard added (test, rule in CLAUDE.md):**
