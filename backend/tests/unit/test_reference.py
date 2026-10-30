from typing import Any

import pytest

from app.domain.errors import AppError, ErrorCode
from app.domain.models import Lang
from app.hkex.parse import parse_category_text, parse_row
from app.hkex.reference import CategoryIndex, StockDirectory
from tests.conftest import scenario_names, scenario_rows


@pytest.fixture(scope="module")
def categories(reference_raw: dict[str, Any]) -> CategoryIndex:
    r = reference_raw
    return CategoryIndex.from_raw(r["tierone_e"], r["tiertwo_e"], r["tierone_c"], r["tiertwo_c"])


@pytest.fixture(scope="module")
def stocks(reference_raw: dict[str, Any]) -> StockDirectory:
    r = reference_raw
    return StockDirectory.from_raw(
        r["activestock_sehk_e"],
        r["activestock_sehk_c"],
        r["inactivestock_sehk_e"],
        r["inactivestock_sehk_c"],
    )


# --- categories ---


def codes(index: CategoryIndex, lang: Lang, text: str) -> tuple[str, ...]:
    return index.resolve(lang, parse_category_text(text))


def test_english_and_chinese_category_names_resolve_to_the_same_code(
    categories: CategoryIndex,
) -> None:
    en = codes(categories, Lang.EN, "Next Day Disclosure Returns - [Others]")
    tc = codes(categories, Lang.TC, "翌日披露報表 - [其他]")
    assert len(en) == 1
    assert en == tc


def test_parent_only_category_resolves_to_the_tier_one_code(categories: CategoryIndex) -> None:
    en = codes(categories, Lang.EN, "Monthly Returns")
    assert en == ("51500",)
    assert codes(categories, Lang.TC, "月報表") == en


def test_multi_category_entries_resolve_every_child(categories: CategoryIndex) -> None:
    en = codes(
        categories,
        Lang.EN,
        "Announcements and Notices - [Placing / Issue of Shares under a General Mandate]",
    )
    tc = codes(categories, Lang.TC, "公告及通告 - [配售 / 根據一般性授權發行股份]")
    assert len(en) == 2
    assert set(en) == set(tc)


def test_cancelled_prefix_does_not_change_the_codes(categories: CategoryIndex) -> None:
    plain = codes(
        categories, Lang.EN, "Announcements and Notices - [Inside Information / Resumption]"
    )
    prefixed = codes(
        categories,
        Lang.EN,
        "(Headline Revised) Announcements and Notices - [Inside Information / Resumption]",
    )
    assert plain == prefixed != ()


def test_an_unknown_child_makes_the_whole_category_unknown(categories: CategoryIndex) -> None:
    # Partial codes could look like a conflict or a match that is not there.
    assert (
        codes(categories, Lang.EN, "Announcements and Notices - [Placing / No Such Category]") == ()
    )
    assert codes(categories, Lang.EN, "No Such Parent - [Others]") == ()
    assert codes(categories, Lang.EN, "") == ()


def test_the_same_child_name_under_different_parents_is_not_confused(
    categories: CategoryIndex,
) -> None:
    # 93 child names in the sample occur under more than one parent; the parent decides.
    a = codes(
        categories, Lang.EN, "Announcements and Notices - [Amendment of Constitutional Documents]"
    )
    b = codes(categories, Lang.EN, "Circulars - [Amendment of Constitutional Documents]")
    assert len(a) == len(b) == 1
    assert a != b


def test_nearly_every_recorded_category_resolves_and_matches_across_languages(
    categories: CategoryIndex,
) -> None:
    total = resolved = pairs = agree = 0
    for name in scenario_names():
        en_rows = scenario_rows(name, "en")
        zh_rows = scenario_rows(name, "zh")
        for r in en_rows:
            doc = parse_row(r, Lang.EN, categories)
            if doc.category_text:
                total += 1
                resolved += bool(doc.category_codes)
        by_minute: dict[tuple[str, str], Any] = {}
        for r in zh_rows:
            by_minute.setdefault((r["STOCK_CODE"], r["DATE_TIME"]), []).append(
                parse_row(r, Lang.TC, categories)
            )
        for r in en_rows:
            doc = parse_row(r, Lang.EN, categories)
            same = by_minute.get((r["STOCK_CODE"], r["DATE_TIME"]), [])
            if (
                len(same) == 1
                and doc.category_codes
                and same[0].category_codes
                and not doc.is_stub
                and not same[0].is_stub
            ):
                pairs += 1
                agree += set(doc.category_codes) == set(same[0].category_codes)
    assert total > 3000
    assert resolved / total > 0.99, f"only {resolved} of {total} categories resolved"
    assert pairs > 500
    assert agree / pairs > 0.99, f"{agree} of {pairs} same-minute pairs share category codes"


# --- stock directory ---


def test_lookup_merges_english_and_chinese_names(stocks: StockDirectory) -> None:
    (s,) = stocks.lookup("09688")
    assert (s.stock_id, s.code, s.name_en, s.name_tc, s.active) == (
        1000057951,
        "09688",
        "ZAI LAB",
        "再鼎醫藥",
        True,
    )


def test_active_security_is_listed_before_a_delisted_one_with_the_same_code(
    stocks: StockDirectory,
) -> None:
    # 00700 is TENCENT today and was YAOHAN INT'L before; about 7% of ordinary codes have a twin.
    found = stocks.lookup("00700")
    assert [(s.name_en, s.active) for s in found] == [("TENCENT", True), ("YAOHAN INT'L", False)]
    assert found[0].name_tc == "騰訊控股"


def test_delisted_stocks_are_found_and_marked_inactive(stocks: StockDirectory) -> None:
    found = stocks.lookup("03333")
    assert len(found) == 3
    assert not any(s.active for s in found)
    assert {s.stock_id for s in found} == {39454, 9278, 22079}


def test_resolve_returns_the_only_match(stocks: StockDirectory) -> None:
    assert stocks.resolve("09688").stock_id == 1000057951


def test_resolve_with_a_stock_id_picks_the_active_tencent(stocks: StockDirectory) -> None:
    assert stocks.resolve("00700", stock_id=7609).name_en == "TENCENT"


def test_unknown_code_is_reported(stocks: StockDirectory) -> None:
    with pytest.raises(AppError) as exc:
        stocks.resolve("99999")
    assert exc.value.code is ErrorCode.UNKNOWN_STOCK_CODE
    assert "99999" in exc.value.message


def test_reused_code_asks_the_user_to_choose(stocks: StockDirectory) -> None:
    with pytest.raises(AppError) as exc:
        stocks.resolve("00013")
    assert exc.value.code is ErrorCode.AMBIGUOUS_STOCK_CODE
    choices = exc.value.details["choices"]  # type: ignore[index]
    assert {c["name_en"] for c in choices} == {"HUTCHISON", "HUTCHMED"}
    assert {c["active"] for c in choices} == {True, False}


def test_a_chosen_stock_id_settles_a_reused_code(stocks: StockDirectory) -> None:
    assert stocks.resolve("00013", stock_id=20).name_en == "HUTCHISON"
    assert stocks.resolve("00013", stock_id=1000001102).name_en == "HUTCHMED"


def test_a_stock_id_from_another_code_is_rejected(stocks: StockDirectory) -> None:
    with pytest.raises(AppError) as exc:
        stocks.resolve("00700", stock_id=20)  # id 20 belongs to code 00013
    assert exc.value.code is ErrorCode.UNKNOWN_STOCK_CODE
