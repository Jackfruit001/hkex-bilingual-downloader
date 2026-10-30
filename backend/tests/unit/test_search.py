import json
from collections.abc import AsyncIterator
from datetime import date, datetime
from typing import Any

import httpx
import pytest
import respx

from app.domain.errors import AppError, ErrorCode
from app.domain.models import Lang, Stock
from app.hkex.client import HkexClient
from app.hkex.search import ROW_CAP, search_both, search_language
from tests.support import FakeServlet, make_row, spread_rows

SERVLET = "https://www1.hkexnews.hk/search/titleSearchServlet.do"
ZAI = Stock(stock_id=1000057951, code="09688", name_en="ZAI LAB", name_tc="再鼎醫藥", active=True)
DELISTED = Stock(stock_id=20, code="00013", name_en="HUTCHISON", name_tc="和黃", active=False)


async def no_sleep(_: float) -> None:
    return None


@pytest.fixture
async def client() -> AsyncIterator[HkexClient]:
    c = HkexClient(sleep=no_sleep, min_interval_s=0.0, jitter=lambda: 0.0)
    yield c
    await c.aclose()


def serve(servlet: FakeServlet) -> None:
    respx.get(SERVLET).mock(side_effect=servlet)


@respx.mock
async def test_search_sends_the_verified_parameters(client: HkexClient) -> None:
    servlet = FakeServlet([], [])
    serve(servlet)
    await search_both(client, ZAI, date(2026, 10, 28), date(2026, 10, 28))
    en = servlet.asked_for("EN")[0]
    zh = servlet.asked_for("ZH")[0]
    assert en["stockId"] == "1000057951" and en["category"] == "0" and en["market"] == "SEHK"
    assert (en["fromDate"], en["toDate"]) == ("20261027", "20261029")  # one day of buffer each side
    assert en["rowRange"] == "100" and en["sortDir"] == "0" and en["documentType"] == "-1"
    assert (en["t1code"], en["t2Gcode"], en["t2code"]) == ("-2", "-2", "-2")
    assert zh["lang"] == "ZH"


@respx.mock
async def test_delisted_stock_uses_category_one(client: HkexClient) -> None:
    servlet = FakeServlet([], [])
    serve(servlet)
    await search_both(client, DELISTED, date(2015, 1, 1), date(2015, 1, 31))
    assert servlet.requests[0]["category"] == "1"


@respx.mock
async def test_buffer_rows_outside_the_requested_days_are_dropped_in_hong_kong_time(
    client: HkexClient,
) -> None:
    eve = make_row(1, datetime(2026, 10, 27, 23, 59))
    inside_late = make_row(2, datetime(2026, 10, 28, 22, 52))
    inside_early = make_row(3, datetime(2026, 10, 28, 0, 0))
    after = make_row(4, datetime(2026, 10, 29, 0, 1))
    servlet = FakeServlet([eve, inside_late, inside_early, after], [])
    serve(servlet)
    out = await search_both(client, ZAI, date(2026, 10, 28), date(2026, 10, 28))
    assert sorted(d.news_id for d in out.english) == ["2", "3"]
    assert out.diagnostics.outside_range == 2


@respx.mock
async def test_both_languages_come_back_separately(client: HkexClient) -> None:
    en = make_row(10, datetime(2026, 10, 28, 22, 52), seq=1739)
    tc = make_row(11, datetime(2026, 10, 28, 22, 52), seq=1740, chinese=True)
    serve(FakeServlet([en], [tc]))
    out = await search_both(client, ZAI, date(2026, 10, 28), date(2026, 10, 28))
    assert [d.lang for d in out.english] == [Lang.EN]
    assert [d.lang for d in out.chinese] == [Lang.TC]
    assert out.chinese[0].path.endswith("_c.pdf")


@respx.mock
async def test_one_call_when_everything_fits_in_the_first_page(client: HkexClient) -> None:
    servlet = FakeServlet(spread_rows(40, date(2026, 10, 1), 10), [])
    serve(servlet)
    docs = (await search_both(client, ZAI, date(2026, 10, 1), date(2026, 10, 10))).english
    assert len(docs) == 40
    assert len(servlet.asked_for("EN")) == 1


@respx.mock
async def test_a_second_call_asks_for_exactly_the_total(client: HkexClient) -> None:
    servlet = FakeServlet(spread_rows(250, date(2026, 9, 1), 30), [])
    serve(servlet)
    out = await search_both(client, ZAI, date(2026, 9, 1), date(2026, 9, 30))
    assert len(out.english) == 250
    assert len({d.news_id for d in out.english}) == 250
    assert [p["rowRange"] for p in servlet.asked_for("EN")] == ["100", "250"]
    assert out.diagnostics.english.calls == 2


@respx.mock
async def test_no_results_makes_a_single_call_per_language(client: HkexClient) -> None:
    servlet = FakeServlet([], [])
    serve(servlet)
    out = await search_both(client, ZAI, date(2026, 1, 1), date(2026, 1, 1))
    assert out.english == [] and out.chinese == []
    assert len(servlet.requests) == 2


@respx.mock
async def test_repeated_rows_are_removed_by_news_id(client: HkexClient) -> None:
    rows = spread_rows(30, date(2026, 10, 1), 10)
    serve(FakeServlet(rows + rows[:5], []))  # the server repeats five rows
    docs = (await search_both(client, ZAI, date(2026, 10, 1), date(2026, 10, 10))).english
    assert len(docs) == 30


@respx.mock
async def test_two_documents_sharing_a_page_path_are_both_kept(client: HkexClient) -> None:
    """`/dod/en.html` is a shared page, so the path alone cannot identify a document."""
    a = make_row(1, datetime(2026, 4, 9, 16, 44))
    b = make_row(2, datetime(2026, 4, 9, 16, 45))
    a["FILE_LINK"] = b["FILE_LINK"] = "/listedco/listconews/sehk/dod/en.html"
    serve(FakeServlet([a, b], []))
    docs = (await search_both(client, ZAI, date(2026, 4, 9), date(2026, 4, 9))).english
    assert len(docs) == 2


@respx.mock
async def test_ranges_over_the_row_cap_are_split_and_merged(client: HkexClient) -> None:
    rows = spread_rows(6000, date(2026, 1, 1), 120)
    servlet = FakeServlet(rows, [])
    serve(servlet)
    out = await search_both(client, ZAI, date(2026, 1, 1), date(2026, 4, 30))
    assert len(out.english) == 6000
    assert len({d.news_id for d in out.english}) == 6000
    assert max(int(p["rowRange"]) for p in servlet.requests) <= ROW_CAP
    assert out.diagnostics.english.splits >= 1


@respx.mock
async def test_more_than_the_hard_limit_is_refused_before_fetching_everything(
    client: HkexClient,
) -> None:
    servlet = FakeServlet(spread_rows(20_500, date(2024, 1, 1), 700), [])
    serve(servlet)
    with pytest.raises(AppError) as exc:
        await search_both(client, ZAI, date(2024, 1, 1), date(2025, 11, 30))
    assert exc.value.code is ErrorCode.TOO_MANY_RESULTS
    assert "20,000" in exc.value.message
    assert len(servlet.requests) <= 4


@respx.mock
async def test_a_single_day_over_the_cap_returns_what_it_can_and_says_so(
    client: HkexClient,
) -> None:
    rows = [make_row(i, datetime(2026, 3, 2, 9, i % 60)) for i in range(1, ROW_CAP + 51)]
    serve(FakeServlet(rows, []))
    out = await search_both(client, ZAI, date(2026, 3, 2), date(2026, 3, 2))
    assert len(out.english) == ROW_CAP
    assert any("more than" in w for w in out.diagnostics.warnings)


@respx.mock
async def test_a_server_that_ignores_row_range_cannot_loop_us(client: HkexClient) -> None:
    servlet = FakeServlet(spread_rows(250, date(2026, 9, 1), 30), [], ignore_row_range=True)
    serve(servlet)
    out = await search_both(client, ZAI, date(2026, 9, 1), date(2026, 9, 30))
    assert len(out.english) == 100
    assert len(servlet.asked_for("EN")) == 2
    assert any("250" in w and "100" in w for w in out.diagnostics.warnings)


@respx.mock
async def test_a_chinese_search_that_comes_back_in_english_is_an_error(client: HkexClient) -> None:
    """`lang=TC` silently returns English (research notes Q1); the echoed language must be checked."""
    serve(
        FakeServlet(
            [],
            [make_row(1, datetime(2026, 10, 28, 9, 0), chinese=True)],
            echo={"EN": "E", "ZH": "E"},
        )
    )
    with pytest.raises(AppError) as exc:
        await search_language(client, ZAI, Lang.TC, date(2026, 10, 28), date(2026, 10, 28))
    assert exc.value.code is ErrorCode.HKEX_UNAVAILABLE
    assert exc.value.details is not None and "language" in exc.value.details["reason"]


@respx.mock
async def test_rows_that_cannot_be_parsed_are_counted_not_hidden(client: HkexClient) -> None:
    good = make_row(1, datetime(2026, 10, 28, 9, 0))
    bad = make_row(2, datetime(2026, 10, 28, 9, 1))
    bad["FILE_LINK"] = ""
    serve(FakeServlet([good, bad], []))
    out = await search_both(client, ZAI, date(2026, 10, 28), date(2026, 10, 28))
    assert [d.news_id for d in out.english] == ["1"]
    assert out.diagnostics.english.rows_skipped == 1
    assert any("Skipped 1" in w for w in out.diagnostics.warnings)


@respx.mock
async def test_chinese_section_rows_without_the_c_suffix_are_reported(client: HkexClient) -> None:
    odd = make_row(1, datetime(2026, 10, 28, 9, 0), chinese=False)  # served by the Chinese search
    serve(FakeServlet([], [odd]))
    out = await search_both(client, ZAI, date(2026, 10, 28), date(2026, 10, 28))
    assert len(out.chinese) == 1
    assert out.diagnostics.chinese.rows_without_c_suffix == 1


@respx.mock
async def test_result_field_may_be_null_or_missing(client: HkexClient) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        lang = request.url.params["lang"]
        body: dict[str, Any] = {
            "lang": "E" if lang == "EN" else "C",
            "recordCnt": 0,
            "hasNextRow": False,
        }
        if lang == "EN":
            body["result"] = None
        return httpx.Response(200, json=body)

    respx.get(SERVLET).mock(side_effect=handler)
    out = await search_both(client, ZAI, date(2026, 10, 28), date(2026, 10, 28))
    assert out.english == [] and out.chinese == []


@respx.mock
async def test_the_start_is_not_pushed_before_the_first_hkexnews_record(client: HkexClient) -> None:
    servlet = FakeServlet([], [])
    serve(servlet)
    await search_both(client, ZAI, date(1999, 4, 1), date(1999, 4, 2))
    assert servlet.requests[0]["fromDate"] == "19990401"


@respx.mock
async def test_diagnostics_report_rows_and_duration(client: HkexClient) -> None:
    serve(
        FakeServlet(
            spread_rows(5, date(2026, 10, 1), 5),
            spread_rows(4, date(2026, 10, 1), 5, chinese=True, start_id=100),
        )
    )
    d = (await search_both(client, ZAI, date(2026, 10, 1), date(2026, 10, 5))).diagnostics
    assert (d.english.rows_fetched, d.chinese.rows_fetched) == (5, 4)
    assert d.duration_s >= 0
    json.dumps(d.to_dict())  # serialisable for the API
