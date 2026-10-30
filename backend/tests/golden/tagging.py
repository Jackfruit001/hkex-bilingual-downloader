"""Case types, stratified sampling and coverage for the golden set (SPEC §10.4). Pure."""

import random
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date

from app.config import PAIRING, PairingConfig
from app.domain.timeutil import HKT
from app.pairing.models import Announcement, Format, SingleReason, Status
from tests.golden.schema import REQUIRED_CASE_TYPES, CaseType, Entry

PRE_2007_BEFORE = date(2007, 1, 1)
MIN_ENTRIES = 50
MIN_ISSUERS = 12
# Required case types that real data did not supply. Zarif accepted these as README limitations
# (31 October 2026); they stop counting as gaps, but are always listed so they stay visible.
ACCEPTED_GAPS: dict[CaseType, str] = {
    CaseType.SEPARATE_ANNUAL_REPORT: (
        "no separately published annual report was found on HKEXnews in 13 issuers' annual-report "
        "seasons; the rule is tested with synthetic documents only (README limitation)"
    ),
}
_ORDER = {case: i for i, case in enumerate(CaseType)}


def _special(a: Announcement, stock_active: bool, cfg: PairingConfig) -> set[CaseType]:
    docs = [d for d in (a.en, a.tc) if d is not None]
    found: set[CaseType] = set()
    if not stock_active:
        found.add(CaseType.DELISTED)
    if a.release_at.astimezone(HKT).date() < PRE_2007_BEFORE:
        found.add(CaseType.PRE_2007)
    if a.status in (Status.EN_ONLY, Status.TC_ONLY):
        if a.reason is SingleReason.STUB_IN_OTHER_SECTION:
            found.add(
                CaseType.EN_ONLY_STUB if a.status is Status.EN_ONLY else CaseType.TC_ONLY_STUB
            )
        else:
            found.add(CaseType.SINGLE_NOT_FOUND)
    if a.separate:
        annual = any(c in cfg.separate_codes for d in docs for c in d.category_codes)
        found.add(CaseType.SEPARATE_ANNUAL_REPORT if annual else CaseType.SEPARATE_OTHER)
    if a.bilingual:
        found.add(CaseType.BILINGUAL_IDENTICAL)
    if any(d.flags or d.category_prefix for d in docs):
        found.add(CaseType.REVISED_OR_CANCELLED)
    if a.format is Format.MULTI_FILE:
        found.add(CaseType.MULTI_FILE)
    if a.format is Format.WEB_PAGE:
        found.add(CaseType.WEB_PAGE)
    if a.layout_ambiguous:
        found.add(CaseType.BLOCK_LAYOUT)
    return found


def tag_announcements(
    announcements: Sequence[Announcement],
    *,
    stock_active: bool,
    cfg: PairingConfig = PAIRING,
) -> dict[str, tuple[CaseType, ...]]:
    """The case types of each announcement, in a fixed order, keyed by announcement id."""
    per_day = Counter(a.release_at.astimezone(HKT).date() for a in announcements)
    per_minute = Counter(
        a.release_at.astimezone(HKT).replace(second=0, microsecond=0) for a in announcements
    )
    tagged: dict[str, tuple[CaseType, ...]] = {}
    for a in announcements:
        types = _special(a, stock_active, cfg)
        if a.status in (Status.MATCHED, Status.CHECK) and not types:
            types.add(CaseType.ORDINARY)
        if per_day[a.release_at.astimezone(HKT).date()] > 1:
            types.add(CaseType.SEVERAL_SAME_DAY)
        if per_minute[a.release_at.astimezone(HKT).replace(second=0, microsecond=0)] > 1:
            types.add(CaseType.SEVERAL_SAME_MINUTE)
        tagged[a.id] = tuple(sorted(types, key=_ORDER.__getitem__))
    return tagged


# --- sampling ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class Candidate:
    id: str
    strata: frozenset[str]  # case types and "status:<status>"
    busy: bool  # several announcements the same day: where wrong pairs are most likely


def stratified_sample(candidates: Iterable[Candidate], n: int, seed: int) -> list[str]:
    """Cover every stratum once, rarest first, then fill at random, preferring busy days.

    A sample of only the easy cases could never expose a wrong `matched`. The input order does
    not matter and the same seed gives the same sample.
    """
    pool = sorted(candidates, key=lambda c: c.id)
    rng = random.Random(seed)
    chosen: list[Candidate] = []

    def pick(options: list[Candidate]) -> Candidate:
        busy = [c for c in options if c.busy]
        return rng.choice(busy or options)

    counts = Counter(s for c in pool for s in c.strata)
    for stratum in sorted(counts, key=lambda s: (counts[s], s)):
        if len(chosen) >= n:
            break
        if any(stratum in c.strata for c in chosen):
            continue
        chosen.append(pick([c for c in pool if stratum in c.strata and c not in chosen]))
    while len(chosen) < min(n, len(pool)):
        chosen.append(pick([c for c in pool if c not in chosen]))
    return [c.id for c in chosen]


# --- coverage ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class Coverage:
    entries: int
    verified: int
    issuers_all: int
    issuers_verified: int
    by_case: dict[CaseType, tuple[int, int]]  # (verified, all)
    gaps: tuple[str, ...]
    accepted: tuple[str, ...] = ()  # accepted gaps still without a verified entry


def coverage(entries: Sequence[Entry]) -> Coverage:
    """How the golden set stands against SPEC §10.4. Only verified entries close a gap."""
    verified = [e for e in entries if e.verified]
    by_case = {
        case: (
            sum(case in e.case_types for e in verified),
            sum(case in e.case_types for e in entries),
        )
        for case in CaseType
    }
    issuers_verified = len({e.stock_id for e in verified})
    gaps: list[str] = []
    if len(verified) < MIN_ENTRIES:
        gaps.append(f"{len(verified)} verified entries; at least {MIN_ENTRIES} are needed")
    if issuers_verified < MIN_ISSUERS:
        gaps.append(f"{issuers_verified} verified issuers; at least {MIN_ISSUERS} are needed")
    missing = [case for case in REQUIRED_CASE_TYPES if by_case[case][0] == 0]
    gaps.extend(
        f"no verified entry for case type {case.value}"
        for case in missing
        if case not in ACCEPTED_GAPS
    )
    accepted = tuple(
        f"{case.value}: {ACCEPTED_GAPS[case]}" for case in missing if case in ACCEPTED_GAPS
    )
    return Coverage(
        entries=len(entries),
        verified=len(verified),
        issuers_all=len({e.stock_id for e in entries}),
        issuers_verified=issuers_verified,
        by_case=by_case,
        gaps=tuple(gaps),
        accepted=accepted,
    )
