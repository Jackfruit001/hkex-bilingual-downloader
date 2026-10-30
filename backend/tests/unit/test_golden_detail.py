"""The per-row detail the helper prints for Zarif: everything needed to decide, nothing hidden."""

from collections import Counter
from datetime import datetime
from pathlib import Path

from app.domain.models import Lang
from app.domain.timeutil import HKT
from app.pairing.content_check import TextStatus
from app.pairing.models import Announcement, Rival, SingleReason, Status
from tests.golden.draft import FileView, RowFiles
from tests.golden.render import display_width, row_detail
from tests.golden.schema import CaseType
from tests.golden.store import FileFacts
from tests.support import make_doc

WHEN = datetime(2026, 10, 28, 22, 52, tzinfo=HKT)
EN = make_doc(Lang.EN, 1739, WHEN, news_id=100, title="Annual Results")
TC = make_doc(Lang.TC, 1740, WHEN, news_id=101, c_suffix=True, title="全年業績")


def view(
    lang: Lang, news_id: str, sha: str, lines: tuple[str, ...], tokens: dict[str, int]
) -> FileView:
    return FileView(
        lang=lang,
        news_id=news_id,
        path=Path(f"/cache/{lang.value}_{news_id}.pdf"),
        facts=FileFacts(sha256=sha * 64, bytes=86016, tokens=tokens),
        text_status=TextStatus.OK,
        lines=lines,
        tokens=Counter(tokens),
    )


def pair(**kw: object) -> Announcement:
    return Announcement(
        id="100:101",
        status=Status.MATCHED,
        release_at=WHEN,
        en=EN,
        tc=TC,
        score=14,
        evidence=("Published together at 22:52 HKT.",),
        **kw,  # type: ignore[arg-type]
    )


def detail(a: Announcement, files: RowFiles | None = None, width: int = 100) -> str:
    return "\n".join(row_detail(3, a, (CaseType.ORDINARY,), "09688-100", files, width))


def test_the_header_names_the_row_the_entry_and_the_matchers_status() -> None:
    text = detail(pair())
    assert "row 3" in text and "09688-100" in text and "matched" in text and "score 14" in text
    assert "ordinary" in text


def test_both_documents_are_listed_with_time_file_number_news_id_and_title() -> None:
    text = detail(pair())
    assert "EN" in text and "TC" in text
    assert "2026-10-28 22:52" in text
    assert "1739" in text and "1740" in text and "news 100" in text and "news 101" in text
    assert "Annual Results" in text and "全年業績" in text


def test_the_matchers_evidence_and_the_source_links_are_shown() -> None:
    text = detail(pair())
    assert "Published together at 22:52 HKT." in text
    assert EN.source_url in text and TC.source_url in text


def test_rivals_are_listed_so_the_pair_can_be_doubted() -> None:
    rival = make_doc(Lang.TC, 1741, WHEN, news_id=103, c_suffix=True, title="另一份")
    text = detail(pair(rivals=(Rival(document=rival, score=5),)))
    assert "rivals" in text and "1741" in text and "score 5" in text


def test_a_single_language_row_says_why_and_links_the_notice() -> None:
    stub = make_doc(Lang.TC, 1740, WHEN, news_id=101, c_suffix=True, ext="htm", stub=True)
    a = Announcement(
        id="100:-",
        status=Status.EN_ONLY,
        release_at=WHEN,
        en=EN,
        reason=SingleReason.STUB_IN_OTHER_SECTION,
        stub=stub,
        score=None,
    )
    text = detail(a)
    assert "TC  none" in text and "notice" in text and stub.source_url in text


def test_without_files_it_says_nothing_was_fetched() -> None:
    assert "no PDFs fetched" in detail(pair())


def test_with_files_it_shows_hashes_figures_overlap_and_the_two_first_pages() -> None:
    tokens = {"2026": 3, "1234567": 1}
    files = RowFiles(
        en=view(Lang.EN, "100", "a", ("Annual results for 2026", "Revenue 1,234,567"), tokens),
        tc=view(Lang.TC, "101", "b", ("2026年全年業績", "收益 1,234,567"), tokens),
        containment=1.0,
        skipped=[],
    )
    text = detail(pair(), files, width=100)
    assert "sha256 aaaaaaaa" in text and "sha256 bbbbbbbb" in text
    assert "different files" in text
    assert "100% of the figures in the smaller set (4 figures compared)" in text
    assert "2026×3" in text
    assert "Annual results for 2026" in text and "2026年全年業績" in text
    assert "/cache/en_100.pdf" in text and "/cache/tc_101.pdf" in text


def test_identical_bytes_are_called_out() -> None:
    tokens = {"2026": 3}
    files = RowFiles(
        en=view(Lang.EN, "100", "a", ("x",), tokens),
        tc=view(Lang.TC, "101", "a", ("x",), tokens),
        containment=1.0,
        skipped=[],
    )
    assert "IDENTICAL" in detail(pair(), files)


def test_skipped_files_are_listed_with_their_reason() -> None:
    files = RowFiles(
        en=None, tc=None, containment=None, skipped=["EN 100: a web page entry, not fetched"]
    )
    text = detail(pair(), files)
    assert "skipped" in text and "a web page entry, not fetched" in text


def test_unreadable_text_is_flagged_rather_than_shown_as_no_figures() -> None:
    scanned = FileView(
        lang=Lang.EN,
        news_id="100",
        path=Path("/cache/en_100.pdf"),
        facts=FileFacts(sha256="c" * 64, bytes=10, tokens={}),
        text_status=TextStatus.UNAVAILABLE,
        lines=(),
        tokens=Counter(),
    )
    text = detail(pair(), RowFiles(en=scanned, tc=None, containment=None, skipped=[]))
    assert "unavailable" in text


def test_no_line_is_wider_than_the_terminal() -> None:
    long = "x" * 200
    files = RowFiles(
        en=view(Lang.EN, "100", "a", (long,), {"2026": 1}),
        tc=view(Lang.TC, "101", "b", ("全" * 100,), {"2026": 1}),
        containment=1.0,
        skipped=[],
    )
    a = pair().model_copy(update={"evidence": (long,)})
    for line in row_detail(1, a, (CaseType.ORDINARY,), "09688-100", files, 100):
        if "http" not in line and "/cache/" not in line:
            assert display_width(line) <= 100, line


def test_a_small_set_of_figures_is_called_weak_evidence() -> None:
    few = {"2026": 3}
    files = RowFiles(
        en=view(Lang.EN, "100", "a", ("x",), {"2026": 3, "28": 2, "50": 1, "60": 1, "70": 1}),
        tc=view(Lang.TC, "101", "b", ("y",), few),
        containment=1.0,
        skipped=[],
    )
    text = detail(pair(), files)
    assert "(3 figures compared)" in text
    assert "too few figures to rely on" in text


def test_enough_figures_carry_no_warning() -> None:
    many = {"2026": 3, "28": 2, "50": 1, "60": 1, "70": 1}
    files = RowFiles(
        en=view(Lang.EN, "100", "a", ("x",), many),
        tc=view(Lang.TC, "101", "b", ("y",), many),
        containment=1.0,
        skipped=[],
    )
    text = detail(pair(), files)
    assert "(8 figures compared)" in text
    assert "too few figures" not in text


def test_the_reason_the_text_is_unusable_is_shown_with_the_file() -> None:
    garbled = FileView(
        lang=Lang.TC,
        news_id="101",
        path=Path("/cache/tc_101.pdf"),
        facts=FileFacts(sha256="d" * 64, bytes=10, tokens={}),
        text_status=TextStatus.UNAVAILABLE,
        lines=(),
        tokens=Counter(),
        note="only 1.4% of the characters are Chinese; the PDF's text can't be decoded",
    )
    text = detail(pair(), RowFiles(en=None, tc=garbled, containment=None, skipped=[]))
    assert "TC text unavailable: only 1.4% of the characters are Chinese" in text
    assert "figures not compared" in text
