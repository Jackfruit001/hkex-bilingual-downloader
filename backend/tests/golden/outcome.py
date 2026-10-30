"""Judging the matcher against the golden set (SPEC §10.4, Phase 2.6). Pure: no I/O, no clock.

`truth` is the only input taken from an entry. `proposal` is what the matcher said when the entry
was drafted; it is ignored here so a stale proposal can neither excuse nor accuse anything.

The one failure that matters is `MATCHED_WRONG`: a pair shown as confirmed that the golden set
does not support. Everything else is visible to a user as "check" or as a single-language entry.
"""

import textwrap
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from app.domain.models import Document, Lang
from app.pairing.content_check import best_match
from app.pairing.models import (
    Announcement,
    ContentEvidence,
    ContentVerdict,
    PairingResult,
    SingleReason,
    Status,
)
from tests.golden.draft import sha256_by_document
from tests.golden.schema import CaseType, DocRef, Entry
from tests.golden.store import FileFacts


class Outcome(StrEnum):
    MATCHED_RIGHT = "matched_right"
    MATCHED_WRONG = "matched_wrong"  # the failure the golden test exists to catch
    CHECK_RIGHT = "check_right"
    CHECK_WRONG = "check_wrong"  # visible: shown for checking with another partner
    CHECK_NO_COUNTERPART = "check_no_counterpart"  # truth: no counterpart; matcher offers one
    HELD_APART = "held_apart"  # a real pair shown as two single-language entries
    SINGLE_RIGHT = "single_right"
    SINGLE_REASON_DIFFERS = "single_reason_differs"
    MISSING = "missing"  # the search did not return a document of the entry: a golden set fault


@dataclass(frozen=True)
class Judgement:
    entry_id: str
    outcome: Outcome
    pair: bool  # the golden set says both versions exist
    case_types: tuple[CaseType, ...]
    status: str  # what the matcher showed for the entry's first document
    detail: str  # one sentence on how the matcher and the golden set differ, or agree
    evidence: tuple[str, ...]  # the matcher's own evidence text, as a user would see it


# --- judging ----------------------------------------------------------------------------------


def _find(announcements: Sequence[Announcement], lang: Lang, news_id: str) -> Announcement | None:
    """The announcement showing a document as a version. A stub notice is never a version."""
    for a in announcements:
        doc = a.en if lang is Lang.EN else a.tc
        if doc is not None and doc.news_id == news_id:
            return a
    return None


def _judgement(
    entry: Entry, outcome: Outcome, detail: str, *shown: Announcement | None
) -> Judgement:
    rows = list(dict.fromkeys(a for a in shown if a is not None))
    evidence = tuple(line for a in rows for line in a.evidence)
    return Judgement(
        entry.id,
        outcome,
        entry.truth.en is not None and entry.truth.tc is not None,
        tuple(entry.case_types),
        rows[0].status.value if rows else "-",
        detail,
        evidence,
    )


def _judge_pair(
    entry: Entry, en: DocRef, tc: DocRef, announcements: Sequence[Announcement]
) -> Judgement:
    a = _find(announcements, Lang.EN, en.news_id)
    b = _find(announcements, Lang.TC, tc.news_id)
    absent = [
        f"{label} {ref.news_id}"
        for label, ref, found in (("English", en, a), ("Chinese", tc, b))
        if found is None
    ]
    if a is None or b is None:
        return _judgement(
            entry, Outcome.MISSING, "not in the search result: " + " and ".join(absent), a, b
        )
    if a is b:
        outcome = Outcome.MATCHED_RIGHT if a.status is Status.MATCHED else Outcome.CHECK_RIGHT
        return _judgement(entry, outcome, f"English {en.news_id} with Chinese {tc.news_id}", a)
    reasons = []
    if a.status is Status.MATCHED and a.tc is not None:
        reasons.append(
            f"English {en.news_id} is confirmed with Chinese {a.tc.news_id}, not {tc.news_id}"
        )
    if b.status is Status.MATCHED and b.en is not None:
        reasons.append(
            f"Chinese {tc.news_id} is confirmed with English {b.en.news_id}, not {en.news_id}"
        )
    if reasons:
        return _judgement(entry, Outcome.MATCHED_WRONG, "; ".join(reasons), a, b)
    if Status.CHECK in (a.status, b.status):
        return _judgement(
            entry,
            Outcome.CHECK_WRONG,
            f"English {en.news_id} and Chinese {tc.news_id} belong together, but a different "
            "partner is offered for checking",
            a,
            b,
        )
    return _judgement(
        entry,
        Outcome.HELD_APART,
        f"English {en.news_id} and Chinese {tc.news_id} belong together but are shown apart",
        a,
        b,
    )


_REASON = {"stub": SingleReason.STUB_IN_OTHER_SECTION, "not_found": SingleReason.NOT_FOUND}


def _judge_single(entry: Entry, announcements: Sequence[Announcement]) -> Judgement:
    truth = entry.truth
    lang, ref = (Lang.EN, truth.en) if truth.en is not None else (Lang.TC, truth.tc)
    assert ref is not None and truth.absent is not None
    side = "English" if lang is Lang.EN else "Chinese"
    other = "Chinese" if lang is Lang.EN else "English"
    a = _find(announcements, lang, ref.news_id)
    if a is None:
        return _judgement(entry, Outcome.MISSING, f"not in the search result: {side} {ref.news_id}")
    partner: Document | None = a.tc if lang is Lang.EN else a.en
    if partner is not None:
        said = f"{side} {ref.news_id} with {other} {partner.news_id}"
        if a.status is Status.MATCHED:
            return _judgement(
                entry,
                Outcome.MATCHED_WRONG,
                f"{said} is confirmed, but the golden set says it has no {other} version",
                a,
            )
        return _judgement(
            entry,
            Outcome.CHECK_NO_COUNTERPART,
            f"{said} is offered for checking, but the golden set says it has no {other} version",
            a,
        )
    if a.reason is _REASON[truth.absent]:
        return _judgement(entry, Outcome.SINGLE_RIGHT, f"{side} only, {truth.absent}", a)
    said = a.reason.value if a.reason else "no reason"
    return _judgement(
        entry,
        Outcome.SINGLE_REASON_DIFFERS,
        f"the matcher says {said}; the golden set says {truth.absent}",
        a,
    )


def judge(entry: Entry, announcements: Sequence[Announcement]) -> Judgement:
    truth = entry.truth
    if truth.en is not None and truth.tc is not None:
        return _judge_pair(entry, truth.en, truth.tc, announcements)
    return _judge_single(entry, announcements)


def judge_all(
    entries: Sequence[Entry], results: Mapping[str, Sequence[Announcement]]
) -> list[Judgement]:
    """Each entry against the announcements of its own scenario."""
    return [judge(e, results[e.scenario]) for e in entries]


# --- the report -------------------------------------------------------------------------------


@dataclass(frozen=True)
class Report:
    judgements: tuple[Judgement, ...]

    def of(self, *outcomes: Outcome) -> list[Judgement]:
        return [j for j in self.judgements if j.outcome in outcomes]

    @property
    def wrong_matched(self) -> list[Judgement]:
        return self.of(Outcome.MATCHED_WRONG)

    @property
    def missing(self) -> list[Judgement]:
        return self.of(Outcome.MISSING)

    @property
    def precision(self) -> float | None:
        """Of the entries shown as confirmed, the share the golden set supports."""
        right = len(self.of(Outcome.MATCHED_RIGHT))
        shown = right + len(self.wrong_matched)
        return right / shown if shown else None

    @property
    def pairs(self) -> int:
        return sum(j.pair for j in self.judgements)

    @property
    def pairs_confirmed(self) -> int:
        return len(self.of(Outcome.MATCHED_RIGHT))

    @property
    def pairs_offered(self) -> int:
        return len(self.of(Outcome.CHECK_RIGHT))


# --- the printed table ------------------------------------------------------------------------

_ROWS: tuple[tuple[Outcome, str], ...] = (
    (Outcome.MATCHED_RIGHT, "Confirmed, right pair"),
    (Outcome.MATCHED_WRONG, "Confirmed, WRONG"),
    (Outcome.CHECK_RIGHT, "For checking, right partner"),
    (Outcome.CHECK_WRONG, "For checking, wrong partner"),
    (Outcome.CHECK_NO_COUNTERPART, "For checking, none exists"),
    (Outcome.HELD_APART, "Pair shown apart"),
    (Outcome.SINGLE_RIGHT, "Single, right reason"),
    (Outcome.SINGLE_REASON_DIFFERS, "Single, other reason"),
    (Outcome.MISSING, "Not in the search result"),
)
_LABEL = dict(_ROWS)
_GROUPS: tuple[tuple[str, tuple[Outcome, ...]], ...] = (
    ("confirmed", (Outcome.MATCHED_RIGHT,)),
    ("WRONG", (Outcome.MATCHED_WRONG,)),
    ("check", (Outcome.CHECK_RIGHT, Outcome.CHECK_WRONG, Outcome.CHECK_NO_COUNTERPART)),
    ("apart", (Outcome.HELD_APART,)),
    ("single", (Outcome.SINGLE_RIGHT, Outcome.SINGLE_REASON_DIFFERS)),
    ("missing", (Outcome.MISSING,)),
)
_WIDTH = 110


def _percent(report: Report) -> str:
    p = report.precision
    if p is None:
        return "nothing was confirmed"
    right = len(report.of(Outcome.MATCHED_RIGHT))
    return f"{p:.1%} ({right} of {right + len(report.wrong_matched)})"


def _outcome_table(runs: Mapping[str, Report]) -> list[str]:
    names = list(runs)
    widths = [max(len(n), 4) for n in names]
    head = "".join(f"  {n:>{w}}" for n, w in zip(names, widths, strict=True))
    lines = [f"{'Outcome':<28}{head}"]
    for outcome, label in _ROWS:
        cells = "".join(
            f"  {len(runs[n].of(outcome)):>{w}}" for n, w in zip(names, widths, strict=True)
        )
        lines.append(f"{label:<28}{cells}")
    for n, report in runs.items():
        lines.append(
            f"{n}: confirmed pairs are right {_percent(report)}; "
            f"pairs confirmed {report.pairs_confirmed}, offered for checking "
            f"{report.pairs_offered}, of {report.pairs}"
        )
    return lines


def _case_table(name: str, report: Report) -> list[str]:
    lines = [f"By case type, {name} (an entry counts under each of its case types):"]
    lines.append(f"{'case type':<24}{'entries':>8}" + "".join(f"{g:>10}" for g, _ in _GROUPS))
    for case in CaseType:
        mine = [j for j in report.judgements if case in j.case_types]
        if not mine:
            continue
        counts = Counter(j.outcome for j in mine)
        cells = "".join(f"{sum(counts[o] for o in os):>10}" for _, os in _GROUPS)
        lines.append(f"{case.value:<24}{len(mine):>8}{cells}")
    return lines


def _not_confirmed(runs: Mapping[str, Report]) -> list[str]:
    first = next(iter(runs.values()))
    by_run = {n: {j.entry_id: j for j in r.judgements} for n, r in runs.items()}
    lines: list[str] = []
    for j in first.judgements:
        seen = {n: by_run[n][j.entry_id] for n in runs if j.entry_id in by_run[n]}
        if all(x.outcome is Outcome.MATCHED_RIGHT for x in seen.values()):
            continue
        shown = "; ".join(f"{n}: {_LABEL[x.outcome]}" for n, x in seen.items())
        lines.append(f"{j.entry_id}  {shown}")
        worst = next((x for x in seen.values() if x.outcome is not Outcome.MATCHED_RIGHT), j)
        for text in (worst.detail, *worst.evidence):
            lines.extend(
                textwrap.wrap(text, _WIDTH, initial_indent="    ", subsequent_indent="      ")
            )
    return lines


def render(runs: Mapping[str, Report], *, issuers: int) -> str:
    """The metrics table: outcomes per run, per case type, and every entry not confirmed."""
    first = next(iter(runs.values()))
    out = [
        f"Golden set: {len(first.judgements)} verified entries from {issuers} issuers",
        "",
        *_outcome_table(runs),
    ]
    for name, report in runs.items():
        out += ["", *_case_table(name, report)]
    listing = _not_confirmed(runs)
    out += ["", "Entries not confirmed, with the matcher's reason:"]
    out += listing or ["Every entry was confirmed."]
    return "\n".join(out) + "\n"


# --- evidence from the files' facts -----------------------------------------------------------


def content_evidence(result: PairingResult, facts: Mapping[str, FileFacts]) -> ContentEvidence:
    """What downloading the files would add (SPEC §4.5), worked out from their recorded facts.

    Every known file's hash is passed on. Each pair offered for checking is compared with its own
    Chinese partner and the rivals the matcher listed. A pair whose own two documents have no
    readable figures gets no verdict, however readable a rival is; a rival without figures is left
    out of the comparison.
    """

    def figures(doc: Document) -> Mapping[str, int]:
        found = facts.get(f"{doc.lang.value}:{doc.news_id}")
        return found.tokens if found else {}

    verdicts: list[ContentVerdict] = []
    for a in result.announcements:
        if a.status is not Status.CHECK or a.en is None or a.tc is None:
            continue
        english, partner = figures(a.en), figures(a.tc)
        if not english or not partner:
            continue
        candidates = {a.tc.news_id: Counter(partner)}
        for rival in a.rivals:
            if rival.document.lang is Lang.TC and (theirs := figures(rival.document)):
                candidates[rival.document.news_id] = Counter(theirs)
        verdict = best_match(a.en.news_id, Counter(english), candidates)
        if verdict is not None:
            verdicts.append(verdict)
    return ContentEvidence(sha256=sha256_by_document(facts), verdicts=tuple(verdicts))
