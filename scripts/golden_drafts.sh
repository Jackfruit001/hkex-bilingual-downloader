#!/bin/bash
# How the first golden drafts were made (Phase 2.4, 31 October 2026): one `draft` run per issuer
# window, with the rows named so the run is repeatable. Entries already in pairs.yaml are never
# changed, so this is safe to re-run; it refreshes the figure fingerprints and prints each row.
#
#   scripts/golden_drafts.sh            live where the cache is empty (about 60 search responses, 125 PDFs)
#   scripts/golden_drafts.sh --offline  cache only; no requests at all
#
# Live runs are one request at a time, at least a second apart, and stop at the first refusal.
set -euo pipefail
cd "$(dirname "$0")/.."

draft() {
  echo "=== $*"
  uv run --project backend python scripts/golden_helper.py draft "$@"
}

EXTRA=("$@")

# Zai Lab: the known pair day, and the Form 8-K day (English only, Chinese notice)
draft 09688 2026-10-28 2026-10-28 --pick 1,2 ${EXTRA[@]+"${EXTRA[@]}"}
draft 09688 2026-10-23 2026-10-23 --pick 1,2,3,4 ${EXTRA[@]+"${EXTRA[@]}"}

# Large caps, October 2026: ordinary pairs, English-only and Chinese-only rows with notices
for run in "00700:1,2,8" "01810:3,8" "09988:1,2" "03690:1,2" "00939:1,5" "01398:1,3,7" \
           "02318:2,5" "00388:2,3,4,5" "00941:1,3" "01299:1,3"; do
  draft "${run%%:*}" 2026-10-01 2026-10-30 --pick "${run##*:}" --max-mb 10 ${EXTRA[@]+"${EXTRA[@]}"}
done

# HSBC results day: several pairs in the same minute
draft 00005 2026-07-25 2026-08-05 --pick 8,9,10,12,13,14,15 --max-mb 10 ${EXTRA[@]+"${EXTRA[@]}"}
# HSBC 2005: no categories, no notices, multi-file entries, "_c" numbering
draft 00005 2005-03-31 2005-04-07 --pick 1,2,6,8,9,10,11,12,13,14 --max-mb 10 ${EXTRA[@]+"${EXTRA[@]}"}
# HSBC March 2024: a cancelled submission
draft 00005 2024-03-13 2024-03-15 --pick 4,5,6 --max-mb 10 ${EXTRA[@]+"${EXTRA[@]}"}
# Hutchison (delisted; code 00013 is also Hutchmed): block layouts, revised and cancelled rows
draft 00013 2015-01-14 2015-01-27 --stock-id 20 --pick 1,2,3,4,75,77,76,79,78,148,170,171 \
  --max-mb 10 ${EXTRA[@]+"${EXTRA[@]}"}

# Small caps in annual-report season
for run in "02372:4" "01292:4" "06909:4,5" "03718:8" "02658:6"; do
  draft "${run%%:*}" 2026-03-15 2026-04-30 --pick "${run##*:}" --max-mb 8 ${EXTRA[@]+"${EXTRA[@]}"}
done

# GEM issuers (08xxx; files under /gem/, which the parser accepted from 31 October)
for run in "08223:3,5,8,10,13" "08293:3,7" "08069:4,9"; do
  draft "${run%%:*}" 2026-03-15 2026-04-30 --pick "${run##*:}" --max-mb 8 ${EXTRA[@]+"${EXTRA[@]}"}
done

uv run --project backend python scripts/golden_helper.py coverage
