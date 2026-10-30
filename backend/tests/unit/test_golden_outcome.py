"""Judging the matcher against the golden set: every way an entry can come out (Phase 2.6)."""

from datetime import datetime
from typing import Any

import pytest

from app.domain.models import Document, Lang
from app.pairing.models import (
    Announcement,
    PairingDiagnostics,
    PairingResult,
    Rival,
    SingleReason,
    Status,
)
from tests.golden.outcome import (
    Judgement,
    Outcome,
    Report,
    content_evidence,
    judge,
    judge_all,
    render,
)
from tests.golden.schema import CaseType, DocRef, Entry, Proposal, Truth
from tests.golden.store import FileFacts
from tests.support import make_doc

WHEN = datetime(2026, 10, 28, 22, 52)


def en(news_id: int) -> Document:
    return make_doc(Lang.EN, news_id, WHEN, news_id=news_id)


def tc(news_id: int) -> Document:
    return make_doc(Lang.TC, news_id, WHEN, news_id=news_id, c_suffix=True)


def ann(
    status: Status,
    english: Document | None = None,
    chinese: Document | None = None,
    *,
    reason: SingleReason | None = None,
    rivals: tuple[Rival, ...] = (),
    evidence: tuple[str, ...] = ("Published together.",),
    stub: Document | None = None,
) -> Announcement:
    first = english or chinese
    assert first is not None
    return Announcement(
        id=f"a{first.news_id}",
        status=status,
        release_at=WHEN,
        en=english,
        tc=chinese,
        reason=reason,
        rivals=rivals,
        evidence=evidence,
        stub=stub,
    )


def ref(news_id: int) -> DocRef:
    return DocRef(news_id=str(news_id), path="/x.pdf", title="t", released="2026-10-28 22:52")


def entry(truth: Truth, **overrides: Any) -> Entry:
    fields: dict[str, Any] = {
        "id": "00001-1",
        "verified": True,
        "stock_code": "00001",
        "stock_id": 1,
        "stock_name": "TEST",
        "scenario": "s",
        "case_types": [CaseType.ORDINARY],
        "truth": truth,
        "proposal": Proposal(status="matched"),
    }
    return Entry(**(fields | overrides))


def pair_entry(en_id: int, tc_id: int, **overrides: Any) -> Entry:
    return entry(Truth(en=ref(en_id), tc=ref(tc_id)), **overrides)


def en_single(en_id: int, absent: str) -> Entry:
    return entry(Truth(en=ref(en_id), absent=absent))


def tc_single(tc_id: int, absent: str) -> Entry:
    return entry(Truth(tc=ref(tc_id), absent=absent))


# --- a pair in the golden set -----------------------------------------------------------------


def test_a_confirmed_pair_that_is_the_right_one() -> None:
    j = judge(pair_entry(10, 11), [ann(Status.MATCHED, en(10), tc(11))])
    assert j.outcome is Outcome.MATCHED_RIGHT
    assert j.status == "matched"


def test_a_pair_offered_for_checking_with_the_right_partner() -> None:
    j = judge(pair_entry(10, 11), [ann(Status.CHECK, en(10), tc(11))])
    assert j.outcome is Outcome.CHECK_RIGHT


def test_the_english_document_confirmed_with_another_chinese_one_is_wrong() -> None:
    result = [
        ann(Status.MATCHED, en(10), tc(12)),
        ann(Status.TC_ONLY, None, tc(11), reason=SingleReason.NOT_FOUND),
    ]
    j = judge(pair_entry(10, 11), result)
    assert j.outcome is Outcome.MATCHED_WRONG
    assert "12" in j.detail and "11" in j.detail


def test_the_chinese_document_confirmed_with_another_english_one_is_wrong() -> None:
    result = [
        ann(Status.EN_ONLY, en(10), reason=SingleReason.NOT_FOUND),
        ann(Status.MATCHED, en(9), tc(11)),
    ]
    j = judge(pair_entry(10, 11), result)
    assert j.outcome is Outcome.MATCHED_WRONG
    assert "9" in j.detail


def test_a_wrong_partner_offered_for_checking_is_visible_and_not_a_failure() -> None:
    result = [
        ann(Status.CHECK, en(10), tc(12)),
        ann(Status.TC_ONLY, None, tc(11), reason=SingleReason.NOT_FOUND),
    ]
    assert judge(pair_entry(10, 11), result).outcome is Outcome.CHECK_WRONG


def test_a_wrong_confirmed_pair_outranks_a_check_on_the_other_side() -> None:
    result = [ann(Status.MATCHED, en(10), tc(12)), ann(Status.CHECK, en(9), tc(11))]
    assert judge(pair_entry(10, 11), result).outcome is Outcome.MATCHED_WRONG


def test_a_pair_shown_as_two_single_language_entries_is_held_apart() -> None:
    result = [
        ann(Status.EN_ONLY, en(10), reason=SingleReason.NOT_FOUND),
        ann(Status.TC_ONLY, None, tc(11), reason=SingleReason.NOT_FOUND),
    ]
    j = judge(pair_entry(10, 11), result)
    assert j.outcome is Outcome.HELD_APART
    assert j.status == "en_only"


# --- a single-language entry ------------------------------------------------------------------


def test_a_single_with_the_right_reason() -> None:
    result = [ann(Status.EN_ONLY, en(10), reason=SingleReason.STUB_IN_OTHER_SECTION)]
    assert judge(en_single(10, "stub"), result).outcome is Outcome.SINGLE_RIGHT
    result = [ann(Status.TC_ONLY, None, tc(11), reason=SingleReason.NOT_FOUND)]
    assert judge(tc_single(11, "not_found"), result).outcome is Outcome.SINGLE_RIGHT


def test_a_single_with_another_reason_is_reported_apart() -> None:
    result = [ann(Status.EN_ONLY, en(10), reason=SingleReason.NOT_FOUND)]
    j = judge(en_single(10, "stub"), result)
    assert j.outcome is Outcome.SINGLE_REASON_DIFFERS
    assert "not_found" in j.detail and "stub" in j.detail


def test_a_document_with_no_counterpart_confirmed_with_one_is_wrong() -> None:
    result = [ann(Status.MATCHED, en(10), tc(11))]
    assert judge(en_single(10, "not_found"), result).outcome is Outcome.MATCHED_WRONG
    assert judge(tc_single(11, "stub"), result).outcome is Outcome.MATCHED_WRONG


def test_a_document_with_no_counterpart_offered_a_partner_for_checking() -> None:
    result = [ann(Status.CHECK, en(10), tc(11))]
    assert judge(en_single(10, "not_found"), result).outcome is Outcome.CHECK_NO_COUNTERPART


# --- what counts as found ---------------------------------------------------------------------


def test_a_document_that_the_search_did_not_return_is_missing() -> None:
    j = judge(pair_entry(10, 11), [ann(Status.EN_ONLY, en(10), reason=SingleReason.NOT_FOUND)])
    assert j.outcome is Outcome.MISSING
    assert "Chinese 11" in j.detail


def test_a_stub_notice_is_not_a_version() -> None:
    result = [ann(Status.EN_ONLY, en(10), reason=SingleReason.STUB_IN_OTHER_SECTION, stub=tc(11))]
    assert judge(tc_single(11, "stub"), result).outcome is Outcome.MISSING


def test_the_proposal_made_when_the_entry_was_drafted_is_ignored() -> None:
    e = pair_entry(10, 11, proposal=Proposal(status="matched", score=14, evidence=["x"]))
    assert judge(e, [ann(Status.CHECK, en(10), tc(11))]).outcome is Outcome.CHECK_RIGHT


def test_the_judgement_carries_the_matchers_own_evidence_and_the_entry_case_types() -> None:
    e = pair_entry(10, 11, case_types=[CaseType.PRE_2007, CaseType.ORDINARY])
    j = judge(
        e, [ann(Status.CHECK, en(10), tc(11), evidence=("Published 1 minute apart.", "Compare."))]
    )
    assert j.evidence == ("Published 1 minute apart.", "Compare.")
    assert j.case_types == (CaseType.PRE_2007, CaseType.ORDINARY)
    assert j.entry_id == "00001-1"


def test_judge_all_uses_each_entrys_own_scenario() -> None:
    a = pair_entry(10, 11, id="a", scenario="one")
    b = pair_entry(20, 21, id="b", scenario="two")
    results = {
        "one": [ann(Status.MATCHED, en(10), tc(11))],
        "two": [ann(Status.CHECK, en(20), tc(21))],
    }
    assert [j.outcome for j in judge_all([a, b], results)] == [
        Outcome.MATCHED_RIGHT,
        Outcome.CHECK_RIGHT,
    ]


# --- the report -------------------------------------------------------------------------------


def verdict(
    outcome: Outcome,
    entry_id: str = "e",
    *,
    pair: bool = True,
    cases: tuple[CaseType, ...] = (CaseType.ORDINARY,),
) -> Judgement:
    return Judgement(entry_id, outcome, pair, cases, "matched", "detail", ("why",))


def test_precision_is_the_share_of_confirmed_pairs_that_are_right() -> None:
    report = Report(
        (
            verdict(Outcome.MATCHED_RIGHT),
            verdict(Outcome.MATCHED_RIGHT),
            verdict(Outcome.MATCHED_RIGHT),
            verdict(Outcome.MATCHED_WRONG),
            verdict(Outcome.CHECK_RIGHT),
        )
    )
    assert report.precision == 0.75
    assert [j.outcome for j in report.wrong_matched] == [Outcome.MATCHED_WRONG]


def test_precision_is_none_when_nothing_was_confirmed() -> None:
    assert Report((verdict(Outcome.CHECK_RIGHT),)).precision is None


def test_pairs_confirmed_and_offered_count_only_pairs() -> None:
    report = Report(
        (
            verdict(Outcome.MATCHED_RIGHT),
            verdict(Outcome.CHECK_RIGHT),
            verdict(Outcome.HELD_APART),
            verdict(Outcome.SINGLE_RIGHT, pair=False),
        )
    )
    assert (report.pairs, report.pairs_confirmed, report.pairs_offered) == (3, 1, 1)


def test_missing_documents_are_listed() -> None:
    report = Report((verdict(Outcome.MISSING, "m"), verdict(Outcome.MATCHED_RIGHT)))
    assert [j.entry_id for j in report.missing] == ["m"]


# --- the printed table ------------------------------------------------------------------------


def runs() -> dict[str, Report]:
    structural = Report(
        (
            verdict(Outcome.MATCHED_RIGHT, "ok-1"),
            verdict(Outcome.CHECK_RIGHT, "chk-1", cases=(CaseType.REVISED_OR_CANCELLED,)),
            verdict(Outcome.MATCHED_WRONG, "bad-1", cases=(CaseType.PRE_2007, CaseType.ORDINARY)),
            verdict(Outcome.SINGLE_RIGHT, "one-1", pair=False, cases=(CaseType.EN_ONLY_STUB,)),
        )
    )
    with_content = Report(
        (
            verdict(Outcome.MATCHED_RIGHT, "ok-1"),
            verdict(Outcome.MATCHED_RIGHT, "chk-1", cases=(CaseType.REVISED_OR_CANCELLED,)),
            verdict(Outcome.MATCHED_WRONG, "bad-1", cases=(CaseType.PRE_2007, CaseType.ORDINARY)),
            verdict(Outcome.SINGLE_RIGHT, "one-1", pair=False, cases=(CaseType.EN_ONLY_STUB,)),
        )
    )
    return {"structural": structural, "with content check": with_content}


def line(text: str, start: str) -> str:
    return next(ln for ln in text.splitlines() if ln.strip().startswith(start))


def test_the_table_shows_both_runs_side_by_side() -> None:
    text = render(runs(), issuers=3)
    assert "4 verified entries from 3 issuers" in text
    header = line(text, "Outcome")
    assert "structural" in header and "with content check" in header
    assert line(text, "Confirmed, right pair").split()[-2:] == ["1", "2"]
    assert line(text, "Confirmed, WRONG").split()[-2:] == ["1", "1"]
    assert line(text, "For checking, right partner").split()[-2:] == ["1", "0"]


def test_the_table_states_precision_and_pairs_for_each_run() -> None:
    text = render(runs(), issuers=3)
    assert "50.0% (1 of 2)" in text  # structural: 1 right, 1 wrong
    assert "66.7% (2 of 3)" in text  # with content: 2 right, 1 wrong


def test_the_table_counts_an_entry_under_each_of_its_case_types() -> None:
    text = render(runs(), issuers=3)
    assert line(text, "pre_2007").split()[1:3] == ["1", "0"]  # entries, confirmed
    assert line(text, "ordinary").split()[1] == "2"  # ok-1 and bad-1


def test_every_entry_not_confirmed_is_listed_with_its_reason() -> None:
    text = render(runs(), issuers=3)
    assert "chk-1" in text and "bad-1" in text and "one-1" in text
    assert "ok-1" not in text
    assert "why" in text


def test_a_run_that_confirms_every_entry_lists_nothing() -> None:
    clean = {"structural": Report((verdict(Outcome.MATCHED_RIGHT, "ok-1"),))}
    text = render(clean, issuers=1)
    assert "ok-1" not in text
    assert "Every entry was confirmed" in text


# --- evidence from the files' facts -----------------------------------------------------------


def facts(tokens: dict[str, int], digest: str = "a") -> FileFacts:
    return FileFacts(sha256=digest * 64, bytes=1, tokens=tokens)


FIGURES = {"100": 1, "200": 1, "300": 1, "400": 1, "500": 1, "600": 1}
OTHER = {"711": 1, "722": 1, "733": 1, "744": 1, "755": 1, "766": 1}


def result_of(*announcements: Announcement) -> PairingResult:
    return PairingResult(tuple(announcements), PairingDiagnostics())


def test_a_checked_pair_gets_a_verdict_against_its_partner_and_the_rivals() -> None:
    rival = Rival(document=tc(12), score=4)
    check = ann(Status.CHECK, en(10), tc(11), rivals=(rival,))
    evidence = content_evidence(
        result_of(check),
        {"en:10": facts(FIGURES), "tc:11": facts(FIGURES, "b"), "tc:12": facts(OTHER, "c")},
    )
    (v,) = evidence.verdicts
    assert (v.en_news_id, v.tc_news_id, v.conclusive) == ("10", "11", True)
    assert v.runner_up == 0.0


def test_a_rival_that_fits_better_wins_the_verdict() -> None:
    rival = Rival(document=tc(12), score=4)
    check = ann(Status.CHECK, en(10), tc(11), rivals=(rival,))
    evidence = content_evidence(
        result_of(check),
        {"en:10": facts(FIGURES), "tc:11": facts(OTHER, "b"), "tc:12": facts(FIGURES, "c")},
    )
    assert evidence.verdicts[0].tc_news_id == "12"


def test_the_sha256_of_every_known_file_is_passed_on() -> None:
    evidence = content_evidence(result_of(), {"en:10": facts({}, "a"), "tc:11": facts({}, "b")})
    assert evidence.sha256 == {(Lang.EN, "10"): "a" * 64, (Lang.TC, "11"): "b" * 64}


def test_an_unreadable_side_gives_no_verdict() -> None:
    check = ann(Status.CHECK, en(10), tc(11), rivals=(Rival(document=tc(12), score=4),))
    # a readable rival does not stand in for an unreadable partner
    rival_readable = {
        "en:10": facts(FIGURES),
        "tc:11": facts({}, "b"),
        "tc:12": facts(FIGURES, "c"),
    }
    assert content_evidence(result_of(check), rival_readable).verdicts == ()
    assert (
        content_evidence(
            result_of(check), {"en:10": facts({}), "tc:11": facts(FIGURES, "b")}
        ).verdicts
        == ()
    )


def test_a_missing_file_gives_no_verdict() -> None:
    check = ann(Status.CHECK, en(10), tc(11))
    assert content_evidence(result_of(check), {"en:10": facts(FIGURES)}).verdicts == ()


def test_a_rival_without_readable_text_is_left_out_not_counted_against() -> None:
    rival = Rival(document=tc(12), score=4)
    check = ann(Status.CHECK, en(10), tc(11), rivals=(rival,))
    evidence = content_evidence(
        result_of(check),
        {"en:10": facts(FIGURES), "tc:11": facts(FIGURES, "b"), "tc:12": facts({}, "c")},
    )
    assert evidence.verdicts[0].tc_news_id == "11"


@pytest.mark.parametrize("status", [Status.MATCHED, Status.EN_ONLY, Status.TC_ONLY])
def test_only_pairs_offered_for_checking_get_a_verdict(status: Status) -> None:
    both = status is Status.MATCHED
    a = ann(
        status,
        en(10) if status is not Status.TC_ONLY else None,
        tc(11) if both or status is Status.TC_ONLY else None,
        reason=None if both else SingleReason.NOT_FOUND,
    )
    assert (
        content_evidence(
            result_of(a), {"en:10": facts(FIGURES), "tc:11": facts(FIGURES, "b")}
        ).verdicts
        == ()
    )
