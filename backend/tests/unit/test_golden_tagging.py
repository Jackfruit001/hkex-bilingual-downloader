"""Case types, stratified sampling and coverage for the golden set (SPEC §10.4)."""

from datetime import datetime

import pytest

from app.domain.models import Document, Flag, Lang
from app.domain.timeutil import HKT
from app.pairing.models import Announcement, Format, SingleReason, Status
from tests.golden.schema import REQUIRED_CASE_TYPES, CaseType, DocRef, Entry, Proposal, Truth
from tests.golden.tagging import (
    ACCEPTED_GAPS,
    Candidate,
    coverage,
    stratified_sample,
    tag_announcements,
)
from tests.support import make_doc

WHEN = datetime(2026, 10, 28, 22, 52, tzinfo=HKT)


def doc(lang: Lang, seq: int, when: datetime = WHEN, **kw: object) -> Document:
    return make_doc(lang, seq, when, news_id=seq, c_suffix=lang is Lang.TC, **kw)  # type: ignore[arg-type]


def pair(
    seq: int,
    when: datetime = WHEN,
    *,
    status: Status = Status.MATCHED,
    en_kw: dict[str, object] | None = None,
    tc_kw: dict[str, object] | None = None,
    **fields: object,
) -> Announcement:
    return Announcement(
        id=f"a{seq}",
        status=status,
        release_at=when,
        en=doc(Lang.EN, seq, when, **(en_kw or {})),
        tc=doc(Lang.TC, seq + 1, when, **(tc_kw or {})),
        **fields,  # type: ignore[arg-type]
    )


def tags(*announcements: Announcement, active: bool = True) -> dict[str, tuple[CaseType, ...]]:
    return tag_announcements(announcements, stock_active=active)


def at(minute: int, hour: int = 22, day: int = 28) -> datetime:
    return datetime(2026, 10, day, hour, minute, tzinfo=HKT)


def test_a_lone_matched_pair_is_ordinary() -> None:
    assert tags(pair(100))["a100"] == (CaseType.ORDINARY,)


def test_a_check_pair_is_also_ordinary() -> None:
    assert tags(pair(100, status=Status.CHECK))["a100"] == (CaseType.ORDINARY,)


def test_several_announcements_on_one_day_are_tagged() -> None:
    result = tags(pair(100, at(10)), pair(200, at(40)))
    assert result["a100"] == (CaseType.ORDINARY, CaseType.SEVERAL_SAME_DAY)
    assert result["a200"] == (CaseType.ORDINARY, CaseType.SEVERAL_SAME_DAY)


def test_the_same_minute_implies_the_same_day() -> None:
    result = tags(pair(100, at(10)), pair(200, at(10)))
    assert result["a100"] == (
        CaseType.ORDINARY,
        CaseType.SEVERAL_SAME_DAY,
        CaseType.SEVERAL_SAME_MINUTE,
    )


def test_announcements_on_different_days_are_not_several_on_one_day() -> None:
    result = tags(pair(100, at(10, day=27)), pair(200, at(10, day=28)))
    assert result["a100"] == (CaseType.ORDINARY,)


def test_the_same_clock_time_on_different_days_is_not_the_same_minute() -> None:
    result = tags(pair(100, at(10, day=27)), pair(200, at(10, day=28)))
    assert CaseType.SEVERAL_SAME_MINUTE not in result["a100"]


def test_english_only_with_a_stub() -> None:
    a = Announcement(
        id="e",
        status=Status.EN_ONLY,
        release_at=WHEN,
        en=doc(Lang.EN, 10),
        reason=SingleReason.STUB_IN_OTHER_SECTION,
        stub=doc(Lang.TC, 11, stub=True),
    )
    assert tags(a)["e"] == (CaseType.EN_ONLY_STUB,)


def test_chinese_only_with_a_stub() -> None:
    a = Announcement(
        id="t",
        status=Status.TC_ONLY,
        release_at=WHEN,
        tc=doc(Lang.TC, 11),
        reason=SingleReason.STUB_IN_OTHER_SECTION,
        stub=doc(Lang.EN, 10, stub=True),
    )
    assert tags(a)["t"] == (CaseType.TC_ONLY_STUB,)


def test_a_single_language_entry_with_no_counterpart_is_not_found() -> None:
    a = Announcement(
        id="n",
        status=Status.EN_ONLY,
        release_at=WHEN,
        en=doc(Lang.EN, 10),
        reason=SingleReason.NOT_FOUND,
    )
    assert tags(a)["n"] == (CaseType.SINGLE_NOT_FOUND,)


def test_a_separately_published_annual_report() -> None:
    a = pair(
        100,
        separate=True,
        en_kw={"categories": ("40100",)},
        tc_kw={"categories": ("40100",)},
        status=Status.CHECK,
    )
    assert tags(a)["a100"] == (CaseType.SEPARATE_ANNUAL_REPORT,)


def test_another_separate_submission_is_not_an_annual_report() -> None:
    a = pair(100, separate=True, en_kw={"categories": ("30100",)}, tc_kw={"categories": ("30100",)})
    assert tags(a)["a100"] == (CaseType.SEPARATE_OTHER,)


def test_a_bilingual_identical_file() -> None:
    assert tags(pair(100, bilingual=True))["a100"] == (CaseType.BILINGUAL_IDENTICAL,)


@pytest.mark.parametrize(
    "en_kw",
    [
        {"flags": frozenset({Flag.CANCELLED})},
        {"flags": frozenset({Flag.HEADLINES_REVISED})},
        {"flags": frozenset({Flag.REVISED})},
    ],
)
def test_a_revised_or_cancelled_headline(en_kw: dict[str, object]) -> None:
    assert tags(pair(100, en_kw=en_kw))["a100"] == (CaseType.REVISED_OR_CANCELLED,)


def test_a_marker_the_parser_could_not_map_still_counts_as_revised() -> None:
    a = pair(100)
    en = a.en.model_copy(update={"category_prefix": "(Something New)"})  # type: ignore[union-attr]
    assert tags(a.model_copy(update={"en": en}))["a100"] == (CaseType.REVISED_OR_CANCELLED,)


def test_a_multi_file_document() -> None:
    a = pair(100, format=Format.MULTI_FILE, en_kw={"size_label": "Multi-Files"})
    assert tags(a)["a100"] == (CaseType.MULTI_FILE,)


def test_a_web_page_entry() -> None:
    assert tags(pair(100, format=Format.WEB_PAGE))["a100"] == (CaseType.WEB_PAGE,)


def test_a_document_before_2007() -> None:
    when = datetime(2006, 12, 29, 17, 0, tzinfo=HKT)
    assert tags(pair(100, when))["a100"] == (CaseType.PRE_2007,)


def test_a_document_on_the_first_day_of_2007_is_not_pre_2007() -> None:
    when = datetime(2007, 1, 1, 0, 0, tzinfo=HKT)
    assert CaseType.PRE_2007 not in tags(pair(100, when))["a100"]


def test_a_document_on_the_last_day_of_2006_is_pre_2007() -> None:
    when = datetime(2006, 12, 31, 23, 59, tzinfo=HKT)
    assert CaseType.PRE_2007 in tags(pair(100, when))["a100"]


def test_a_delisted_company() -> None:
    assert tags(pair(100), active=False)["a100"] == (CaseType.DELISTED,)


def test_a_same_minute_block_layout_is_tagged_and_not_ordinary() -> None:
    a = pair(100, status=Status.CHECK, layout_ambiguous=True)
    assert tags(a)["a100"] == (CaseType.BLOCK_LAYOUT,)


def test_a_stub_claim_takes_its_format_from_the_real_document() -> None:
    a = Announcement(
        id="e",
        status=Status.EN_ONLY,
        release_at=WHEN,
        en=doc(Lang.EN, 10, ext="htm", file_type="HTM"),
        reason=SingleReason.STUB_IN_OTHER_SECTION,
        stub=doc(Lang.TC, 11, stub=True),
        format=Format.WEB_PAGE,
    )
    assert set(tags(a)["e"]) == {CaseType.EN_ONLY_STUB, CaseType.WEB_PAGE}


def test_every_announcement_gets_at_least_one_type() -> None:
    announcements = [
        pair(100, at(10)),
        pair(200, at(10), status=Status.CHECK, layout_ambiguous=True),
        pair(300, datetime(2005, 5, 5, 9, 0, tzinfo=HKT)),
        Announcement(
            id="n",
            status=Status.TC_ONLY,
            release_at=at(50),
            tc=doc(Lang.TC, 9, at(50)),
            reason=SingleReason.NOT_FOUND,
        ),
    ]
    result = tag_announcements(announcements, stock_active=False)
    assert set(result) == {a.id for a in announcements}
    assert all(result[a.id] for a in announcements)


def test_types_come_back_in_a_fixed_order_without_repeats() -> None:
    a = pair(100, at(10), format=Format.WEB_PAGE, bilingual=True)
    result = tags(a, pair(200, at(10)), active=False)["a100"]
    assert len(set(result)) == len(result)
    assert list(result) == sorted(result, key=list(CaseType).index)


# --- stratified sampling ----------------------------------------------------------------------


def cand(id_: str, *strata: str, busy: bool = False) -> Candidate:
    return Candidate(id_, frozenset(strata), busy)


POOL = [cand(f"c{i:02d}", "ordinary", "status:matched", busy=i % 3 == 0) for i in range(30)] + [
    cand("rare1", "web_page", "status:matched"),
    cand("rare2", "bilingual_identical", "status:matched"),
    cand("chk1", "ordinary", "status:check"),
    cand("stub1", "en_only_stub", "status:en_only"),
]


def test_every_stratum_is_covered_before_random_fill() -> None:
    chosen = stratified_sample(POOL, 5, seed=1)
    strata = set().union(*(c.strata for c in POOL if c.id in chosen))
    assert {"web_page", "bilingual_identical", "en_only_stub", "status:check"} <= strata


def test_the_same_seed_gives_the_same_sample() -> None:
    assert stratified_sample(POOL, 10, seed=7) == stratified_sample(POOL, 10, seed=7)


def test_a_different_seed_gives_a_different_fill() -> None:
    assert stratified_sample(POOL, 10, seed=1) != stratified_sample(POOL, 10, seed=2)


def test_the_input_order_does_not_change_the_sample() -> None:
    assert stratified_sample(POOL, 10, seed=3) == stratified_sample(POOL[::-1], 10, seed=3)


def test_the_sample_never_exceeds_n_and_has_no_repeats() -> None:
    for n in (0, 1, 3, 12, 100):
        chosen = stratified_sample(POOL, n, seed=5)
        assert len(chosen) == min(n, len(POOL)) and len(set(chosen)) == len(chosen)


def test_when_there_are_more_strata_than_slots_the_rarest_come_first() -> None:
    chosen = stratified_sample(POOL, 2, seed=1)
    assert len(chosen) == 2
    assert not any(c.startswith("c") for c in chosen)


def test_fill_prefers_busy_days() -> None:
    pool = [cand(f"q{i:02d}", "ordinary", busy=i < 4) for i in range(20)]
    chosen = stratified_sample(pool, 4, seed=9)
    assert all(int(c[1:]) < 4 for c in chosen)


def test_an_empty_pool_gives_an_empty_sample() -> None:
    assert stratified_sample([], 5, seed=1) == []


# --- coverage ---------------------------------------------------------------------------------


def golden(i: int, types: list[CaseType], *, verified: bool, stock_id: int = 1) -> Entry:
    en = DocRef(news_id=str(i), path="/x.pdf", title="t", released="2026-10-28 22:52")
    tc = DocRef(news_id=str(i + 1), path="/x_c.pdf", title="t", released="2026-10-28 22:52")
    return Entry(
        id=f"09688-{i}",
        verified=verified,
        stock_code="09688",
        stock_id=stock_id,
        stock_name="ZAI LAB",
        scenario="s",
        case_types=types,
        truth=Truth(en=en, tc=tc),
        proposal=Proposal(status="matched", score=1, evidence=[]),
    )


def test_coverage_counts_verified_and_draft_entries_apart() -> None:
    entries = [
        golden(1, [CaseType.ORDINARY], verified=True),
        golden(3, [CaseType.ORDINARY], verified=False),
    ]
    c = coverage(entries)
    assert (c.entries, c.verified) == (2, 1)
    assert c.by_case[CaseType.ORDINARY] == (1, 2)


def test_coverage_counts_issuers_by_security_not_by_code() -> None:
    entries = [
        golden(1, [CaseType.ORDINARY], verified=True, stock_id=20),  # HUTCHISON
        golden(3, [CaseType.ORDINARY], verified=True, stock_id=1000001102),  # HUTCHMED, same 00013
    ]
    assert coverage(entries).issuers_verified == 2


def test_an_empty_golden_set_reports_every_gap() -> None:
    gaps = coverage([]).gaps
    assert any("50" in g for g in gaps) and any("12" in g for g in gaps)
    for case in REQUIRED_CASE_TYPES:
        if case not in ACCEPTED_GAPS:
            assert any(case.value in g for g in gaps)


def test_only_verified_entries_count_towards_the_totals() -> None:
    entries = [
        golden(2 * i, list(REQUIRED_CASE_TYPES), verified=i < 10, stock_id=i) for i in range(60)
    ]
    gaps = coverage(entries).gaps
    assert "10 verified entries; at least 50 are needed" in gaps
    assert "10 verified issuers; at least 12 are needed" in gaps
    assert len(gaps) == 2


def test_unverified_entries_do_not_close_a_gap() -> None:
    entries = [golden(i, list(REQUIRED_CASE_TYPES), verified=False, stock_id=i) for i in range(60)]
    assert coverage(entries).gaps


def test_a_complete_verified_set_has_no_gaps() -> None:
    entries = [
        golden(2 * i, list(REQUIRED_CASE_TYPES), verified=True, stock_id=i) for i in range(50)
    ]
    c = coverage(entries)
    assert c.gaps == ()
    assert c.issuers_verified == 50


def test_fifty_entries_from_eleven_issuers_is_a_gap() -> None:
    entries = [
        golden(2 * i, list(REQUIRED_CASE_TYPES), verified=True, stock_id=i % 11) for i in range(50)
    ]
    assert any("issuers" in g for g in coverage(entries).gaps)


def test_extra_case_types_are_counted_but_never_required() -> None:
    entries = [
        golden(2 * i, [*REQUIRED_CASE_TYPES, CaseType.BLOCK_LAYOUT], verified=True, stock_id=i)
        for i in range(50)
    ]
    c = coverage(entries)
    assert c.by_case[CaseType.BLOCK_LAYOUT] == (50, 50)
    assert c.gaps == ()


def test_a_case_nobody_could_find_is_an_accepted_gap_not_a_failure() -> None:
    assert CaseType.SEPARATE_ANNUAL_REPORT in ACCEPTED_GAPS
    types = [c for c in REQUIRED_CASE_TYPES if c not in ACCEPTED_GAPS]
    entries = [golden(2 * i, types, verified=True, stock_id=i) for i in range(50)]
    c = coverage(entries)
    assert c.gaps == ()
    assert [a.split(":")[0] for a in c.accepted] == ["separate_annual_report"]
    assert "README" in c.accepted[0]


def test_an_accepted_gap_that_gets_a_verified_entry_is_no_longer_listed() -> None:
    entries = [
        golden(2 * i, list(REQUIRED_CASE_TYPES), verified=True, stock_id=i) for i in range(50)
    ]
    c = coverage(entries)
    assert c.gaps == () and c.accepted == ()


def test_an_accepted_gap_does_not_excuse_anything_else() -> None:
    types = [
        c for c in REQUIRED_CASE_TYPES if c not in ACCEPTED_GAPS and c is not CaseType.WEB_PAGE
    ]
    entries = [golden(2 * i, types, verified=True, stock_id=i) for i in range(50)]
    assert coverage(entries).gaps == ("no verified entry for case type web_page",)
