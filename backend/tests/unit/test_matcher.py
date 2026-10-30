"""Pairing rules (SPEC §4, D-009, D-011). Every wrong `matched` would be the worst failure."""

from datetime import date, datetime
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.domain.models import Document, Flag, Lang
from app.pairing.matcher import pair_documents
from app.pairing.models import (
    Announcement,
    ContentEvidence,
    ContentVerdict,
    Format,
    PairingResult,
    SingleReason,
    Status,
)
from tests.support import make_doc


def d(lang: Lang, seq: int | None, minute: int = 0, day: int = 28, **kw: Any) -> Document:
    return make_doc(lang, seq, datetime(2026, 10, day, 10, minute), **kw)


def en(seq: int | None, minute: int = 0, **kw: Any) -> Document:
    return d(Lang.EN, seq, minute, **kw)


def tc(seq: int | None, minute: int = 0, **kw: Any) -> Document:
    return d(Lang.TC, seq, minute, **kw)


def run(english: list[Document], chinese: list[Document], **kw: Any) -> PairingResult:
    return pair_documents(english, chinese, **kw)


def shape(result: PairingResult) -> dict[tuple[int | None, int | None], Status]:
    return {
        (a.en.seq if a.en else None, a.tc.seq if a.tc else None): a.status
        for a in result.announcements
    }


def only(result: PairingResult) -> Announcement:
    (a,) = result.announcements
    return a


# --- the ordinary case -------------------------------------------------------------------


def test_a_consecutive_same_minute_same_category_pair_is_matched() -> None:
    a = only(run([en(1739, 52)], [tc(1740, 52)]))
    assert a.status is Status.MATCHED
    assert (a.en and a.en.seq, a.tc and a.tc.seq) == (1739, 1740)
    assert a.score == 3 + 3 + 4 + 1  # S1 + S2 + S3 + S4 (news ids follow the file numbers)
    assert a.evidence[0] == (
        "Published together at 10:52 HKT, same headline category, "
        "consecutive HKEX file numbers (01739 and 01740)."
    )
    assert a.format is Format.PDF and not a.layout_ambiguous and a.rivals == ()


def test_two_pairs_on_one_day_are_matched_separately() -> None:
    result = run([en(1671, 28), en(1739, 52)], [tc(1672, 28), tc(1740, 52)])
    assert shape(result) == {(1739, 1740): Status.MATCHED, (1671, 1672): Status.MATCHED}


def test_interleaved_same_minute_pairs_are_matched() -> None:
    # Listing documents in research notes: EN 684 with TC 685 and EN 694 with TC 695.
    english, chinese = [en(684), en(694)], [tc(685), tc(695)]
    assert set(shape(run(english, chinese)).values()) == {Status.MATCHED}


def test_closely_numbered_interleaved_pairs_pass_the_margin() -> None:
    english, chinese = [en(100), en(102)], [tc(101), tc(103)]
    result = run(english, chinese)
    assert shape(result) == {(100, 101): Status.MATCHED, (102, 103): Status.MATCHED}


def test_announcements_are_sorted_newest_first() -> None:
    result = run([en(10, 0), en(20, 30)], [tc(11, 0), tc(21, 30)])
    assert [a.release_at.minute for a in result.announcements] == [30, 0]


# --- thresholds, margin and conflicts ----------------------------------------------------


def test_a_missing_category_on_one_side_keeps_the_score_below_the_threshold() -> None:
    # S1 3 + S2 0 + S3 4 + S4 1 = 8 < 9
    a = only(run([en(100, categories=())], [tc(101)]))
    assert (a.status, a.score) == (Status.CHECK, 8)


def test_agreeing_title_numbers_lift_the_same_pair_to_the_threshold() -> None:
    e = en(100, categories=(), title="2026 Interim results")
    t = tc(101, title="2026年中期業績")
    a = only(run([e], [t]))
    assert (a.status, a.score) == (Status.MATCHED, 9)


def test_a_close_rival_blocks_matched() -> None:
    # TC 103's news id also follows EN 100's, so it scores 3 + 3 + 2 + 1 = 9 against 11.
    english = [en(100, news_id=500)]
    chinese = [tc(101, news_id=501), tc(103, news_id=501)]
    result = run(english, chinese)
    best = next(a for a in result.announcements if a.en)
    assert best.status is Status.CHECK
    assert best.tc and best.tc.seq == 101
    assert [r.document.seq for r in best.rivals] == [103]
    assert "Best guess" in " ".join(best.evidence)


def test_a_distant_rival_does_not_block_matched() -> None:
    result = run([en(100)], [tc(101), tc(103, 3)])  # TC 103 is 3 minutes later: 1 + 3 + 2 = 6
    best = next(a for a in result.announcements if a.en)
    assert best.status is Status.MATCHED


def test_disjoint_categories_are_not_paired() -> None:
    # S1 3 + S2 -4 + S3 4 = 3, below the check floor of 4.
    e, t = en(100, categories=("50200",), news_id=1), tc(101, categories=("18480",), news_id=9)
    assert shape(run([e], [t])) == {(100, None): Status.EN_ONLY, (None, 101): Status.TC_ONLY}


def test_disjoint_categories_at_the_check_floor_are_never_matched() -> None:
    # With the weak NEWS_ID signal the same pair reaches 4: shown as a check, conflict stated.
    a = only(run([en(100, categories=("50200",))], [tc(101, categories=("18480",))]))
    assert (a.status, a.score) == (Status.CHECK, 4)
    assert "The headline categories differ." in a.evidence


def test_conflicting_title_numbers_are_never_matched() -> None:
    a = only(run([en(100, title="2025 Annual report")], [tc(101, title="2024年報")]))
    assert a.status is Status.CHECK
    assert any("numbers" in line for line in a.evidence)


def test_a_cancelled_flag_on_one_side_is_never_matched() -> None:
    a = only(run([en(100, flags=frozenset({Flag.CANCELLED}))], [tc(101)]))
    assert a.status is Status.CHECK
    assert any("revised or cancelled" in line for line in a.evidence)


def test_same_minute_documents_far_apart_in_number_are_only_a_check() -> None:
    a = only(run([en(100)], [tc(130)]))  # S1 3 + S2 3, no sequence relation
    assert (a.status, a.score) == (Status.CHECK, 6)


# --- pre-2007 (D-009) ---------------------------------------------------------------------


def old(lang: Lang, seq: int, minute: int = 0, **kw: Any) -> Document:
    when = datetime(2005, 11, 28, 10, minute)
    return make_doc(lang, seq, when, categories=(), old_style=True, c_suffix=lang is Lang.TC, **kw)


def old_pair(minute_en: int = 0, minute_tc: int = 0, seq_en: int = 110, seq_tc: int = 110) -> Any:
    return [old(Lang.EN, seq_en, minute_en)], [old(Lang.TC, seq_tc, minute_tc)]


def test_a_2005_pair_with_the_same_number_and_minute_is_matched() -> None:
    english, chinese = old_pair()
    a = only(run(english, chinese))
    assert (a.status, a.score) == (Status.MATCHED, 7)
    assert "same HKEX file number" in a.evidence[0]


def test_a_2005_pair_a_minute_apart_is_only_a_check() -> None:
    english, chinese = old_pair(minute_tc=1)  # S1 +1 + S3 +4 = 5
    assert only(run(english, chinese)).status is Status.CHECK


def test_a_pre_2007_score_of_seven_without_the_same_minute_is_only_a_check() -> None:
    # S1 close 1 + S3 exact 4 + S4 1 + S6 1 = 7 reaches the no-category threshold, but D-009 also
    # needs the same release minute, so it must stay a check.
    e = old(Lang.EN, 110, 0, title="Annual Report 2005", news_id=500)
    t = old(Lang.TC, 110, 1, title="2005年報", news_id=501)
    a = only(run([e], [t]))
    assert a.score == 7
    assert a.status is Status.CHECK


def test_a_2005_pair_without_the_exact_number_relation_is_only_a_check() -> None:
    english, chinese = old_pair(seq_tc=111)  # same minute, numbers only near: 3 + 2 = 5
    assert only(run(english, chinese)).status is Status.CHECK


def test_consecutive_2005_pairs_are_both_matched_because_each_number_is_unique() -> None:
    english = [old(Lang.EN, n) for n in (110, 111)]
    chinese = [old(Lang.TC, n) for n in (110, 111)]
    result = run(english, chinese)
    assert shape(result) == {(110, 110): Status.MATCHED, (111, 111): Status.MATCHED}
    assert result.diagnostics.non_interleaved_groups == 0


def test_a_2005_chinese_file_with_no_english_number_is_not_pulled_to_a_neighbour() -> None:
    # TC 96_c has no EN 96 here; it must not be offered to EN 97 just because 96 is close to 97.
    result = run([old(Lang.EN, 97)], [old(Lang.TC, 96)])
    assert set(shape(result).values()) == {Status.EN_ONLY, Status.TC_ONLY}


def test_a_lone_pre_2007_pair_with_plus_one_numbering_is_only_a_check() -> None:
    # Without a 2005-style pair beside it the scheme is unproven; before 2007 it is assumed old,
    # so the +1 relation is ignored and only the weak NEWS_ID signal remains: 3 + 1.
    english, chinese = old_pair(seq_tc=111)
    a = only(run(english, chinese))
    assert a.status is Status.CHECK and a.score == 4


def test_a_2015_c_file_one_after_the_english_file_is_a_normal_pair() -> None:
    when = datetime(2015, 6, 3, 18, 3)
    e = make_doc(Lang.EN, 49, when, old_style=True)
    t = make_doc(Lang.TC, 50, when, old_style=True, c_suffix=True)
    assert only(run([e], [t])).status is Status.MATCHED


# --- stubs ----------------------------------------------------------------------------------


def test_a_chinese_stub_makes_the_english_document_english_only() -> None:
    result = run([en(1070, 28)], [tc(1071, 28, stub=True)])
    a = only(result)
    assert (a.status, a.reason) == (Status.EN_ONLY, SingleReason.STUB_IN_OTHER_SECTION)
    assert a.tc is None and a.stub is not None and a.stub.seq == 1071
    assert a.evidence == (
        "The issuer published this in English only. "
        "HKEXnews' Chinese section shows a notice instead.",
    )


def test_an_english_stub_makes_the_chinese_document_chinese_only() -> None:
    a = only(run([en(500, stub=True)], [tc(499)]))
    assert (a.status, a.reason) == (Status.TC_ONLY, SingleReason.STUB_IN_OTHER_SECTION)
    assert a.en is None and a.stub is not None and a.tc is not None and a.tc.seq == 499


def test_a_stub_is_never_offered_as_a_version_or_paired() -> None:
    # The stub (TC 103) must not become EN 100's partner, even though 100 and 103 are close.
    result = run([en(100), en(102)], [tc(101), tc(103, stub=True)])
    assert shape(result) == {(100, 101): Status.MATCHED, (102, None): Status.EN_ONLY}
    assert all(not (a.tc and a.tc.is_stub) for a in result.announcements)


def test_stubs_are_removed_before_the_layout_is_judged() -> None:
    # EN 100 / TC 101 plus an English-only document 102 with its stub 103, all in one minute.
    result = run([en(100), en(102)], [tc(101), tc(103, stub=True)])
    pair = next(a for a in result.announcements if a.tc)
    assert pair.status is Status.MATCHED and not pair.layout_ambiguous


def test_a_stub_two_numbers_after_its_document_still_claims_it() -> None:
    # File numbers are one counter for the whole market, so another issuer's file (133) can sit
    # between EN 132 and its stub 134. Seen twice in 790 stubs (research notes Q7).
    a = only(run([en(132, 30)], [tc(134, 30, stub=True)]))
    assert (a.status, a.reason) == (Status.EN_ONLY, SingleReason.STUB_IN_OTHER_SECTION)
    assert a.stub is not None and a.stub.seq == 134


def test_a_distant_stub_does_not_guess_between_two_candidates() -> None:
    # Two unclaimed English documents in the minute: which one the stub stands in for is unknown.
    result = run([en(130, 30), en(132, 30)], [tc(134, 30, stub=True)])
    assert result.diagnostics.orphan_stubs == 1
    assert all(a.reason is not SingleReason.STUB_IN_OTHER_SECTION for a in result.announcements)


def test_a_distant_stub_never_claims_a_document_that_has_a_real_counterpart() -> None:
    result = run([en(100, 30)], [tc(101, 30), tc(103, 30, stub=True)])
    assert shape(result) == {(100, 101): Status.MATCHED}
    assert result.diagnostics.orphan_stubs == 1


def test_a_stub_in_a_different_minute_claims_nothing() -> None:
    result = run([en(132, 30)], [tc(134, 31, stub=True)])
    assert result.diagnostics.orphan_stubs == 1
    assert only(result).reason is SingleReason.NOT_FOUND


def test_a_stub_with_no_matching_document_is_counted_and_ignored() -> None:
    result = run([en(50, 5)], [tc(901, 40, stub=True), tc(51, 5)])
    assert shape(result) == {(50, 51): Status.MATCHED}
    assert result.diagnostics.orphan_stubs == 1


def test_a_shared_page_stub_without_a_file_number_claims_by_news_id() -> None:
    # dod/en.html with dod/tc.html: no file numbers; the stub's NEWS_ID is the English one plus 1.
    result = run([en(None, news_id=12099591)], [tc(None, news_id=12099592, stub=True)])
    a = only(result)
    assert (a.status, a.reason) == (Status.EN_ONLY, SingleReason.STUB_IN_OTHER_SECTION)


def test_a_real_shared_page_pair_is_only_a_check() -> None:
    a = only(run([en(None, news_id=7)], [tc(None, news_id=8)]))
    assert (a.status, a.score) == (Status.CHECK, 3 + 3 + 1)


# --- single language ------------------------------------------------------------------------


def test_an_english_document_without_a_counterpart_is_not_found() -> None:
    a = only(run([en(100)], [], searched=(date(2026, 10, 1), date(2026, 10, 31))))
    assert (a.status, a.reason) == (Status.EN_ONLY, SingleReason.NOT_FOUND)
    assert a.evidence == ("No Chinese version found between 1 Oct 2026 and 31 Oct 2026.",)


def test_a_chinese_document_without_a_counterpart_is_not_found() -> None:
    a = only(run([], [tc(101)]))
    assert (a.status, a.reason) == (Status.TC_ONLY, SingleReason.NOT_FOUND)
    assert a.en is None and a.release_at == tc(101).release_at


def test_empty_input_gives_no_announcements() -> None:
    assert run([], []).announcements == ()


# --- same-minute batches (D-011) -------------------------------------------------------------


def block(n: int, first: int = 910) -> tuple[list[Document], list[Document]]:
    kw: dict[str, Any] = {"title": "Disclosure of Dealings under Rule 22", "old_style": True}
    english = [d(Lang.EN, first + i, 3, **kw) for i in range(n)]
    chinese = [d(Lang.TC, first + n + i, 3, c_suffix=True, **kw) for i in range(n)]
    return english, chinese


def test_a_block_batch_is_never_matched() -> None:
    result = run(*block(2))
    assert set(shape(result).values()) == {Status.CHECK}
    assert all(a.layout_ambiguous for a in result.announcements)
    assert result.diagnostics.non_interleaved_groups == 1


def test_a_block_batch_pairs_by_file_order_and_says_so() -> None:
    result = run(*block(2))
    assert set(shape(result)) == {(910, 912), (911, 913)}
    a = next(a for a in result.announcements if a.en and a.en.seq == 910)
    assert any("file order cannot show" in line for line in a.evidence)
    assert {r.document.seq for r in a.rivals} == {911, 913}


def test_a_three_by_three_block_is_never_matched() -> None:
    result = run(*block(3))
    assert set(shape(result).values()) == {Status.CHECK}
    assert set(shape(result)) == {(910, 913), (911, 914), (912, 915)}


def test_the_adjacent_pair_in_a_block_does_not_slip_through_the_margin() -> None:
    # The second English file and the first Chinese file are consecutive, so SPEC v1.2 scored
    # them 11 against 8 and would have matched them. This is the failure D-011 prevents.
    result = run(*block(2))
    assert Status.MATCHED not in shape(result).values()


def test_a_block_beside_an_interleaved_pair_in_another_minute_does_not_infect_it() -> None:
    english, chinese = block(2)
    english.append(en(500, 40))
    chinese.append(tc(501, 40))
    result = run(english, chinese)
    assert shape(result)[(500, 501)] is Status.MATCHED


def test_an_unassigned_document_names_the_counterpart_it_lost() -> None:
    # EN 100 and EN 101 are consecutive, so the group is a batch; only TC 102 exists.
    result = run([en(100), en(101)], [tc(102)])
    loser = next(a for a in result.announcements if a.status is Status.EN_ONLY)
    assert loser.en and loser.en.seq == 101
    assert any("possible counterpart" in line for line in loser.evidence)
    assert shape(result)[(100, 102)] is Status.CHECK


# --- decisive signals --------------------------------------------------------------------------


def test_identical_bytes_make_a_bilingual_document_matched_even_in_a_block() -> None:
    english, chinese = block(2)
    shared = {
        (Lang.EN, english[0].news_id): "aa" * 32,
        (Lang.TC, chinese[1].news_id): "aa" * 32,
        (Lang.EN, english[1].news_id): "bb" * 32,
        (Lang.TC, chinese[0].news_id): "bb" * 32,
    }
    result = run(english, chinese, content=ContentEvidence(sha256=shared))
    matched = {k for k, v in shape(result).items() if v is Status.MATCHED}
    assert matched == {(910, 913), (911, 912)}
    assert all(a.bilingual for a in result.announcements)
    assert "Bilingual document" in result.announcements[0].evidence[0]


def test_identical_bytes_cannot_override_a_hard_conflict() -> None:
    e, t = en(100, categories=("1",)), tc(101, categories=("2",))
    digest = "cc" * 32
    ev = ContentEvidence(sha256={(Lang.EN, e.news_id): digest, (Lang.TC, t.news_id): digest})
    assert Status.MATCHED not in shape(run([e], [t], content=ev)).values()


def verdict(e: Document, t: Document, *, conclusive: bool = True) -> ContentVerdict:
    return ContentVerdict(e.news_id, t.news_id, 0.84, 0.1, 12, conclusive)


def test_a_conclusive_content_check_upgrades_a_block_and_overrides_file_order() -> None:
    english, chinese = block(2)
    verdicts = (verdict(english[0], chinese[1]), verdict(english[1], chinese[0]))
    result = run(english, chinese, content=ContentEvidence(verdicts=verdicts))
    assert {k for k, v in shape(result).items() if v is Status.MATCHED} == {(910, 913), (911, 912)}
    a = next(iter(result.announcements))
    assert any("Content check" in line for line in a.evidence)
    assert not any(x.layout_ambiguous for x in result.announcements)


def test_an_inconclusive_content_check_changes_nothing() -> None:
    english, chinese = block(2)
    verdicts = (verdict(english[0], chinese[1], conclusive=False),)
    result = run(english, chinese, content=ContentEvidence(verdicts=verdicts))
    assert set(shape(result).values()) == {Status.CHECK}
    assert set(shape(result)) == {(910, 912), (911, 913)}


def test_a_content_verdict_for_a_conflicting_pair_does_not_match_it() -> None:
    e, t = en(100, categories=("1",)), tc(101, categories=("2",))
    ev = ContentEvidence(verdicts=(verdict(e, t),))
    assert Status.MATCHED not in shape(run([e], [t], content=ev)).values()


# --- separate submissions (SPEC §4.4) -----------------------------------------------------------


def test_an_annual_report_published_on_another_day_is_a_check() -> None:
    e = d(Lang.EN, 20, 0, day=15, categories=("40100",), title="2025 Annual Report")
    t = d(Lang.TC, 33, 0, day=28, categories=("40100",), title="2025年報")
    a = only(run([e], [t]))
    assert (a.status, a.separate) == (Status.CHECK, True)
    assert a.evidence[0] == "Chinese version published separately on 28 Oct 2026."


def test_a_tc_report_published_before_the_english_one_says_so() -> None:
    e = d(Lang.EN, 33, 0, day=28, categories=("40100",), title="2025 Annual Report")
    t = d(Lang.TC, 20, 0, day=15, categories=("40100",), title="2025年報")
    assert only(run([e], [t])).evidence[0] == "Chinese version published separately on 15 Oct 2026."


def test_other_categories_are_not_paired_across_days() -> None:
    e = d(Lang.EN, 20, 0, day=15)
    t = d(Lang.TC, 33, 0, day=28)
    assert shape(run([e], [t])) == {(20, None): Status.EN_ONLY, (None, 33): Status.TC_ONLY}


def test_separate_submissions_further_apart_than_14_days_are_not_paired() -> None:
    e = d(Lang.EN, 20, 0, day=1, categories=("40100",))
    t = d(Lang.TC, 33, 0, day=28, categories=("40100",))
    assert shape(run([e], [t])) == {(20, None): Status.EN_ONLY, (None, 33): Status.TC_ONLY}


def test_listing_document_categories_are_separate_submission_categories() -> None:
    e = d(Lang.EN, 20, 0, day=15, categories=("31200",), title="Supplementary Listing Document")
    t = d(Lang.TC, 33, 0, day=20, categories=("31200",), title="補充上市文件")
    assert only(run([e], [t])).separate


def test_a_same_day_pair_in_a_separate_category_is_a_normal_pair() -> None:
    a = only(run([en(100, categories=("40100",))], [tc(101, categories=("40100",))]))
    assert (a.status, a.separate) == (Status.MATCHED, False)


# --- formats ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kw", "expected"),
    [
        ({}, Format.PDF),
        ({"ext": "htm", "file_type": "HTM"}, Format.WEB_PAGE),
        ({"ext": "htm", "file_type": "", "size_label": "Multi-Files"}, Format.MULTI_FILE),
        ({"ext": "doc", "file_type": "DOC"}, Format.OTHER),
    ],
)
def test_format_follows_the_file_type(kw: dict[str, str], expected: Format) -> None:
    assert only(run([en(100, **kw)], [])).format is expected


def test_chinese_multi_file_label_is_recognised() -> None:
    t = tc(101, ext="htm", file_type="", size_label="多檔案")
    assert only(run([], [t])).format is Format.MULTI_FILE


def test_mixed_formats_are_reported_as_other_with_a_note() -> None:
    a = only(run([en(100)], [tc(101, ext="htm", file_type="HTM")]))
    assert a.format is Format.OTHER
    assert any("different formats" in line for line in a.evidence)


# --- invariants (property tests) ------------------------------------------------------------------


@st.composite
def document_sets(draw: st.DrawFn) -> tuple[list[Document], list[Document]]:
    n_en = draw(st.integers(0, 7))
    n_tc = draw(st.integers(0, 7))
    seqs = draw(
        st.lists(st.integers(1, 30), min_size=n_en + n_tc, max_size=n_en + n_tc, unique=True)
    )
    docs: list[Document] = []
    for i, seq in enumerate(seqs):
        lang = Lang.EN if i < n_en else Lang.TC
        docs.append(
            d(
                lang,
                seq,
                draw(st.sampled_from([0, 0, 1, 2, 40])),
                categories=draw(st.sampled_from([("A",), ("A",), ("B",), ("A", "B"), ()])),
                title=draw(st.sampled_from(["Notice 2026", "Notice 2025", "Notice", "公告 2026"])),
                stub=draw(st.booleans()) and draw(st.booleans()),
                news_id=1000 + i,
                flags=draw(
                    st.sampled_from([frozenset(), frozenset(), frozenset({Flag.CANCELLED})])
                ),
                c_suffix=lang is Lang.TC and draw(st.booleans()),
            )
        )
    return [x for x in docs if x.lang is Lang.EN], [x for x in docs if x.lang is Lang.TC]


@settings(max_examples=300, suppress_health_check=[HealthCheck.too_slow], deadline=None)
@given(document_sets())
def test_every_real_document_appears_exactly_once_and_stubs_never_do(
    sets: tuple[list[Document], list[Document]],
) -> None:
    english, chinese = sets
    result = run(english, chinese)
    shown: list[tuple[Lang, str]] = []
    stubs: list[str] = []
    for a in result.announcements:
        for doc in (a.en, a.tc):
            if doc is not None:
                assert not doc.is_stub
                shown.append((doc.lang, doc.news_id))
        if a.stub is not None:
            assert a.stub.is_stub
            stubs.append(a.stub.news_id)
    expected = [(x.lang, x.news_id) for x in english + chinese if not x.is_stub]
    assert sorted(shown) == sorted(expected)
    assert len(stubs) == len(set(stubs))


@settings(max_examples=300, suppress_health_check=[HealthCheck.too_slow], deadline=None)
@given(document_sets())
def test_a_matched_pair_has_no_conflict_and_never_comes_from_an_ambiguous_layout(
    sets: tuple[list[Document], list[Document]],
) -> None:
    result = run(*sets)
    for a in result.announcements:
        if a.status is Status.MATCHED:
            assert a.en and a.tc and a.score is not None and a.score >= 7
            assert not a.layout_ambiguous and not a.separate
            assert a.en.flags == a.tc.flags
            assert not any(s.kind in ("disjoint", "conflict") for s in a.signals)
        if a.status in (Status.EN_ONLY, Status.TC_ONLY):
            assert (a.en is None) != (a.tc is None)
            assert a.reason is not None
        if a.status is Status.CHECK:
            assert a.en and a.tc


@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow], deadline=None)
@given(document_sets(), st.randoms(use_true_random=False))
def test_the_result_does_not_depend_on_input_order(
    sets: tuple[list[Document], list[Document]], rnd: Any
) -> None:
    english, chinese = sets
    shuffled_en, shuffled_tc = english[:], chinese[:]
    rnd.shuffle(shuffled_en)
    rnd.shuffle(shuffled_tc)

    def summary(r: PairingResult) -> list[tuple[str, Status]]:
        return [(a.id, a.status) for a in r.announcements]

    assert summary(run(english, chinese)) == summary(run(shuffled_en, shuffled_tc))
