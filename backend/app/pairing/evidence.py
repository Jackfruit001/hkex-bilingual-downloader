"""Readable evidence for each announcement (SPEC §4.6). Pure string building, no scoring."""

from datetime import date

from app.domain.models import Document, Lang
from app.pairing.models import ContentVerdict, Rival, SignalHit, SingleReason

_LANG_NAME = {Lang.EN: "English", Lang.TC: "Chinese"}
_A_LANG_NAME = {Lang.EN: "an English", Lang.TC: "a Chinese"}

CHECK_NOTE = "Best guess shown; compare before relying on it."
NO_CATEGORY_NOTE = (
    "Neither version has a headline category, so time and file numbers can't confirm the pair "
    "on their own."
)


def hkt_date(value: date) -> str:
    return f"{value.day} {value:%b} {value.year}"


def _hits(signals: tuple[SignalHit, ...]) -> dict[str, SignalHit]:
    return {s.id: s for s in signals}


def _file(number: str) -> str:
    return f"{int(number):05d}"


def _minutes(count: str) -> str:
    return "1 minute" if count == "1" else f"{count} minutes"


def _describe(en: Document, tc: Document, signals: tuple[SignalHit, ...]) -> str:
    hits = _hits(signals)
    parts: list[str] = []
    s1 = hits.get("S1")
    if s1 is not None:
        if s1.kind == "same_minute":
            parts.append(f"Published together at {en.release_at:%H:%M} HKT")
        else:
            gap = _minutes(s1.values[0])
            parts.append(
                f"Published {gap} apart ({en.release_at:%H:%M} and {tc.release_at:%H:%M} HKT)"
            )
    s2 = hits.get("S2")
    if s2 is not None:
        parts.append(
            {
                "identical": "same headline category",
                "overlap": "overlapping headline categories",
                "disjoint": "different headline categories",
                "unavailable": "no headline category to compare",
            }[s2.kind]
        )
    s3 = hits.get("S3")
    if s3 is not None and s3.kind != "none":
        a, b = _file(s3.values[0]), _file(s3.values[1])
        parts.append(
            {
                "plus_one": f"consecutive HKEX file numbers ({a} and {b})",
                "same_number_c": f"the same HKEX file number ({a}) with the Chinese file marked _c",
                "near": f"nearby HKEX file numbers ({a} and {b})",
                "proximity": f"nearby HKEX file numbers ({a} and {b})",
            }[s3.kind]
        )
    elif s3 is not None:
        parts.append("file numbers not close")
    s6 = hits.get("S6")
    if s6 is not None and s6.kind == "agree":
        parts.append("the same numbers appear in both titles")
    return ", ".join(parts) + "."


_CONFLICT_TEXT = {
    "categories_disjoint": "The headline categories differ.",
    "title_numbers": "The numbers in the titles disagree.",
    "flags_differ": "One version is marked revised or cancelled and the other is not.",
}


def pair_evidence(
    en: Document,
    tc: Document,
    signals: tuple[SignalHit, ...],
    *,
    matched: bool,
    conflicts: tuple[str, ...],
    bilingual: bool,
    separate: bool,
    uncategorised: bool,
    verdict: ContentVerdict | None,
    layout_counts: tuple[int, int] | None,
    rivals: tuple[Rival, ...],
    mixed_formats: tuple[str, str] | None,
) -> tuple[str, ...]:
    lines: list[str] = []
    if bilingual:
        lines.append(
            "Bilingual document: the English and Chinese sections link the identical file."
        )
    elif separate:
        lines.append(f"Chinese version published separately on {hkt_date(tc.release_at.date())}.")
    else:
        lines.append(_describe(en, tc, signals))
    lines.extend(_CONFLICT_TEXT[c] for c in conflicts)
    if uncategorised:
        lines.append(NO_CATEGORY_NOTE)
    if verdict is not None:
        lines.append(f"Content check: {round(verdict.score * 100)}% of figures match.")
    if layout_counts is not None:
        n_en, n_tc = layout_counts
        lines.append(
            f"{n_en} English and {n_tc} Chinese documents were published at "
            f"{en.release_at:%H:%M}; file order cannot show which Chinese file belongs to which "
            "English file."
        )
    if mixed_formats is not None:
        lines.append(
            f"The two versions have different formats ({mixed_formats[0]} and {mixed_formats[1]})."
        )
    if not matched:
        lines.append(CHECK_NOTE)
    if rivals:
        listed = ", ".join(f"{_LANG_NAME[r.document.lang]} file {_seq(r.document)}" for r in rivals)
        lines.append(f"Other possible matches: {listed}.")
    return tuple(lines)


def _seq(doc: Document) -> str:
    return f"{doc.seq:05d}" if doc.seq is not None else doc.news_id


def single_evidence(
    doc: Document,
    reason: SingleReason,
    *,
    searched: tuple[date, date] | None,
    lost_to: Document | None,
) -> tuple[str, ...]:
    other_lang = Lang.TC if doc.lang is Lang.EN else Lang.EN
    other = _LANG_NAME[other_lang]
    if searched is None:
        lines = [f"No {other} version found in the search results."]
    else:
        lines = [
            f"No {other} version found between {hkt_date(searched[0])} and {hkt_date(searched[1])}."
        ]
    if reason is SingleReason.STUB_IN_OTHER_SECTION:
        # The notice says a version "may or may not" be published there; it never says "only".
        lines.append(
            f"HKEXnews' {other} section shows a notice instead, saying {_A_LANG_NAME[other_lang]} "
            "version may or may not be published there."
        )
        return tuple(lines)
    if lost_to is not None:
        lines.append(
            f"A possible counterpart ({_LANG_NAME[lost_to.lang]} file {_seq(lost_to)}) is shown "
            "with another entry."
        )
    return tuple(lines)
