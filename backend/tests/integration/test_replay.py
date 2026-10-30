"""Replay the Phase 0 recordings through the real client and search code, offline."""

import json
from collections.abc import AsyncIterator
from datetime import date
from typing import Any

import httpx
import pytest
import respx

from app.domain.models import Document, Lang, Stock
from app.hkex.client import HkexClient
from app.hkex.reference import CategoryIndex
from app.hkex.search import LangStats, search_language
from tests.conftest import RAW, scenario_names

SERVLET = "https://www1.hkexnews.hk/search/titleSearchServlet.do"


async def no_sleep(_: float) -> None:
    return None


@pytest.fixture
async def client() -> AsyncIterator[HkexClient]:
    c = HkexClient(sleep=no_sleep, min_interval_s=0.0, jitter=lambda: 0.0)
    yield c
    await c.aclose()


@pytest.fixture(scope="module")
def categories() -> CategoryIndex:
    def load(name: str) -> Any:
        return json.loads((RAW / "reference" / f"{name}.json").read_text(encoding="utf-8"))

    return CategoryIndex.from_raw(
        load("tierone_e"), load("tiertwo_e"), load("tierone_c"), load("tiertwo_c")
    )


def recorded_calls(scenario: str, lang: str) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """(request params, response body) for each recorded call, in order."""
    out = []
    for body_file in sorted((RAW / scenario).glob(f"{lang}_[0-9].json"), key=lambda f: f.stem):
        params = json.loads(body_file.with_suffix(".params.json").read_text(encoding="utf-8"))[
            "params"
        ]
        out.append((params, json.loads(body_file.read_text(encoding="utf-8"))))
    return out


def scenario_stock(scenario: str) -> tuple[Stock, date, date]:
    meta = json.loads((RAW / scenario / "scenario.json").read_text(encoding="utf-8"))
    entry = meta["stock"][0]
    stock = Stock(
        stock_id=entry["i"], code=entry["c"], name_en=entry["n"], active=meta["category"] == 0
    )
    return (
        stock,
        date.fromisoformat(f"{meta['from'][:4]}-{meta['from'][4:6]}-{meta['from'][6:]}"),
        date.fromisoformat(f"{meta['to'][:4]}-{meta['to'][4:6]}-{meta['to'][6:]}"),
    )


async def replay(
    client: HkexClient, scenario: str, lang: Lang, categories: CategoryIndex
) -> tuple[list[Document], LangStats, list[str]]:
    """Serve the recorded responses in order and assert each request equals the recorded one."""
    key = "en" if lang is Lang.EN else "zh"
    calls = recorded_calls(scenario, key)
    sent: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(dict(request.url.params))
        return httpx.Response(200, json=calls[len(sent) - 1][1])

    stock, start, end = scenario_stock(scenario)
    stats, warnings = LangStats(), []
    with respx.mock:
        respx.get(SERVLET).mock(side_effect=handler)
        docs = await search_language(
            client, stock, lang, start, end, categories, stats=stats, warnings=warnings
        )
    assert len(sent) == len(calls), (
        f"{scenario}/{key}: sent {len(sent)} calls, recorded {len(calls)}"
    )
    for ours, (recorded, _) in zip(sent, calls, strict=True):
        assert ours == {k: str(v) for k, v in recorded.items()}, (
            f"{scenario}/{key}: request differs"
        )
    assert warnings == []
    return docs, stats, warnings


@pytest.mark.parametrize("scenario", scenario_names())
async def test_every_scenario_replays_exactly_and_parses_cleanly(
    client: HkexClient, categories: CategoryIndex, scenario: str
) -> None:
    for lang in (Lang.EN, Lang.TC):
        docs, stats, _ = await replay(client, scenario, lang, categories)
        recorded = recorded_calls(scenario, "en" if lang is Lang.EN else "zh")[-1][1]
        assert len(docs) == recorded["recordCnt"]
        assert stats.rows_skipped == 0
        assert len({d.news_id for d in docs}) == len(docs)
        assert all(d.lang is lang for d in docs)
        if lang is Lang.EN:
            assert stats.rows_with_c_suffix == 0


async def test_large_range_takes_two_calls_and_returns_every_row(
    client: HkexClient, categories: CategoryIndex
) -> None:
    docs, stats, _ = await replay(client, "large-range", Lang.EN, categories)
    assert len(docs) == 1574
    assert stats.calls == 2


async def test_no_results_is_one_call_and_empty(
    client: HkexClient, categories: CategoryIndex
) -> None:
    for lang in (Lang.EN, Lang.TC):
        docs, stats, _ = await replay(client, "no-results", lang, categories)
        assert docs == [] and stats.calls == 1


async def test_zai_lab_pairs_are_one_apart_in_file_number_and_news_id(
    client: HkexClient, categories: CategoryIndex
) -> None:
    en, _, _ = await replay(client, "zai-lab-nddr", Lang.EN, categories)
    tc, _, _ = await replay(client, "zai-lab-nddr", Lang.TC, categories)
    assert [d.seq for d in en] == [1739, 1671]
    assert [d.seq for d in tc] == [1740, 1672]
    assert [int(b.news_id) - int(a.news_id) for a, b in zip(en, tc, strict=True)] == [1, 1]
    assert all(a.category_codes == b.category_codes != () for a, b in zip(en, tc, strict=True))


async def test_form_8k_has_one_chinese_stub_and_no_english_stub(
    client: HkexClient, categories: CategoryIndex
) -> None:
    en, _, _ = await replay(client, "form-8k-en-only", Lang.EN, categories)
    tc, _, _ = await replay(client, "form-8k-en-only", Lang.TC, categories)
    assert len(en) == len(tc) == 4
    assert [d for d in en if d.is_stub] == []
    (stub,) = [d for d in tc if d.is_stub]
    assert stub.path.endswith("2026102301071_c.htm") and stub.file_type == "HTM"
    (real,) = [d for d in en if d.title.startswith("OVERSEAS REGULATORY ANNOUNCEMENT - FORM 8-K")]
    assert real.seq is not None and stub.seq == real.seq + 1


async def test_a_plus_h_has_one_english_stub_for_a_chinese_only_report(
    client: HkexClient, categories: CategoryIndex
) -> None:
    en, _, _ = await replay(client, "a-plus-h-30d", Lang.EN, categories)
    tc, _, _ = await replay(client, "a-plus-h-30d", Lang.TC, categories)
    (stub,) = [d for d in en if d.is_stub]
    assert stub.path.endswith("2026103000899.htm")
    assert [d for d in tc if d.is_stub] == []
    (real,) = [d for d in tc if d.path.endswith("2026103000898_c.pdf")]
    assert stub.seq == (real.seq or 0) + 1
    assert stub.category_codes == real.category_codes != ()


async def test_exchange_notices_on_web_pages_are_not_mistaken_for_stubs(
    client: HkexClient, categories: CategoryIndex
) -> None:
    en, _, _ = await replay(client, "delisted", Lang.EN, categories)
    notices = [d for d in en if d.title.startswith("EXCHANGE NOTICE") and d.file_type == "HTM"]
    assert len(notices) > 5
    assert not any(d.is_stub for d in notices)


async def test_documents_on_display_pages_have_no_folder_date_and_a_stub_in_chinese(
    client: HkexClient, categories: CategoryIndex
) -> None:
    en, _, _ = await replay(client, "reused-code", Lang.EN, categories)
    tc, stats, _ = await replay(client, "reused-code", Lang.TC, categories)
    (dod_en,) = [d for d in en if "/dod/" in d.path]
    (dod_tc,) = [d for d in tc if "/dod/" in d.path]
    assert (dod_en.folder_date, dod_en.seq) == (None, None)
    assert dod_en.file_type == "PDF" and not dod_en.is_stub
    assert dod_tc.is_stub
    assert stats.rows_without_c_suffix >= 1  # tc.html carries no _c


async def test_2005_documents_have_no_categories_and_use_the_same_number_with_c(
    client: HkexClient, categories: CategoryIndex
) -> None:
    en, _, _ = await replay(client, "old-docs", Lang.EN, categories)
    tc, _, _ = await replay(client, "old-docs", Lang.TC, categories)
    assert (len(en), len(tc)) == (125, 35)
    assert all(d.category_codes == () for d in en + tc)
    assert all(d.release_at.year == 2005 for d in en + tc)
    ltn_en = {d.seq for d in en if d.seq is not None}
    same_number = [d for d in tc if d.seq in ltn_en]
    assert same_number, "2005 Chinese files share the English file number"


async def test_same_minute_documents_with_the_same_category_still_have_distinct_numbers(
    client: HkexClient, categories: CategoryIndex
) -> None:
    en, _, _ = await replay(client, "listing-docs", Lang.EN, categories)
    tc, _, _ = await replay(client, "listing-docs", Lang.TC, categories)
    assert sorted(d.seq or 0 for d in en) == [684, 694]
    assert sorted(d.seq or 0 for d in tc) == [685, 695]
    assert len({d.release_at for d in en + tc}) == 1
    assert len({d.category_codes for d in en + tc}) == 1


async def test_multi_code_documents_keep_every_code(
    client: HkexClient, categories: CategoryIndex
) -> None:
    en, _, _ = await replay(client, "annual-report-season", Lang.EN, categories)
    assert any(d.stock_codes == ("00700", "80700") for d in en)
    assert all("00700" in d.stock_codes for d in en)
