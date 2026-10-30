"""Pairing signals S1 to S4 and S6 (SPEC §4.2) and hard conflicts (§4.3). Pure functions.

S5 (identical bytes) and S7 (content check) need the files and are applied by the matcher
from `ContentEvidence`.
"""

import re
from collections.abc import Iterable
from datetime import date

from app.config import PAIRING, PairingConfig
from app.domain.models import Document
from app.hkex.parse import has_chinese_suffix
from app.pairing.models import SignalHit

_FULL_WIDTH_DIGITS = {0xFF10 + i: str(i) for i in range(10)}  # U+FF10..U+FF19
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def numbering_uses_same_number(
    folders: dict[date, list[Document]], cfg: PairingConfig = PAIRING
) -> dict[date, bool]:
    """Which date folders number a Chinese file with the English number plus `_c` (2005).

    HKEX files in 2014 onwards share one counter across languages, so an English and a Chinese
    file in the same folder never share a number, even when the Chinese file ends in `_c`.
    A folder where a `_c` file does share its number with an English file is numbered the old
    way (research notes Q6). Folders before `cfg.same_number_before` are assumed old-style.
    """
    result: dict[date, bool] = {}
    for day, docs in folders.items():
        english = {d.seq for d in docs if d.lang.value == "en" and d.seq is not None}
        detected = any(
            d.lang.value == "tc" and d.seq in english and has_chinese_suffix(d.path) for d in docs
        )
        result[day] = detected or day < cfg.same_number_before
    return result


def minutes_apart(en: Document, tc: Document) -> int:
    return round(abs((en.release_at - tc.release_at).total_seconds()) / 60)


def time_signal(en: Document, tc: Document, cfg: PairingConfig = PAIRING) -> SignalHit:
    """S1: same release minute +3; within 5 minutes +1."""
    gap = minutes_apart(en, tc)
    if gap == 0:
        return SignalHit(id="S1", points=cfg.same_minute, kind="same_minute")
    if gap <= cfg.within_minutes:
        return SignalHit(id="S1", points=cfg.near_minutes_points, kind="close", values=(str(gap),))
    return SignalHit(id="S1", points=0, kind="apart", values=(str(gap),))


def category_signal(en: Document, tc: Document, cfg: PairingConfig = PAIRING) -> SignalHit:
    """S2: identical headline category codes +3, overlapping +1, disjoint -4."""
    a, b = set(en.category_codes), set(tc.category_codes)
    if not a or not b:
        return SignalHit(id="S2", points=0, kind="unavailable")
    if a == b:
        return SignalHit(id="S2", points=cfg.categories_identical, kind="identical")
    if a & b:
        return SignalHit(id="S2", points=cfg.categories_overlap, kind="overlap")
    return SignalHit(id="S2", points=cfg.categories_disjoint, kind="disjoint")


def file_relation(
    en: Document, tc: Document, *, same_number_numbering: bool, cfg: PairingConfig = PAIRING
) -> str | None:
    """How the two file numbers relate: `plus_one`, `same_number_c`, `near` or None.

    Where the Chinese file reuses the English number (2005), numbers are unique within a
    language, so only an exact match says anything; a nearby number is no evidence at all.
    """
    if (
        en.folder_date is None
        or tc.folder_date is None
        or en.folder_date != tc.folder_date
        or en.seq is None
        or tc.seq is None
    ):
        return None
    gap = tc.seq - en.seq
    if same_number_numbering:
        return "same_number_c" if gap == 0 and has_chinese_suffix(tc.path) else None
    if gap == 1:
        return "plus_one"
    return "near" if abs(gap) <= cfg.file_near_window else None


def sequence_signal(
    en: Document,
    tc: Document,
    *,
    same_number_numbering: bool,
    neutral: bool = False,
    cfg: PairingConfig = PAIRING,
) -> SignalHit:
    """S3: the Chinese file number relates to the English one in this folder's numbering scheme.

    `neutral` scores every candidate in a non-interleaved same-minute group at the proximity
    level, so adjacency does not favour one pair (D-011).
    """
    relation = file_relation(en, tc, same_number_numbering=same_number_numbering, cfg=cfg)
    values = (str(en.seq), str(tc.seq))
    if relation is None:
        return SignalHit(id="S3", points=0, kind="none")
    if neutral:
        return SignalHit(id="S3", points=cfg.file_near, kind="proximity", values=values)
    if relation == "near":
        return SignalHit(id="S3", points=cfg.file_near, kind="near", values=values)
    return SignalHit(id="S3", points=cfg.file_exact, kind=relation, values=values)


def news_id_signal(en: Document, tc: Document, cfg: PairingConfig = PAIRING) -> SignalHit | None:
    """S4: the Chinese NEWS_ID is the English one plus 1. Weak; not shared across languages."""
    try:
        follows = int(tc.news_id) == int(en.news_id) + 1
    except ValueError:
        return None
    if not follows:
        return None
    return SignalHit(id="S4", points=cfg.news_id_next, kind="next")


def title_numbers(title: str, cfg: PairingConfig = PAIRING) -> frozenset[str]:
    """Long numbers in a title (years, amounts), with commas removed and full-width folded."""
    found = _NUMBER.findall(title.translate(_FULL_WIDTH_DIGITS))
    numbers = (n.replace(",", "") for n in found)
    return frozenset(
        n for n in numbers if sum(c.isdigit() for c in n) >= cfg.title_number_min_digits
    )


def title_number_signal(
    en: Document, tc: Document, cfg: PairingConfig = PAIRING
) -> SignalHit | None:
    """S6: long numbers in both titles agree +1 (one set holds the other) or are disjoint -2."""
    a, b = title_numbers(en.title, cfg), title_numbers(tc.title, cfg)
    if not a or not b:
        return None
    if not a & b:
        return SignalHit(id="S6", points=cfg.title_numbers_conflict, kind="conflict")
    if a <= b or b <= a:
        return SignalHit(
            id="S6", points=cfg.title_numbers_agree, kind="agree", values=tuple(sorted(a & b))
        )
    return None


def hard_conflicts(en: Document, tc: Document, hits: Iterable[SignalHit]) -> tuple[str, ...]:
    """Reasons a pair can never be `matched` (SPEC §4.3 step 4)."""
    kinds = {(h.id, h.kind) for h in hits}
    found: list[str] = []
    if ("S2", "disjoint") in kinds:
        found.append("categories_disjoint")
    if ("S6", "conflict") in kinds:
        found.append("title_numbers")
    if en.flags != tc.flags:
        found.append("flags_differ")
    return tuple(found)
