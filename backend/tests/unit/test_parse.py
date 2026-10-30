from datetime import date, datetime
from typing import Any

import pytest

from app.domain.models import Flag, Lang
from app.domain.timeutil import HKT
from app.hkex.parse import (
    RowError,
    has_chinese_suffix,
    parse_category_text,
    parse_file_path,
    parse_row,
)


def row(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "FILE_INFO": "84KB",
        "NEWS_ID": "12386841",
        "SHORT_TEXT": "Next Day Disclosure Returns - [Others]<br/>",
        "TOTAL_COUNT": "2",
        "DOD_WEB_PATH": "",
        "STOCK_NAME": "ZAI LAB",
        "TITLE": "Next Day Disclosure Return",
        "FILE_TYPE": "PDF",
        "DATE_TIME": "28/10/2026 22:52",
        "LONG_TEXT": "Next Day Disclosure Returns - [Others]",
        "STOCK_CODE": "09688",
        "FILE_LINK": "/listedco/listconews/sehk/2026/1028/2026102801739.pdf",
    }
    return {**base, **overrides}


def test_parses_a_normal_english_row() -> None:
    doc = parse_row(row(), Lang.EN)
    assert doc.lang is Lang.EN
    assert doc.release_at == datetime(2026, 10, 28, 22, 52, tzinfo=HKT)
    assert doc.stock_codes == ("09688",)
    assert doc.stock_names == ("ZAI LAB",)
    assert doc.title == "Next Day Disclosure Return"
    assert doc.file_type == "PDF"
    assert doc.size_label == "84KB"
    assert doc.news_id == "12386841"
    assert doc.folder_date == date(2026, 10, 28)
    assert doc.seq == 1739
    assert not doc.is_stub
    assert doc.flags == frozenset()
    assert (
        doc.source_url
        == "https://www1.hkexnews.hk/listedco/listconews/sehk/2026/1028/2026102801739.pdf"
    )


def test_parses_a_chinese_row() -> None:
    doc = parse_row(
        row(
            TITLE="翌日披露報表",
            LONG_TEXT="翌日披露報表 - [其他]",
            NEWS_ID="12386842",
            FILE_LINK="/listedco/listconews/sehk/2026/1028/2026102801740_c.pdf",
        ),
        Lang.TC,
    )
    assert doc.lang is Lang.TC
    assert doc.seq == 1740
    assert doc.title == "翌日披露報表"


def test_unescapes_collapses_whitespace_and_normalises_to_nfc() -> None:
    doc = parse_row(
        row(TITLE="  Notice &amp;  Form A \n of　Meeting ", LONG_TEXT="Circulars &#x2f; Other"),
        Lang.EN,
    )
    assert doc.title == "Notice & Form A of Meeting"
    assert doc.category_text == "Circulars / Other"
    decomposed = parse_row(row(TITLE="Café"), Lang.EN)
    assert decomposed.title == "Café"


def test_tolerates_nulls_and_numbers_in_string_fields() -> None:
    doc = parse_row(
        row(NEWS_ID=12386841, FILE_INFO=None, LONG_TEXT=None, SHORT_TEXT=None, TITLE=None), Lang.EN
    )
    assert doc.news_id == "12386841"
    assert doc.size_label == ""
    assert doc.category_text == ""
    assert doc.title == ""
    assert doc.category_codes == ()


def test_stock_code_numbers_are_padded_and_multi_codes_split() -> None:
    doc = parse_row(row(STOCK_CODE="00700<br/>80700", STOCK_NAME="TENCENT<br/>TENCENT-R"), Lang.EN)
    assert doc.stock_codes == ("00700", "80700")
    assert doc.stock_names == ("TENCENT", "TENCENT-R")
    assert parse_row(row(STOCK_CODE=5), Lang.EN).stock_codes == ("00005",)
    assert parse_row(row(STOCK_CODE="00005<BR>00006"), Lang.EN).stock_codes == ("00005", "00006")


@pytest.mark.parametrize("missing", ["FILE_LINK", "DATE_TIME", "NEWS_ID"])
def test_rows_without_identity_are_rejected_not_guessed(missing: str) -> None:
    with pytest.raises(RowError, match=missing):
        parse_row(row(**{missing: ""}), Lang.EN)


def test_bad_date_is_a_row_error() -> None:
    with pytest.raises(RowError, match="DATE_TIME"):
        parse_row(row(DATE_TIME="yesterday"), Lang.EN)


@pytest.mark.parametrize(
    ("path", "folder", "seq"),
    [
        ("/listedco/listconews/sehk/2026/1028/2026102801739.pdf", date(2026, 10, 28), 1739),
        ("/listedco/listconews/sehk/2026/1028/2026102801740_c.pdf", date(2026, 10, 28), 1740),
        ("/listedco/listconews/sehk/2026/1023/2026102301071_c.htm", date(2026, 10, 23), 1071),
        ("/listedco/listconews/sehk/2005/1128/ltn20051128110_c.pdf", date(2005, 11, 28), 110),
        ("/listedco/listconews/SEHK/2008/1120/LTN20081120321.pdf", date(2008, 11, 20), 321),
        ("/listedco/listconews/sehk/2008/1120/00705_439528/EWP127.pdf", date(2008, 11, 20), None),
        ("/listedco/listconews/sehk/dod/en.html", None, None),
        ("/listedco/listconews/sehk/dod/tc.html", None, None),
        # GEM issuers (08xxx) use the same scheme under /gem/ (research notes, Phase 2.4 findings).
        ("/listedco/listconews/gem/2026/0430/2026043004744.pdf", date(2026, 4, 30), 4744),
        ("/listedco/listconews/gem/2026/0402/2026040201183_c.pdf", date(2026, 4, 2), 1183),
        ("/listedco/listconews/GEM/2026/0402/2026040201183_c.pdf", date(2026, 4, 2), 1183),
    ],
)
def test_parse_file_path_handles_every_observed_shape(
    path: str, folder: date | None, seq: int | None
) -> None:
    assert parse_file_path(path) == (folder, seq)


def test_chinese_suffix_detection() -> None:
    assert has_chinese_suffix("/listedco/listconews/sehk/2026/1028/2026102801740_c.pdf")
    assert has_chinese_suffix("/listedco/listconews/sehk/2005/1128/ltn20051128110_c.pdf")
    assert has_chinese_suffix("/listedco/listconews/sehk/2026/1023/2026102301071_c.htm")
    assert not has_chinese_suffix("/listedco/listconews/sehk/2026/1028/2026102801739.pdf")
    assert not has_chinese_suffix("/listedco/listconews/sehk/2026/1028/abc_c_def.pdf")


@pytest.mark.parametrize(
    ("file_type", "path", "expected"),
    [
        ("PDF", "/x/2026/1028/2026102801739.pdf", "PDF"),
        ("", "/listedco/listconews/sehk/2005/0812/ltn20050812073.htm", "HTM"),
        ("doc", "/listedco/listconews/sehk/2005/0812/ltn20050812074.doc", "DOC"),
    ],
)
def test_file_type_falls_back_to_the_extension(file_type: str, path: str, expected: str) -> None:
    assert parse_row(row(FILE_TYPE=file_type, FILE_LINK=path), Lang.EN).file_type == expected


# --- stubs (research notes §5, verified titles) ---

EN_STUB = (
    "An announcement has just been published by the issuer in the Chinese section of this website, "
    "a corresponding version of which may or may not be published in this section"
)
TC_STUB = "發行人剛在本網站英文版面發布一項公告，相應中文版本或會／或不會在本版面發布。"


def test_english_stub_is_detected_by_title() -> None:
    doc = parse_row(
        row(
            TITLE=EN_STUB,
            FILE_TYPE="HTM",
            FILE_INFO="1KB",
            FILE_LINK="/listedco/listconews/sehk/2026/1030/2026103000899.htm",
        ),
        Lang.EN,
    )
    assert doc.is_stub


def test_chinese_stub_is_detected_by_title() -> None:
    doc = parse_row(
        row(
            TITLE=TC_STUB,
            FILE_TYPE="HTM",
            FILE_INFO="1KB",
            FILE_LINK="/listedco/listconews/sehk/2026/1023/2026102301071_c.htm",
        ),
        Lang.TC,
    )
    assert doc.is_stub


def test_stub_detection_survives_case_and_spacing_changes() -> None:
    assert parse_row(row(TITLE="  " + EN_STUB.upper().replace(" ", "  ")), Lang.EN).is_stub


def test_real_web_page_entries_are_not_stubs() -> None:
    doc = parse_row(
        row(
            TITLE="EXCHANGE NOTICE - TRADING HALT",
            FILE_TYPE="HTM",
            FILE_INFO="1KB",
            FILE_LINK="/listedco/listconews/sehk/2015/0519/ltn20150519057.htm",
        ),
        Lang.EN,
    )
    assert not doc.is_stub


def test_a_stub_title_is_only_a_stub_in_its_own_section() -> None:
    assert not parse_row(row(TITLE=EN_STUB), Lang.TC).is_stub
    assert not parse_row(row(TITLE=TC_STUB), Lang.EN).is_stub


# --- category text and flags ---


def test_category_with_parent_and_one_child() -> None:
    p = parse_category_text("Next Day Disclosure Returns - [Share Buyback]")
    assert (p.prefix, p.parent, p.children) == (
        "",
        "Next Day Disclosure Returns",
        ("Share Buyback",),
    )


def test_spaced_slash_separates_categories_and_unspaced_slash_stays_in_a_name() -> None:
    # Raw HKEX text escapes every slash as &#x2f;; only the separator has spaces around it.
    p = parse_category_text("Circulars - [Notice of EGM/SGM / Interim/Half-Year Report]")
    assert p.children == ("Notice of EGM/SGM", "Interim/Half-Year Report")
    q = parse_category_text(
        "Announcements and Notices - [Placing / Issue of Shares under a General Mandate]"
    )
    assert q.children == ("Placing", "Issue of Shares under a General Mandate")


def test_category_with_several_children_splits_on_spaced_slash_only() -> None:
    p = parse_category_text(
        "Announcements and Notices - [Group Restructuring or Scheme of Arrangement / Privatisation/Withdrawal]"
    )
    assert p.children == (
        "Group Restructuring or Scheme of Arrangement",
        "Privatisation/Withdrawal",
    )


def test_category_without_children() -> None:
    p = parse_category_text("Monthly Returns")
    assert (p.prefix, p.parent, p.children) == ("", "Monthly Returns", ())


def test_empty_category_is_empty() -> None:
    p = parse_category_text("")
    assert (p.prefix, p.parent, p.children) == ("", "", ())


@pytest.mark.parametrize(
    ("text", "prefix", "parent"),
    [
        (
            "(Cancelled and Reissued) Takeovers Code - dealing disclosures",
            "Cancelled and Reissued",
            "Takeovers Code - dealing disclosures",
        ),
        (
            "(Headline Revised) Announcements and Notices - [Inside Information / Resumption]",
            "Headline Revised",
            "Announcements and Notices",
        ),
        (
            "(Cancelled [Incorrect Submission]) Announcements and Notices - [Other]",
            "Cancelled [Incorrect Submission]",
            "Announcements and Notices",
        ),
        (
            "(取消 - 標題已被取代及更換) 公告及通告 - [內幕消息]",
            "取消 - 標題已被取代及更換",
            "公告及通告",
        ),
        (
            "(此文件已經作廢，經修訂文件已另行發出) 合併守則 - 交易披露",
            "此文件已經作廢，經修訂文件已另行發出",
            "合併守則 - 交易披露",
        ),
        (
            "(修改後標題) 公告及通告 - [內幕消息 / 復牌]",
            "修改後標題",
            "公告及通告",
        ),
    ],
)
def test_category_prefixes_are_split_off(text: str, prefix: str, parent: str) -> None:
    p = parse_category_text(text)
    assert (p.prefix, p.parent) == (prefix, parent)


@pytest.mark.parametrize(
    ("lang", "category", "flags"),
    [
        (
            Lang.EN,
            "(Cancelled and Reissued) Takeovers Code - dealing disclosures",
            {Flag.CANCELLED},
        ),
        (
            Lang.EN,
            "(Cancelled since Headlines Superseded and Replaced) Announcements and Notices - [Inside Information]",
            {Flag.CANCELLED},
        ),
        (
            Lang.EN,
            "(Cancelled [Incorrect Submission]) Announcements and Notices - [Other]",
            {Flag.CANCELLED},
        ),
        (
            Lang.EN,
            "(Headline Revised) Announcements and Notices - [Inside Information / Resumption]",
            {Flag.HEADLINES_REVISED},
        ),
        (
            Lang.EN,
            "(Headlines Revised) Announcements and Notices - [Change in Directors &#x2f; Other]",
            {Flag.HEADLINES_REVISED},
        ),
        (
            Lang.TC,
            "(修改後標題) 公告及通告 - [內幕消息 &#x2f; 復牌]",
            {Flag.HEADLINES_REVISED},
        ),
        (Lang.TC, "(取消 - 標題已被取代及更換) 公告及通告 - [內幕消息]", {Flag.CANCELLED}),
        (Lang.TC, "(此文件已經作廢，經修訂文件已另行發出) 合併守則 - 交易披露", {Flag.CANCELLED}),
        (Lang.EN, "Announcements and Notices - [Other]", set()),
    ],
)
def test_flags_come_from_category_prefix(lang: Lang, category: str, flags: set[Flag]) -> None:
    assert parse_row(row(LONG_TEXT=category), lang).flags == frozenset(flags)


def test_revised_flag_comes_from_english_title_prefix() -> None:
    assert Flag.REVISED in parse_row(row(TITLE="(Revised) Annual Report 2025"), Lang.EN).flags
    assert Flag.REVISED not in parse_row(row(TITLE="Revised Annual Report 2025"), Lang.EN).flags


@pytest.mark.parametrize(
    ("title", "revised"),
    [
        ("(經修訂) 董事名單與其角色和職能", True),
        ("(經修訂)翌日披露報表", True),
        ("經修訂年報", False),
        ("建議採納第三次經修訂及重列之組織章程大綱及細則", False),
    ],
)
def test_revised_flag_comes_from_chinese_title_prefix(title: str, revised: bool) -> None:
    assert (Flag.REVISED in parse_row(row(TITLE=title), Lang.TC).flags) is revised


def test_a_chinese_cancelled_marker_is_not_a_revised_flag() -> None:
    doc = parse_row(
        row(LONG_TEXT="(此文件已經作廢，經修訂文件已另行發出) 合併守則 - 交易披露"), Lang.TC
    )
    assert doc.flags == frozenset({Flag.CANCELLED})


def test_unrecognised_prefix_is_kept_so_the_matcher_can_see_it() -> None:
    doc = parse_row(row(LONG_TEXT="(Some New Marker) Announcements and Notices - [Other]"), Lang.EN)
    assert doc.category_prefix == "Some New Marker"
    assert doc.flags == frozenset()
