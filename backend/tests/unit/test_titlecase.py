"""Title Case for all-caps English titles (SPEC §5, D-004). Pure, so tested exhaustively."""

import re
from dataclasses import replace

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.config import NAMING
from app.naming.titlecase import is_mostly_upper, to_title_case

# --- when it applies ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("ANNUAL REPORT", True),
        ("Annual Report", False),
        ("Notice of AGM", False),
        ("ABCDEFGhij", True),  # exactly 70% of the letters are upper case
        ("ABCDEFghij", False),  # 60%
        ("委任董事", False),  # no ASCII letters at all
        ("2026", False),
        ("", False),
        ("自願性公告 - HMPL-760 研究", True),  # the ASCII letters are all upper case
    ],
)
def test_the_seventy_percent_rule_counts_ascii_letters_only(text: str, expected: bool) -> None:
    assert is_mostly_upper(text) is expected


@pytest.mark.parametrize(
    "title",
    [
        "Appointment of Director",
        "Notice of AGM",
        "HUTCHMED Announces Results",
        "ABCDEFghij",
        "委任董事",
        "2026年報",
        "",
    ],
)
def test_titles_that_are_not_mostly_upper_case_stay_as_published(title: str) -> None:
    assert to_title_case(title) == title


def test_as_published_mode_keeps_the_hkex_casing() -> None:
    cfg = replace(NAMING, title_case_mode="as_published")
    assert (
        to_title_case("OVERSEAS REGULATORY ANNOUNCEMENT", cfg) == "OVERSEAS REGULATORY ANNOUNCEMENT"
    )


# --- the rules ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        # the SPEC example
        (
            "OVERSEAS REGULATORY ANNOUNCEMENT - FORM 8-K",
            "Overseas Regulatory Announcement - Form 8-K",
        ),
        ("NOTICE OF ANNUAL GENERAL MEETING", "Notice of Annual General Meeting"),
        (
            "ANNOUNCEMENT OF THE ANNUAL RESULTS FOR THE YEAR ENDED 31 DECEMBER 2025",
            "Announcement of the Annual Results for the Year Ended 31 December 2025",
        ),
        ("SECOND INTERIM DIVIDEND FOR 2025", "Second Interim Dividend for 2025"),
        ("MAY 2028 NOTES", "May 2028 Notes"),  # a month is not a small word
    ],
)
def test_ordinary_words(title: str, expected: str) -> None:
    assert to_title_case(title) == expected


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("2025 AGM CIRCULAR", "2025 AGM Circular"),
        ("HSBC HOLDINGS PLC ANNOUNCES RESULTS", "HSBC Holdings PLC Announces Results"),
        (
            "EXTENSION OF TIME FOR ACQUISITION OF O2 UK",
            "Extension of Time for Acquisition of O2 UK",
        ),
        ("RESULTS OF THE CKH HOLDINGS EGM", "Results of the CKH Holdings EGM"),
        ("LICENCE AGREEMENT WITH GSK", "Licence Agreement with GSK"),
        ("ESG REPORT IN HKD AND RMB", "ESG Report in HKD and RMB"),
        ("ISSUE OF CNY BONDS BY AN AG", "Issue of CNY Bonds by an AG"),
    ],
)
def test_acronyms_stay_upper_case(title: str, expected: str) -> None:
    assert to_title_case(title) == expected


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("PHASE III CLINICAL TRIAL", "Phase III Clinical Trial"),
        ("CLASS II AND CLASS XXX SHARES", "Class II and Class XXX Shares"),
        ("PART I", "Part I"),
        ("MIX OF CIVIL AND DIVIDEND", "Mix of Civil and Dividend"),  # letters I, V, X only
        ("SERIES XXXI NOTES", "Series Xxxi Notes"),  # the range ends at XXX
    ],
)
def test_roman_numerals_one_to_thirty_stay_upper_case(title: str, expected: str) -> None:
    assert to_title_case(title) == expected


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("FORM 10-Q FOR Q3", "Form 10-Q for Q3"),
        ("H1 2026 RESULTS", "H1 2026 Results"),
        ("FY2025 ANNUAL REPORT", "FY2025 Annual Report"),
        (
            "PRICING OF US$1.8 BILLION AND CNY26 BILLION NOTES",
            "Pricing of US$1.8 Billion and CNY26 Billion Notes",
        ),
        ("1Q24 EARNINGS RELEASE", "1Q24 Earnings Release"),
        (
            "ANNOUNCEMENT PURSUANT TO RULES 13.51B(2) AND 13.51(2)(l) OF THE LISTING RULES",
            "Announcement Pursuant to Rules 13.51B(2) and 13.51(2)(l) of the Listing Rules",
        ),
        ("COVID-19 UPDATE", "COVID-19 Update"),
    ],
)
def test_tokens_with_digits_are_kept_as_published(title: str, expected: str) -> None:
    assert to_title_case(title) == expected


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("ANNOUNCEMENT ON H SHARES", "Announcement on H Shares"),
        ("ISSUE OF A SHARES AND B SHARE", "Issue of A Shares and B Share"),
        ("NOTICE OF A MEETING", "Notice of a Meeting"),  # not before "shares"
        ("ISSUE OF NEW SHARES AND OPTION SHARES", "Issue of New Shares and Option Shares"),
    ],
)
def test_single_letter_share_classes_stay_upper_case(title: str, expected: str) -> None:
    assert to_title_case(title) == expected


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("THE ANNOUNCEMENT", "The Announcement"),
        ("AND SO ON", "And So on"),
        ("REPORT - THE RESULTS OF THE POLL", "Report - The Results of the Poll"),
        ("MERGER PROPOSAL - (A) PROPOSED OFFER", "Merger Proposal - (A) Proposed Offer"),
        ("(OR AT ANY ADJOURNMENT THEREOF)", "(Or at Any Adjournment Thereof)"),
        ("(THE COMPANY) AND [THE GROUP]", "(The Company) and [The Group]"),
        ("FULFILMENT OF (1) A CONDITION", "Fulfilment of (1) a Condition"),
    ],
)
def test_small_words_are_capitalised_first_after_a_bracket_and_after_a_dash(
    title: str, expected: str
) -> None:
    assert to_title_case(title) == expected


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("NON-EXEMPT CONNECTED TRANSACTION", "Non-Exempt Connected Transaction"),
        ("RE-ELECTION OF RETIRING DIRECTORS", "Re-Election of Retiring Directors"),
        ("SPIN-OFF AND CO-INVESTORS", "Spin-Off and Co-Investors"),
        ("MARK-TO-MARKET", "Mark-To-Market"),  # every hyphenated part is capitalised (SPEC §5)
        ("HK-LISTED A-SHARE ISSUER", "HK-Listed A-Share Issuer"),
        ("AND/OR RESUMPTION", "And/Or Resumption"),
        ("R&D AND M&A", "R&D and M&A"),
    ],
)
def test_hyphenated_and_joined_parts_are_cased_one_by_one(title: str, expected: str) -> None:
    assert to_title_case(title) == expected


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("SHAREHOLDERS' CIRCULAR", "Shareholders' Circular"),
        ("THE COMPANY'S BOARD", "The Company's Board"),
        ("THE COMPANY’S BOARD", "The Company’s Board"),
    ],
)
def test_apostrophes_are_kept(title: str, expected: str) -> None:
    assert to_title_case(title) == expected


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("KINROT HOLDINGS L.P.", "Kinrot Holdings L.P."),
        (
            "VENTURE OF 3 ITALIA S.P.A. AND WIND TELECOMUNICAZIONI S.P.A.",
            "Venture of 3 Italia S.P.A. and Wind Telecomunicazioni S.P.A.",
        ),
        ("A.S. WATSON HOLDINGS LIMITED", "A.S. Watson Holdings Limited"),
        ("ABC CO., LTD.", "Abc Co., Ltd."),
    ],
)
def test_dotted_initialisms_stay_upper_case_and_other_abbreviations_do_not(
    title: str, expected: str
) -> None:
    assert to_title_case(title) == expected


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        (
            "LETTER TO SHAREHOLDERS: 2015 ANNUAL GENERAL MEETING",
            "Letter to Shareholders: 2015 Annual General Meeting",
        ),
        (
            "DIRECTOR DECLARATION / SUBSIDIARY BOARD ROLE",
            "Director Declaration / Subsidiary Board Role",
        ),
        (
            "PROPOSALS FOR (1) GENERAL MANDATES; (2) RE-ELECTION",
            "Proposals for (1) General Mandates; (2) Re-Election",
        ),
        ("ÉCOLE DES BEAUX-ARTS", "École Des Beaux-Arts"),
    ],
)
def test_punctuation_and_non_ascii_letters(title: str, expected: str) -> None:
    assert to_title_case(title) == expected


# --- properties --------------------------------------------------------------------------------

_alphabet = st.sampled_from(
    list("ABCDEFGHIJKLMNOPQRSTUVWXYZ") + list("0123456789") + list(" -/&.,;:()[]'$%")
)
_upper_text = st.text(_alphabet, max_size=60)


@given(_upper_text)
def test_only_the_case_of_letters_changes(text: str) -> None:
    result = to_title_case(text)
    assert result.lower() == text.lower()


@given(st.text(max_size=60))
def test_a_title_that_is_not_mostly_upper_case_is_returned_unchanged(text: str) -> None:
    if not is_mostly_upper(text):
        assert to_title_case(text) == text


@given(_upper_text)
def test_tokens_with_digits_are_never_touched(text: str) -> None:
    result = to_title_case(text)
    for before, after in zip(text.split(), result.split(), strict=True):
        if re.search(r"\d", before):
            assert after == before


@given(_upper_text)
def test_title_case_is_idempotent(text: str) -> None:
    once = to_title_case(text)
    assert to_title_case(once) == once
