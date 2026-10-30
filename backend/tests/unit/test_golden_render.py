"""Terminal output for the golden helper: Chinese text is two columns wide, so padding must know."""

from datetime import datetime

from app.domain.models import Lang
from app.domain.timeutil import HKT
from app.pairing.models import Announcement, Rival, SingleReason, Status
from tests.golden.render import (
    announcement_table,
    clip_to_width,
    display_width,
    entry_table,
    figures_line,
    side_by_side,
)
from tests.golden.schema import CaseType, DocRef, Entry, Proposal, Truth
from tests.support import make_doc

WHEN = datetime(2026, 10, 28, 22, 52, tzinfo=HKT)


def test_ascii_is_one_column_per_character() -> None:
    assert display_width("Results") == 7


def test_chinese_characters_and_full_width_digits_are_two_columns() -> None:
    assert display_width("業績") == 4
    assert display_width("２０２６") == 8


def test_combining_marks_take_no_column() -> None:
    assert display_width("é") == 1


def test_clip_leaves_short_text_alone() -> None:
    assert clip_to_width("abc", 10) == "abc"


def test_clip_cuts_with_an_ellipsis_inside_the_width() -> None:
    clipped = clip_to_width("abcdefghij", 6)
    assert clipped == "abcde…" and display_width(clipped) == 6


def test_clip_never_splits_a_wide_character() -> None:
    clipped = clip_to_width("業績公告業績公告", 7)
    assert display_width(clipped) <= 7 and clipped.endswith("…")
    assert clipped == "業績公…"


def test_clip_to_a_tiny_width_still_fits() -> None:
    assert display_width(clip_to_width("業績", 1)) <= 1
    assert clip_to_width("abc", 0) == ""


def test_side_by_side_lines_all_have_the_same_display_width() -> None:
    lines = side_by_side(["Annual results 2026", "second"], ["全年業績 2026", "二", "三"], width=24)
    assert len(lines) == 3
    assert {display_width(line) for line in lines} == {2 * 24 + 3}


def test_side_by_side_marks_the_columns_and_pads_the_short_side() -> None:
    lines = side_by_side(["a"], ["b", "c"], width=4)
    assert lines[0].startswith("a   ") and "│" in lines[0] and lines[0].rstrip().endswith("b")
    assert lines[1].lstrip().startswith("│") or "│" in lines[1]
    assert lines[1].rstrip().endswith("c")


def test_side_by_side_clips_long_lines() -> None:
    lines = side_by_side(["x" * 50], ["y" * 50], width=10)
    assert "…" in lines[0] and display_width(lines[0]) == 23


def test_figures_line_lists_the_most_common_figures_first() -> None:
    from collections import Counter

    line = figures_line(Counter({"2026": 5, "28": 2, "1,000": 1, "50": 2}), limit=3)
    assert line == "2026×5  28×2  50×2  (+1 more)"


def test_figures_line_of_nothing_says_so() -> None:
    from collections import Counter

    assert figures_line(Counter()) == "no figures"


# --- the announcement table -----------------------------------------------------------------


def en(seq: int) -> object:
    return make_doc(Lang.EN, seq, WHEN, news_id=seq, title="Annual Results")


def tc(seq: int) -> object:
    return make_doc(Lang.TC, seq, WHEN, news_id=seq, c_suffix=True, title="全年業績")


def test_the_table_has_one_numbered_row_per_announcement_in_the_order_given() -> None:
    a = Announcement(
        id="a",
        status=Status.MATCHED,
        release_at=WHEN,
        en=en(1739),
        tc=tc(1740),
        score=14,  # type: ignore[arg-type]
    )
    b = Announcement(
        id="b",
        status=Status.EN_ONLY,
        release_at=WHEN,
        en=en(1671),  # type: ignore[arg-type]
        reason=SingleReason.STUB_IN_OTHER_SECTION,
    )
    lines = announcement_table([a, b], {"a": ("ordinary",), "b": ("en_only_stub",)}, width=100)
    assert lines[0].split()[:2] == ["#", "released"]
    assert lines[1].lstrip().startswith("1 ") and "2026-10-28 22:52" in lines[1]
    assert lines[2].lstrip().startswith("2 ")
    assert "matched" in lines[1] and "en_only" in lines[2]
    assert "1739" in lines[1] and "1740" in lines[1]
    assert "1671" in lines[2] and "-" in lines[2].split("en_only")[1][:20]


def test_the_table_shows_case_types_and_titles() -> None:
    a = Announcement(
        id="a",
        status=Status.CHECK,
        release_at=WHEN,
        en=en(1),
        tc=tc(2),  # type: ignore[arg-type]
        rivals=(Rival(document=tc(3), score=5),),  # type: ignore[arg-type]
    )
    (header, row) = announcement_table([a], {"a": ("ordinary", "several_same_day")}, width=120)
    assert "ordinary,several_same_day" in row
    assert "Annual Results" in row
    assert "rivals 1" in row
    assert header


def test_a_long_title_is_clipped_to_the_width() -> None:
    a = Announcement(
        id="a",
        status=Status.MATCHED,
        release_at=WHEN,
        en=make_doc(Lang.EN, 1, WHEN, title="T" * 300),
        tc=make_doc(Lang.TC, 2, WHEN, c_suffix=True),
    )
    for line in announcement_table([a], {"a": ("ordinary",)}, width=90):
        assert display_width(line) <= 90


# --- the entry index ---------------------------------------------------------------------------


def make_entry(
    eid: str,
    *,
    verified: bool = False,
    status: str = "matched",
    tc: bool = True,
    title: str = "Annual Results",
) -> Entry:
    en = DocRef(news_id="1", path="/a.pdf", title=title, released="2026-10-28 22:52")
    ref_tc = DocRef(news_id="2", path="/a_c.pdf", title="全年業績", released="2026-10-28 22:52")
    truth = Truth(en=en, tc=ref_tc) if tc else Truth(tc=ref_tc, absent="stub")
    return Entry(
        id=eid,
        verified=verified,
        stock_code="09688",
        stock_id=1,
        stock_name="ZAI LAB",
        scenario="s",
        case_types=[CaseType.ORDINARY, CaseType.SEVERAL_SAME_DAY],
        truth=truth,
        proposal=Proposal(status=status),
    )


def test_the_index_has_a_header_and_one_line_per_entry_in_order() -> None:
    lines = entry_table([make_entry("09688-1"), make_entry("09688-2", verified=True)], width=120)
    assert len(lines) == 3
    assert lines[0].split()[:3] == ["verified", "id", "proposed"]
    assert "09688-1" in lines[1] and "09688-2" in lines[2]


def test_the_index_marks_verified_entries_and_shows_the_matchers_proposal() -> None:
    lines = entry_table(
        [make_entry("a-1", verified=True), make_entry("a-2", status="check")], width=120
    )
    assert lines[1].lstrip().startswith("yes") and "matched" in lines[1]
    assert lines[2].lstrip().startswith("no") and "check" in lines[2]


def test_the_index_shows_types_and_the_english_title_or_the_chinese_one() -> None:
    lines = entry_table([make_entry("a-1"), make_entry("a-2", tc=False)], width=140)
    assert "ordinary,several_same_day" in lines[1] and "Annual Results" in lines[1]
    assert "全年業績" in lines[2]


def test_no_index_line_is_wider_than_the_terminal() -> None:
    lines = entry_table([make_entry("a-1", title="T" * 300)], width=100)
    assert all(display_width(line) <= 100 for line in lines)


def test_an_empty_index_is_just_the_header() -> None:
    assert len(entry_table([], width=100)) == 1
