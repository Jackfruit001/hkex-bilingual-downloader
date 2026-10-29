# Getting started with Claude Code

This file is for you, not the repo. Keep it outside the project folder (or commit it under `docs/prompts/` if you want the prompts visible as process evidence).

## Before the first prompt (Mac, about 15 minutes)

1. Install tools if missing: `brew install uv node git` (Node 20 or newer). Docker Desktop is optional; Render builds the image for you.
2. Create a public GitHub repository named `hkex-bilingual-downloader` and clone it.
3. Copy `CLAUDE.md` into the repo root and the `docs/` folder alongside it. Commit with the message `docs: add brief, spec, plan and research notes`.
4. Open the folder in VS Code and start Claude Code. Use plan mode for the kickoff (Shift+Tab cycles modes).
5. You'll need a Render account for Phase 0.4 (sign in with GitHub). The free plan is enough for the reachability test; switch to Starter before sharing the link.

## Prompt 1: kickoff (paste as is)

```
You're helping me build my submission for Regevio's practical assessment. Before doing anything else, read CLAUDE.md, docs/SPEC.md, docs/PLAN.md, docs/research-notes.md, docs/DECISIONS.md and docs/AI_LOG.md in full.

Then, without writing any code:

1. Summarise your understanding in at most 15 bullet points: the deliverables, the central requirement, the invariants you must never break, and how phases and gates work.
2. List anything in the docs that is ambiguous, contradictory or risky, or that you would do differently, with your reasoning. Don't edit the docs yet.
3. Propose a concrete plan for Phase 0 only: the files you'll create, the probe script's structure, how it stays polite to HKEXnews (request budget and pacing), which of Q1 to Q12 each scenario answers, and exactly what you need from me (for example the Render setup).

Then stop and wait for my approval.
```

## Prompts for later

At each gate, after you've reviewed the report:

```
Gate N approved [with these changes: ...]. Update docs/PLAN.md, then propose your plan for Phase N+1 and wait for my approval.
```

When you catch a mistake:

```
That's wrong: [what you saw]. Fix it, add a test that would have caught it, and add an entry to docs/AI_LOG.md.
```

Before ending a session:

```
Update docs/PLAN.md with progress and next steps, make sure all tests pass, and commit.
```

If a session runs long and Claude Code starts drifting from the docs:

```
Re-read CLAUDE.md and the current phase in docs/PLAN.md. Check your last changes against the invariants and tell me if anything breaks them.
```
