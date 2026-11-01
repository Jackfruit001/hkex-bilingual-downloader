"""Filenames (SPEC §5): the pipeline, the limits, collisions, ZIP names and the header."""

import re
from datetime import UTC, date, datetime
from random import Random
from urllib.parse import unquote

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pathvalidate import is_valid_filename

from app.config import NAMING
from app.domain.models import Document, Lang
from app.domain.timeutil import HKT
from app.naming.filenames import (
    build_filename,
    bulk_zip_name,
    content_disposition,
    filename_for,
    name_documents,
    pair_zip_name,
    sanitize_given_name,
    slugify,
)
from tests.conftest import recorded_documents
from tests.support import make_doc

EN, TC = Lang.EN, Lang.TC


def at(day: str, hour: int = 12, minute: int = 0) -> datetime:
    y, m, d = (int(x) for x in day.split("-"))
    return datetime(y, m, d, hour, minute, tzinfo=HKT)


# --- the SPEC examples --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("lang", "day", "title", "expected"),
    [
        (
            EN,
            "2026-10-15",
            "Appointment of Director",
            "EN_2026-10-15-00700-Appointment-of-Director.pdf",
        ),
        (TC, "2026-10-15", "委任董事", "TC_2026-10-15-00700-委任董事.pdf"),
        (
            EN,
            "2026-10-15",
            "OVERSEAS REGULATORY ANNOUNCEMENT - FORM 8-K",
            "EN_2026-10-15-00700-Overseas-Regulatory-Announcement-Form-8-K.pdf",
        ),
    ],
)
def test_the_spec_examples(lang: Lang, day: str, title: str, expected: str) -> None:
    assert build_filename(lang, at(day), "00700", title) == expected


# --- real titles (golden set and recorded searches), written out by hand ------------------------
# (language, publication day in Hong Kong, stock code, title as HKEXnews shows it, filename)

REAL: list[tuple[Lang, str, str, str, str]] = [
    # mixed-case English stays as published
    (EN, "2005-03-31", "00005", "Overseas Regulatory Announcement",
     "EN_2005-03-31-00005-Overseas-Regulatory-Announcement.pdf"),
    (EN, "2026-08-04", "00005", "Second Interim Dividend for 2026",
     "EN_2026-08-04-00005-Second-Interim-Dividend-for-2026.pdf"),
    (EN, "2015-01-23", "00013", "Inside Information - Exclusive Negotiations for Potential Acquisition of O2 UK",
     "EN_2015-01-23-00013-Inside-Information-Exclusive-Negotiations-for-Potential-Acquisition-of-O2-UK.pdf"),
    (EN, "2026-10-21", "01398", "Dividend Currency Election Form for 2026 Interim Dividend",
     "EN_2026-10-21-01398-Dividend-Currency-Election-Form-for-2026-Interim-Dividend.pdf"),
    (EN, "2026-10-28", "02318", "Announcement of Unaudited Results for the Nine Months Ended September 30, 2026",
     "EN_2026-10-28-02318-Announcement-of-Unaudited-Results-for-the-Nine-Months-Ended-September-30,-2026.pdf"),
    # all-caps English becomes Title Case
    (EN, "2026-07-31", "00005", "NOTICE OF REDEMPTION",
     "EN_2026-07-31-00005-Notice-of-Redemption.pdf"),
    (EN, "2026-07-30", "00005", "LIST OF DIRECTORS AND THEIR ROLE AND FUNCTION",
     "EN_2026-07-30-00005-List-of-Directors-and-Their-Role-and-Function.pdf"),
    (EN, "2026-07-31", "00005", "HSBC TO SELL ITS AUD36 BILLION AUSTRALIAN HOME AND PERSONAL LOAN PORTFOLIO TO BLACKSTONE",
     "EN_2026-07-31-00005-HSBC-to-Sell-Its-AUD36-Billion-Australian-Home-and-Personal-Loan-Portfolio-to-Blackstone.pdf"),
    (EN, "2015-01-23", "00013", "EXCHANGE NOTICE - TRADING HALT",
     "EN_2015-01-23-00013-Exchange-Notice-Trading-Halt.pdf"),
    (EN, "2026-10-20", "00941", "RESULTS FOR THE FIRST THREE QUARTERS OF 2026",
     "EN_2026-10-20-00941-Results-for-the-First-Three-Quarters-of-2026.pdf"),
    (EN, "2026-10-23", "01810", "DATE OF BOARD MEETING",
     "EN_2026-10-23-01810-Date-of-Board-Meeting.pdf"),
    (EN, "2026-04-30", "02372", "ANNUAL REPORT 2025",
     "EN_2026-04-30-02372-Annual-Report-2025.pdf"),
    (EN, "2026-04-27", "02658", "2025 ANNUAL REPORT",
     "EN_2026-04-27-02658-2025-Annual-Report.pdf"),
    (EN, "2026-10-27", "03690", "GRANT OF RESTRICTED SHARE UNITS",
     "EN_2026-10-27-03690-Grant-of-Restricted-Share-Units.pdf"),
    (EN, "2026-03-27", "08069", "PROPOSED SHARE CONSOLIDATION",
     "EN_2026-03-27-08069-Proposed-Share-Consolidation.pdf"),
    (EN, "2026-04-13", "08223", "RESIGNATION OF NON-EXECUTIVE DIRECTOR AND CHANGE OF COMPOSITION OF BOARD COMMITTEE",
     "EN_2026-04-13-08223-Resignation-of-Non-Executive-Director-and-Change-of-Composition-of-Board-Committee.pdf"),
    (EN, "2026-10-23", "09688", "INSIDE INFORMATION - UPDATE ON FIRST DATA FROM GLOBAL PHASE 1B CLINICAL TRIAL",
     "EN_2026-10-23-09688-Inside-Information-Update-on-First-Data-from-Global-Phase-1B-Clinical-Trial.pdf"),
    (EN, "2026-04-01", "06909", "(Revised) LIST OF DIRECTORS AND THEIR ROLES AND FUNCTIONS",
     "EN_2026-04-01-06909-(Revised)-List-of-Directors-and-Their-Roles-and-Functions.pdf"),
    (EN, "2014-07-07", "00013", "SHARE OPTION SCHEMES OF THE PORTFOLIO COMPANIES OF KINROT HOLDINGS L.P.",
     "EN_2014-07-07-00013-Share-Option-Schemes-of-the-Portfolio-Companies-of-Kinrot-Holdings-L.P.pdf"),
    # forbidden characters become word breaks
    (EN, "2015-04-29", "00013", "LETTER TO SHAREHOLDERS: 2015 ANNUAL GENERAL MEETING",
     "EN_2015-04-29-00013-Letter-to-Shareholders-2015-Annual-General-Meeting.pdf"),
    (EN, "2026-03-02", "00005", "DIRECTOR DECLARATION / SUBSIDIARY BOARD ROLE",
     "EN_2026-03-02-00005-Director-Declaration-Subsidiary-Board-Role.pdf"),
    # the title fits exactly (120 characters in all)
    (EN, "2026-10-07", "01810", "Monthly Return of Equity Issuer on Movements in Securities for the month ended 30 September 2026",
     "EN_2026-10-07-01810-Monthly-Return-of-Equity-Issuer-on-Movements-in-Securities-for-the-month-ended-30-September-2026.pdf"),
    (EN, "2015-05-15", "00013", "EXTENSION OF TIME FOR DESPATCH OF CIRCULAR IN RESPECT OF MAJOR TRANSACTION - ACQUISITION OF O2 UK",
     "EN_2015-05-15-00013-Extension-of-Time-for-Despatch-of-Circular-in-Respect-of-Major-Transaction-Acquisition-of-O2-UK.pdf"),
    # too long: cut at the last hyphen that fits
    (EN, "2005-03-31", "00005", "Circular (Scrip dividend scheme and payment of dividends in United States dollars, sterling or Hong Kong dollars)",
     "EN_2005-03-31-00005-Circular-(Scrip-dividend-scheme-and-payment-of-dividends-in-United-States-dollars,-sterling-or.pdf"),
    (EN, "2026-10-28", "03690", "ISSUANCE OF CNY4.5 BILLION 2.50% SENIOR NOTES DUE 2031 AND CNY3.5 BILLION 3.10% SENIOR NOTES DUE 2036",
     "EN_2026-10-28-03690-Issuance-of-CNY4.5-Billion-2.50%-Senior-Notes-Due-2031-and-CNY3.5-Billion-3.10%-Senior-Notes-Due.pdf"),
    (EN, "2026-10-23", "09688", "PRIVATE PLACEMENT OF AMERICAN DEPOSITARY SHARES AND ISSUANCE OF UNDERLYING SHARES UNDER GENERAL MANDATE",
     "EN_2026-10-23-09688-Private-Placement-of-American-Depositary-Shares-and-Issuance-of-Underlying-Shares-Under-General.pdf"),
    (EN, "2026-10-15", "00388",
     "Letter to Existing Registered Shareholders - (1) Publication of Circular dated 16 October 2026 containing Notice of the General Meeting and Proxy Form; (2) General Meeting of HKEX; and (3) Request for printed or electronic version of Corporate Communication(s)",
     "EN_2026-10-15-00388-Letter-to-Existing-Registered-Shareholders-(1)-Publication-of-Circular-dated-16-October-2026.pdf"),
    (EN, "2026-10-22", "00700",
     "NOTICE OF LISTING ON THE STOCK EXCHANGE OF HONG KONG LIMITED - US$1,300,000,000 6.10% Senior Notes Due 2036 and US$500,000,000 6.75% Senior Notes Due 2046 and CNY20,000,000,000 2.40% Senior Notes Due 2036 and CNY6,000,000,000 3.00% Senior Notes Due 2056 issued under the Global Medium Term Note Programme of Tencent Holdings Limited with Maximum Limit of US$30 Billion",
     "EN_2026-10-22-00700-NOTICE-OF-LISTING-ON-THE-STOCK-EXCHANGE-OF-HONG-KONG-LIMITED-US$1,300,000,000-6.10%-Senior-Notes.pdf"),
    (EN, "2026-10-02", "01299",
     "Publication of Pricing Supplement in relation to CNY1,000,000,000 2.88 per cent. Subordinated Dated Securities due 2036 (to be consolidated and form a single series with the CNY2,500,000,000 2.88 per cent. Subordinated Dated Securities due 2036 issued on 30 April 2026 and the CNY500,000,000 2.88 per cent. Subordinated Dated Securities due 2036 issued on 12 June 2026) (Stock code: 85121) under the US$18,000,000,000 Global Medium Term Note and Securities Programme of AIA Group Limited",
     "EN_2026-10-02-01299-Publication-of-Pricing-Supplement-in-relation-to-CNY1,000,000,000-2.88-per-cent.-Subordinated.pdf"),
    # Traditional Chinese: no Title Case, full-width punctuation stays
    (TC, "2005-03-31", "00005", "致股東信函",
     "TC_2005-03-31-00005-致股東信函.pdf"),
    (TC, "2005-03-31", "00005", "通函 (以股代息計劃及以美元、英鎊或港元支付股息)",
     "TC_2005-03-31-00005-通函-(以股代息計劃及以美元、英鎊或港元支付股息).pdf"),
    (TC, "2026-08-04", "00005", "2026年第二次股息",
     "TC_2026-08-04-00005-2026年第二次股息.pdf"),
    (TC, "2015-01-23", "00013", "交易所通告 - 短暫停牌",
     "TC_2015-01-23-00013-交易所通告-短暫停牌.pdf"),
    (TC, "2015-01-27", "00013", "根據《收購守則》規則22作出的交易披露",
     "TC_2015-01-27-00013-根據《收購守則》規則22作出的交易披露.pdf"),
    (TC, "2026-04-01", "06909", "(經修訂) 董事名單與其角色和職能",
     "TC_2026-04-01-06909-(經修訂)-董事名單與其角色和職能.pdf"),
    (TC, "2026-04-17", "08223", "(經修訂)翌日披露報表",
     "TC_2026-04-17-08223-(經修訂)翌日披露報表.pdf"),
    (TC, "2026-04-30", "08223", "2025 年報",
     "TC_2026-04-30-08223-2025-年報.pdf"),
    (TC, "2026-10-23", "09688", "內幕消息 - 關於zocilurtatug pelitecan全球1b 期臨床研究的首個數據的更新",
     "TC_2026-10-23-09688-內幕消息-關於zocilurtatug-pelitecan全球1b-期臨床研究的首個數據的更新.pdf"),
    (TC, "2026-10-28", "02318", "海外監管公告 - 中國平安保險（集團）股份有限公司第十三屆董事會第十六次會議決議公告",
     "TC_2026-10-28-02318-海外監管公告-中國平安保險（集團）股份有限公司第十三屆董事會第十六次會議決議公告.pdf"),
    # too long: the byte limit binds for Chinese (156 bytes for the title)
    (TC, "2026-10-15", "00388",
     "致現有登記股東之函件 – (1)日期為2026年10月16日的通函連同股東大會通告及代表委任表格的刊發; (2)香港交易所股東大會; 及(3)有關收取公司通訊的印刷本或電子版本的要求",
     "TC_2026-10-15-00388-致現有登記股東之函件-–-(1)日期為2026年10月16日的通函連同股東大會通告及代表委任表格的刊發;.pdf"),
    (TC, "2026-10-22", "00700",
     "根據騰訊控股有限公司最高限額為300億美元之全球中期票據計劃發行將於二零三六年到期的1,300,000,000美元6.10%優先票據及將於二零四六年到期的500,000,000美元6.75%優先票據及將於二零三六年到期的人民幣20,000,000,000元2.40%優先票據及將於二零五六年到期的人民幣6,000,000,000元3.00%優先票據刊發定價補充文件",
     "TC_2026-10-22-00700-根據騰訊控股有限公司最高限額為300億美元之全球中期票據計劃發行將於二零三六年到期的1,300,000,000美元6.10%優先票據.pdf"),
]  # fmt: skip


@pytest.mark.parametrize(
    ("lang", "day", "code", "title", "expected"),
    REAL,
    ids=[f"{r[0].value}-{r[2]}-{r[1]}-{i}" for i, r in enumerate(REAL)],
)
def test_real_titles(lang: Lang, day: str, code: str, title: str, expected: str) -> None:
    assert build_filename(lang, at(day), code, title) == expected


def test_there_are_at_least_thirty_real_titles() -> None:
    assert len(REAL) >= 30
    assert len({r[3] for r in REAL}) == len(REAL)


# --- the date is the Hong Kong date -------------------------------------------------------------


def test_the_date_is_the_hong_kong_date_not_the_utc_date() -> None:
    late_utc = datetime(2026, 10, 27, 17, 30, tzinfo=UTC)  # 28 October 01:30 in Hong Kong
    assert build_filename(EN, late_utc, "00700", "Notice").startswith("EN_2026-10-28-")
    early_hkt = datetime(2026, 10, 28, 0, 5, tzinfo=HKT)
    assert build_filename(EN, early_hkt, "00700", "Notice").startswith("EN_2026-10-28-")


def test_a_naive_datetime_is_refused() -> None:
    with pytest.raises(ValueError, match="time zone"):
        build_filename(EN, datetime(2026, 10, 28, 9, 0), "00700", "Notice")


@pytest.mark.parametrize("code", ["700", "0070", "007000", "ABCDE", "", "0070０"])
def test_the_code_must_be_five_digits(code: str) -> None:
    with pytest.raises(ValueError, match="stock code"):
        build_filename(EN, at("2026-10-28"), code, "Notice")


# --- the slug -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("title", "slug"),
    [
        ('Re: Notice <Draft> "A/B" | C? *', "Re-Notice-Draft-A-B-C"),
        ("back\\slash", "back-slash"),
        ("tab\there\nnew\x00line\x7f", "tab-here-new-line"),
        ("Smith & Sons, Ltd. (Hong Kong)'s Report", "Smith-&-Sons,-Ltd.-(Hong-Kong)'s-Report"),
        ("  ..__Hello World__..  ", "Hello-World"),
        ("Report.", "Report"),
        ("a - b -- c --- d", "a-b-c-d"),
        ("委任　董事", "委任-董事"),  # the ideographic space is a space
        ("全角：冒號？", "全角：冒號？"),  # full-width punctuation stays
        ("Smith &amp; Sons", "Smith-&-Sons"),  # HTML entities are unescaped
        ("Café", "Café"),  # NFC
        ("", ""),
        ("***", ""),
        ("...", ""),
    ],
)
def test_slugify(title: str, slug: str) -> None:
    assert slugify(title) == slug


@pytest.mark.parametrize("title", ["", "   ", "***", "...", '<>:"/\\|?*', "-._ "])
def test_an_empty_title_becomes_untitled(title: str) -> None:
    assert (
        build_filename(EN, at("2026-10-15"), "00700", title) == "EN_2026-10-15-00700-Untitled.pdf"
    )
    assert (
        build_filename(TC, at("2026-10-15"), "00700", title) == "TC_2026-10-15-00700-Untitled.pdf"
    )


def test_title_case_applies_to_english_titles_only() -> None:
    assert build_filename(EN, at("2026-10-15"), "00700", "NOTICE OF AGM").endswith(
        "Notice-of-AGM.pdf"
    )
    assert build_filename(TC, at("2026-10-15"), "00700", "NOTICE OF AGM").endswith(
        "NOTICE-OF-AGM.pdf"
    )


# --- the limits -----------------------------------------------------------------------------------


def core(name: str) -> str:
    """The title part of a filename: between `XX_YYYY-MM-DD-CODE-` and `.pdf`."""
    return name[len("EN_2026-10-15-00700-") : -len(".pdf")]


@pytest.mark.parametrize(("n", "kept"), [(95, 95), (96, 96), (97, 96), (400, 96)])
def test_the_character_limit_is_120_for_the_whole_name(n: int, kept: int) -> None:
    name = build_filename(EN, at("2026-10-15"), "00700", "a" * n)
    assert core(name) == "a" * kept
    assert len(name) == 20 + kept + 4 <= 120


@pytest.mark.parametrize(("n", "kept"), [(51, 51), (52, 52), (53, 52), (200, 52)])
def test_the_byte_limit_is_180_and_never_cuts_inside_a_character(n: int, kept: int) -> None:
    name = build_filename(TC, at("2026-10-15"), "00700", "字" * n)
    assert core(name) == "字" * kept
    assert len(name.encode()) == 20 + 3 * kept + 4 <= 180


def test_a_three_byte_character_that_does_not_fit_is_dropped_whole() -> None:
    # 1 ASCII byte + 52 characters would be 157 bytes; one over the 156-byte title budget.
    name = build_filename(TC, at("2026-10-15"), "00700", "a" + "字" * 60)
    assert core(name) == "a" + "字" * 51
    assert len(name.encode()) == 20 + 1 + 153 + 4


def test_a_cut_at_a_hyphen_does_not_leave_trailing_punctuation() -> None:
    title = "a" * 92 + ". " + "b" * 50  # the only hyphen follows the full stop
    assert core(build_filename(EN, at("2026-10-15"), "00700", title)) == "a" * 92


def test_a_cut_prefers_the_last_hyphen_that_fits() -> None:
    title = " ".join(["word"] * 40)  # words of 4 letters with a hyphen between: 5 characters each
    assert core(build_filename(EN, at("2026-10-15"), "00700", title)) == "-".join(["word"] * 19)


# --- the file name for a document ------------------------------------------------------------------


def test_filename_for_a_document_uses_its_own_language_date_and_title() -> None:
    en = make_doc(EN, 1739, at("2026-10-28", 22, 52), title="NEXT DAY DISCLOSURE RETURN")
    tc = make_doc(TC, 1740, at("2026-10-29", 0, 3), title="翌日披露報表")
    assert filename_for(en, "09688") == "EN_2026-10-28-09688-Next-Day-Disclosure-Return.pdf"
    assert filename_for(tc, "09688") == "TC_2026-10-29-09688-翌日披露報表.pdf"


# --- collisions -------------------------------------------------------------------------------------


def doc(
    lang: Lang,
    seq: int,
    minute: int = 0,
    day: str = "2026-10-15",
    title: str = "Next Day Disclosure Return",
) -> Document:
    return make_doc(lang, seq, at(day, 10, minute), title=title, news_id=seq)


def test_the_first_document_keeps_the_name_and_the_rest_are_numbered_in_publication_order() -> None:
    docs = [doc(EN, 30, 5), doc(EN, 10, 1), doc(EN, 20, 3)]  # deliberately out of order
    names = name_documents(docs, "00700")
    base = "EN_2026-10-15-00700-Next-Day-Disclosure-Return"
    assert [names[d.path] for d in sorted(docs, key=lambda x: x.seq or 0)] == [
        f"{base}.pdf",
        f"{base}-(2).pdf",
        f"{base}-(3).pdf",
    ]


def test_documents_in_the_same_minute_are_numbered_by_file_number() -> None:
    docs = [doc(EN, 12), doc(EN, 11)]
    names = name_documents(docs, "00700")
    assert names[docs[1].path].endswith("Return.pdf")
    assert names[docs[0].path].endswith("Return-(2).pdf")


def test_file_numbers_are_compared_as_numbers_not_as_text() -> None:
    # 2015 paths carry 3 or 4 digits (`ltn20150429999`, `ltn201504291000`): by text, 1000 < 999.
    when = at("2015-04-29", 19, 21)
    low = make_doc(EN, 999, when, old_style=True, title="Letter to Shareholders", news_id=1)
    high = make_doc(EN, 1000, when, old_style=True, title="Letter to Shareholders", news_id=2)
    names = name_documents([high, low], "00013")
    assert names[low.path].endswith("Shareholders.pdf")
    assert names[high.path].endswith("Shareholders-(2).pdf")


def test_names_do_not_depend_on_the_order_the_documents_are_given_in() -> None:
    docs = [doc(EN, n, n % 3) for n in range(1, 8)]
    assert name_documents(docs, "00700") == name_documents(list(reversed(docs)), "00700")


def test_two_languages_or_two_days_do_not_collide() -> None:
    docs = [doc(EN, 1), doc(TC, 2), doc(EN, 3, day="2026-10-16")]
    names = name_documents(docs, "00700")
    assert not any("(2)" in n for n in names.values())


def test_the_same_file_listed_twice_is_one_document() -> None:
    first = doc(EN, 1)
    again = first.model_copy(update={"news_id": "999"})  # a cancelled entry and its replacement
    assert name_documents([first, again], "00700") == {first.path: filename_for(first, "00700")}


def test_stubs_and_pages_that_are_not_pdfs_take_no_number() -> None:
    stub = make_doc(TC, 2, at("2026-10-15", 10), stub=True, title="Next Day Disclosure Return")
    page = make_doc(
        EN, 3, at("2026-10-15", 10), ext="htm", file_type="HTM", title="Next Day Disclosure Return"
    )
    real = doc(EN, 4)
    names = name_documents([stub, page, real], "00700")
    assert names == {real.path: "EN_2026-10-15-00700-Next-Day-Disclosure-Return.pdf"}


def test_a_number_still_fits_in_the_length_limits() -> None:
    long_title = "word " * 60
    docs = [doc(EN, n, n, title=long_title) for n in range(1, 4)]
    found = name_documents(docs, "00700")
    names = [found[d.path] for d in docs]  # in publication order
    assert len(set(names)) == 3
    assert all(len(n) <= 120 and len(n.encode()) <= 180 for n in names)
    assert not names[0].endswith(")" + ".pdf")
    assert names[1].endswith("-(2).pdf") and names[2].endswith("-(3).pdf")


def test_titles_that_only_differ_after_the_cut_are_still_told_apart() -> None:
    a = doc(EN, 1, 1, title="word " * 40 + "alpha")
    b = doc(EN, 2, 2, title="word " * 40 + "beta")
    names = name_documents([a, b], "00700")
    assert names[a.path] != names[b.path]


# --- names sent back by a client -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("given", "clean", "changed"),
    [
        (
            "EN_2026-10-15-00700-Appointment-of-Director.pdf",
            "EN_2026-10-15-00700-Appointment-of-Director.pdf",
            False,
        ),
        ("TC_2026-10-15-00700-委任董事.pdf", "TC_2026-10-15-00700-委任董事.pdf", False),
        ("../../etc/passwd", "etc-passwd.pdf", True),
        ("..\\..\\evil.pdf", "evil.pdf", True),
        ("report", "report.pdf", True),
        ("REPORT.PDF", "REPORT.pdf", True),
        ("my report.pdf", "my-report.pdf", True),
        ("a:b?c.pdf", "a-b-c.pdf", True),
        ("CON.pdf", "CON_.pdf", True),
        ("", "Untitled.pdf", True),
        (".pdf", "Untitled.pdf", True),
        ("   .pdf", "Untitled.pdf", True),
    ],
)
def test_a_name_from_a_client_is_cleaned_and_the_change_is_reported(
    given: str, clean: str, changed: bool
) -> None:
    assert sanitize_given_name(given) == (clean, changed)


def test_a_long_name_from_a_client_is_cut_to_the_limits() -> None:
    name, changed = sanitize_given_name("x" * 300 + ".pdf")
    assert changed and name == "x" * 116 + ".pdf"
    name, changed = sanitize_given_name("字" * 100 + ".pdf")
    assert changed and name == "字" * 58 + ".pdf" and len(name.encode()) == 178


# --- ZIP names --------------------------------------------------------------------------------------


def test_a_pair_zip_is_named_after_the_english_title() -> None:
    assert pair_zip_name(at("2026-10-15"), "00700", "Appointment of Director") == (
        "EN-TC_2026-10-15-00700-Appointment-of-Director.zip"
    )
    assert pair_zip_name(at("2026-10-15"), "00700", "NOTICE OF AGM") == (
        "EN-TC_2026-10-15-00700-Notice-of-AGM.zip"
    )


def test_a_pair_zip_falls_back_to_the_chinese_title() -> None:
    assert pair_zip_name(at("2026-10-15"), "00700", "委任董事", english=False) == (
        "EN-TC_2026-10-15-00700-委任董事.zip"
    )


def test_a_pair_zip_name_respects_the_limits() -> None:
    name = pair_zip_name(at("2026-10-15"), "00700", "word " * 100)
    assert len(name) <= 120 and len(name.encode()) <= 180 and name.endswith("-word.zip")
    name = pair_zip_name(at("2026-10-15"), "00700", "字" * 100, english=False)
    assert len(name.encode()) <= 180 and name.endswith("字.zip")


def test_a_bulk_zip_name() -> None:
    assert bulk_zip_name("00700", date(2026, 10, 1), date(2026, 10, 30)) == (
        "HKEX_00700_2026-10-01_to_2026-10-30.zip"
    )
    with pytest.raises(ValueError, match="stock code"):
        bulk_zip_name("700", date(2026, 10, 1), date(2026, 10, 30))


# --- the download header -----------------------------------------------------------------------------


def test_content_disposition_for_an_ascii_name() -> None:
    assert content_disposition("EN_2026-10-15-00700-Appointment-of-Director.pdf") == (
        'attachment; filename="EN_2026-10-15-00700-Appointment-of-Director.pdf"; '
        "filename*=UTF-8''EN_2026-10-15-00700-Appointment-of-Director.pdf"
    )


def test_content_disposition_for_a_chinese_name() -> None:
    assert content_disposition("TC_2026-10-15-00700-委任董事.pdf") == (
        'attachment; filename="TC_2026-10-15-00700-____.pdf"; '
        "filename*=UTF-8''TC_2026-10-15-00700-%E5%A7%94%E4%BB%BB%E8%91%A3%E4%BA%8B.pdf"
    )


def test_content_disposition_cannot_be_broken_out_of() -> None:
    hostile = 'a"b\\c/d\r\nSet-Cookie: x=1.pdf'
    header = content_disposition(hostile)
    assert "\r" not in header and "\n" not in header
    plain, star = header.split("; filename*=UTF-8''")
    assert plain.count('"') == 2 and "\\" not in plain  # only the two delimiting quotes
    assert not re.search(r"[^A-Za-z0-9%._~-]", star)  # everything else is percent-encoded
    assert unquote(star) == hostile


# --- every recorded title ---------------------------------------------------------------------------


def downloadable() -> list[Document]:
    return [
        d
        for d in recorded_documents()
        if d.path.lower().endswith(".pdf") and not d.is_stub and d.stock_codes
        and re.fullmatch(r"[0-9]{5}", d.stock_codes[0])
    ]  # fmt: skip


WINDOWS_RESERVED = re.compile(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\..*)?$", re.IGNORECASE)


def assert_safe(name: str) -> None:
    assert name.endswith((".pdf", ".zip"))
    assert not re.search(r'[<>:"/\\|?*\x00-\x1f]', name)
    assert not name.endswith((".", " "))
    assert not WINDOWS_RESERVED.match(name)
    assert is_valid_filename(name, platform="universal"), name
    assert (
        len(name) <= NAMING.max_filename_chars and len(name.encode()) <= NAMING.max_filename_bytes
    )


def test_every_recorded_title_gives_a_safe_filename() -> None:
    docs = downloadable()
    assert len(docs) > 5000 and len({(d.lang, d.title) for d in docs}) > 900
    for d in docs:
        name = filename_for(d, d.stock_codes[0])
        assert_safe(name)
        prefix = f"{'EN' if d.lang is EN else 'TC'}_{d.release_at.astimezone(HKT):%Y-%m-%d}-{d.stock_codes[0]}-"
        assert name.startswith(prefix) and len(name) > len(prefix) + len(".pdf")


def test_recorded_documents_of_one_stock_get_distinct_names() -> None:
    by_code: dict[str, list[Document]] = {}
    for d in downloadable():
        by_code.setdefault(d.stock_codes[0], []).append(d)
    assert len(by_code) >= 15
    for code, docs in by_code.items():
        names = name_documents(docs, code)
        assert len(names) == len({d.path for d in docs}), code
        assert len(set(names.values())) == len(names), code
        for name in names.values():
            assert_safe(name)


# --- properties -------------------------------------------------------------------------------------

_titles = st.text(max_size=400)
_when = st.datetimes(
    min_value=datetime(1999, 4, 1), max_value=datetime(2100, 1, 1), timezones=st.just(UTC)
)
_code = st.from_regex(r"[0-9]{5}", fullmatch=True)
_lang = st.sampled_from([EN, TC])


@given(_lang, _when, _code, _titles)
def test_any_title_gives_a_safe_deterministic_filename_with_the_prefix(
    lang: Lang, when: datetime, code: str, title: str
) -> None:
    name = build_filename(lang, when, code, title)
    assert_safe(name)
    prefix = f"{'EN' if lang is EN else 'TC'}_{when.astimezone(HKT):%Y-%m-%d}-{code}-"
    assert name.startswith(prefix) and name.endswith(".pdf")
    assert len(name) > len(prefix) + len(".pdf")  # never empty
    assert build_filename(lang, when, code, title) == name


@given(_titles)
def test_slugify_is_idempotent_and_free_of_spaces_and_forbidden_characters(title: str) -> None:
    slug = slugify(title)
    assert slugify(slug) == slug
    assert not re.search(r'[<>:"/\\|?*\x00-\x1f\s]', slug)
    assert slug == slug.strip("-._ ")


def expected_core(title: str) -> str:
    """SPEC §5 stated again, independently: the longest cut at a hyphen that fits, else a hard cut."""
    full = slugify(title) or NAMING.untitled

    def fits(body: str) -> bool:
        name = f"TC_2026-10-15-00700-{body}.pdf"
        return len(name) <= 120 and len(name.encode()) <= 180

    if fits(full):
        return full
    fitting = [
        full[:i].rstrip("-._ ") for i, c in enumerate(full) if c == "-" and i and fits(full[:i])
    ]
    if fitting:
        return fitting[-1]
    return max((full[:i].rstrip("-._ ") for i in range(1, len(full)) if fits(full[:i])), key=len)


@given(st.text(alphabet=st.sampled_from(list("字詞abcXYZ -._()")), max_size=300))
def test_a_long_title_is_cut_at_the_last_hyphen_that_fits_or_as_late_as_possible(
    title: str,
) -> None:
    name = build_filename(TC, datetime(2026, 10, 15, tzinfo=HKT), "00700", title)
    assert core(name) == expected_core(title)


@settings(max_examples=60)
@given(
    st.lists(
        st.tuples(
            _lang,
            st.integers(0, 59),
            st.sampled_from(["2026-10-15", "2026-10-16"]),
            st.sampled_from(["Notice", "Next Day Disclosure Return", "word " * 70, "委任董事"]),
        ),
        min_size=1,
        max_size=14,
    ),
    st.randoms(use_true_random=False),
)
def test_names_of_a_day_are_unique_safe_and_independent_of_input_order(
    rows: list[tuple[Lang, int, str, str]], rnd: Random
) -> None:
    docs = [
        doc(lang, seq, minute, day, title) for seq, (lang, minute, day, title) in enumerate(rows, 1)
    ]
    names = name_documents(docs, "00700")
    assert len(set(names.values())) == len(docs)
    for name in names.values():
        assert_safe(name)
    shuffled = docs[:]
    rnd.shuffle(shuffled)
    assert name_documents(shuffled, "00700") == names


@given(st.text(max_size=300))
def test_a_name_from_a_client_always_ends_up_safe(given_name: str) -> None:
    name, changed = sanitize_given_name(given_name)
    assert_safe(name)
    assert (name != given_name) == changed
    assert sanitize_given_name(name) == (name, False)
