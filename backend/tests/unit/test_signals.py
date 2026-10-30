from datetime import datetime

import pytest

from app.config import PairingConfig
from app.domain.models import Flag, Lang
from app.pairing.signals import (
    category_signal,
    file_relation,
    hard_conflicts,
    news_id_signal,
    numbering_uses_same_number,
    sequence_signal,
    time_signal,
    title_number_signal,
    title_numbers,
)
from tests.support import make_doc

T = datetime(2026, 10, 28, 22, 52)


def en(**kw):  # type: ignore[no-untyped-def]
    return make_doc(Lang.EN, kw.pop("seq", 1739), kw.pop("when", T), **kw)


def tc(**kw):  # type: ignore[no-untyped-def]
    return make_doc(Lang.TC, kw.pop("seq", 1740), kw.pop("when", T), **kw)


# --- S1 --------------------------------------------------------------------------------


def test_same_minute_scores_three() -> None:
    hit = time_signal(en(), tc())
    assert (hit.id, hit.points, hit.kind) == ("S1", 3, "same_minute")


@pytest.mark.parametrize(
    ("minutes", "points", "kind"), [(1, 1, "close"), (5, 1, "close"), (6, 0, "apart")]
)
def test_minutes_apart(minutes: int, points: int, kind: str) -> None:
    later = (
        datetime(2026, 10, 28, 22, 52 + minutes)
        if 52 + minutes < 60
        else datetime(2026, 10, 28, 23, 52 + minutes - 60)
    )
    hit = time_signal(en(), tc(when=later))
    assert (hit.points, hit.kind) == (points, kind)


# --- S2 --------------------------------------------------------------------------------


def test_identical_categories() -> None:
    assert (
        category_signal(en(categories=("18480", "18380")), tc(categories=("18380", "18480"))).points
        == 3
    )


def test_overlapping_categories() -> None:
    hit = category_signal(en(categories=("18480", "18380")), tc(categories=("18380",)))
    assert (hit.points, hit.kind) == (1, "overlap")


def test_disjoint_categories_are_penalised() -> None:
    hit = category_signal(en(categories=("50200",)), tc(categories=("18480",)))
    assert (hit.points, hit.kind) == (-4, "disjoint")


def test_missing_categories_score_nothing_either_side() -> None:
    assert category_signal(en(categories=()), tc()).kind == "unavailable"
    assert category_signal(en(), tc(categories=())).points == 0


# --- S3 --------------------------------------------------------------------------------


def test_chinese_file_one_after_the_english_file() -> None:
    hit = sequence_signal(en(), tc(), same_number_numbering=False)
    assert (hit.points, hit.kind, hit.values) == (4, "plus_one", ("1739", "1740"))


def test_chinese_file_before_the_english_file_is_only_near() -> None:
    assert sequence_signal(en(seq=1740), tc(seq=1739), same_number_numbering=False).kind == "near"


@pytest.mark.parametrize(("gap", "points"), [(2, 2), (3, 2), (4, 0), (0, 2)])
def test_nearby_file_numbers_in_modern_numbering(gap: int, points: int) -> None:
    hit = sequence_signal(en(), tc(seq=1739 + gap), same_number_numbering=False)
    assert hit.points == points


def test_2005_files_share_the_number_with_c_added() -> None:
    e = en(seq=110, old_style=True)
    t = tc(seq=110, old_style=True, c_suffix=True)
    hit = sequence_signal(e, t, same_number_numbering=True)
    assert (hit.points, hit.kind) == (4, "same_number_c")


def test_nearby_numbers_are_no_evidence_in_same_number_numbering() -> None:
    # In a folder numbered the 2005 way, TC 111_c belongs to EN 111, not to EN 110.
    e = en(seq=110, old_style=True)
    t = tc(seq=111, old_style=True, c_suffix=True)
    assert sequence_signal(e, t, same_number_numbering=True).kind == "none"


def test_c_suffix_with_plus_one_numbering_is_a_normal_plus_one() -> None:
    # 2015 `ltn…_c` files: Chinese file 50 follows English file 49.
    e = en(seq=49, old_style=True)
    t = tc(seq=50, old_style=True, c_suffix=True)
    assert sequence_signal(e, t, same_number_numbering=False).kind == "plus_one"


def test_different_folders_have_no_sequence_relation() -> None:
    other_day = datetime(2026, 10, 29, 22, 52)
    assert file_relation(en(), tc(when=other_day), same_number_numbering=False) is None
    assert sequence_signal(en(), tc(when=other_day), same_number_numbering=False).points == 0


def test_documents_without_file_numbers_have_no_sequence_relation() -> None:
    assert file_relation(en(seq=None), tc(seq=None), same_number_numbering=False) is None


def test_neutral_scoring_gives_every_candidate_the_proximity_score() -> None:
    adjacent = sequence_signal(en(seq=910), tc(seq=911), same_number_numbering=False, neutral=True)
    farther = sequence_signal(en(seq=910), tc(seq=913), same_number_numbering=False, neutral=True)
    assert (adjacent.points, farther.points) == (2, 2)
    assert adjacent.kind == farther.kind == "proximity"


def test_pre_2007_folders_are_assumed_old_style_without_evidence() -> None:
    day = datetime(2006, 3, 1)
    docs = [make_doc(Lang.EN, 5, day, old_style=True), make_doc(Lang.TC, 9, day, old_style=True)]
    assert numbering_uses_same_number({day.date(): docs}) == {day.date(): True}


def test_numbering_scheme_is_detected_per_folder() -> None:
    day = datetime(2005, 11, 28)
    old = [
        make_doc(Lang.EN, 110, day, old_style=True),
        make_doc(Lang.TC, 110, day, old_style=True, c_suffix=True),
        make_doc(Lang.EN, 111, day, old_style=True),
        make_doc(Lang.TC, 111, day, old_style=True, c_suffix=True),
    ]
    modern_day = datetime(2015, 6, 3)
    modern = [
        make_doc(Lang.EN, 910, modern_day, old_style=True),
        make_doc(Lang.TC, 912, modern_day, old_style=True, c_suffix=True),
    ]
    result = numbering_uses_same_number({day.date(): old, modern_day.date(): modern})
    assert result == {day.date(): True, modern_day.date(): False}


# --- S4 --------------------------------------------------------------------------------


def test_news_id_one_after() -> None:
    assert news_id_signal(en(news_id=100), tc(news_id=101)).points == 1


def test_news_id_not_one_after() -> None:
    assert news_id_signal(en(news_id=100), tc(news_id=105)) is None
    assert news_id_signal(en(news_id=100), tc(news_id=99)) is None


# --- S6 --------------------------------------------------------------------------------


def test_title_numbers_keep_long_numbers_only() -> None:
    assert title_numbers("Notice of 2026 AGM, Rule 22, HK$1,500,000.50 and Form 8-K") == {
        "2026",
        "1500000.50",
    }


def test_full_width_digits_are_folded() -> None:
    assert title_numbers("２０２６年股東週年大會通告") == {"2026"}


def test_agreeing_title_numbers() -> None:
    hit = title_number_signal(en(title="2026 Interim results"), tc(title="2026年中期業績"))
    assert hit is not None
    assert (hit.points, hit.kind, hit.values) == (1, "agree", ("2026",))


def test_a_subset_of_numbers_still_agrees() -> None:
    e = en(title="Results for the year ended 31 December 2025, announced 2026")
    t = tc(title="截至2025年12月31日止年度之業績")
    hit = title_number_signal(e, t)
    assert hit is not None and hit.points == 1


def test_conflicting_title_numbers() -> None:
    hit = title_number_signal(en(title="2025 Annual report"), tc(title="2024年報"))
    assert hit is not None
    assert (hit.points, hit.kind) == (-2, "conflict")


def test_titles_without_long_numbers_give_no_signal() -> None:
    assert (
        title_number_signal(en(title="Next Day Disclosure Return"), tc(title="翌日披露報表"))
        is None
    )
    assert title_number_signal(en(title="2026 Interim results"), tc(title="中期業績")) is None


def test_partly_overlapping_numbers_are_neutral() -> None:
    assert title_number_signal(en(title="2025 and 2026"), tc(title="2026 and 2027")) is None


# --- hard conflicts ----------------------------------------------------------------------


def test_disjoint_categories_and_title_numbers_are_hard_conflicts() -> None:
    e, t = en(categories=("1",), title="2025 report"), tc(categories=("2",), title="2024報告")
    hits = [category_signal(e, t), title_number_signal(e, t)]
    assert hard_conflicts(e, t, [h for h in hits if h]) == ("categories_disjoint", "title_numbers")


def test_differing_flags_are_a_hard_conflict() -> None:
    e, t = en(flags=frozenset({Flag.CANCELLED})), tc()
    assert hard_conflicts(e, t, []) == ("flags_differ",)
    assert hard_conflicts(e, tc(flags=frozenset({Flag.CANCELLED})), []) == ()


def test_custom_config_changes_the_weights() -> None:
    cfg = PairingConfig(same_minute=5)
    assert time_signal(en(), tc(), cfg).points == 5
