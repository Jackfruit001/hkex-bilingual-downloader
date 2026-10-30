"""The helper's pipeline: search, pair, tag, choose, fetch, draft entries, record fixtures."""

import hashlib
import json
from collections.abc import AsyncIterator
from datetime import date, datetime
from pathlib import Path

import httpx
import pytest
import respx

from app.config import PairingConfig
from app.domain.models import Document, Lang, Stock
from app.domain.timeutil import HKT
from app.hkex.reference import DEFAULT_SNAPSHOT, CategoryIndex, load_snapshot
from app.hkex.search import SearchDiagnostics, SearchOutput
from app.pairing.content_check import TextStatus
from app.pairing.models import Status
from tests.conftest import scenario_rows
from tests.golden.draft import (
    Drafted,
    Scenario,
    choose_rows,
    counterpart,
    fetch_row_files,
    find_row,
    load_scenario,
    pair_and_tag,
    repair_with_hashes,
    save_fixtures,
    search_and_pair,
    to_entry,
)
from tests.golden.fetch import GoldenClient, HelperStopped
from tests.golden.schema import CaseType
from tests.golden.store import FileFacts
from tests.support import FakeServlet, make_doc, make_pdf

SEARCH = "https://www1.hkexnews.hk/search/titleSearchServlet.do"
ZAI = Stock(stock_id=1000057951, code="09688", name_en="ZAI LAB")


async def no_sleep(_: float) -> None:
    return None


@pytest.fixture(scope="module")
def categories() -> CategoryIndex:
    return load_snapshot(DEFAULT_SNAPSHOT).categories


@pytest.fixture
async def client(tmp_path: Path) -> AsyncIterator[GoldenClient]:
    c = GoldenClient(json_dir=tmp_path / "json", pdf_dir=tmp_path / "pdf", sleep=no_sleep)
    yield c
    await c.aclose()


def recorded(scenario: str) -> FakeServlet:
    return FakeServlet(scenario_rows(scenario, "en"), scenario_rows(scenario, "zh"))


def scenario_for(stock: Stock, start: date, end: date) -> Scenario:
    return Scenario.for_stock(stock, start, end)


# --- search, pair, tag ------------------------------------------------------------------------


@respx.mock
async def test_a_recorded_day_is_searched_paired_and_tagged(
    client: GoldenClient, categories: CategoryIndex
) -> None:
    respx.get(SEARCH).mock(side_effect=recorded("zai-lab-nddr"))
    day = date(2026, 10, 28)
    drafted = await search_and_pair(client, ZAI, categories, scenario_for(ZAI, day, day))

    assert [a.status for a in drafted.rows] == [Status.MATCHED, Status.MATCHED]
    assert {(a.en.seq, a.tc.seq) for a in drafted.rows} == {(1739, 1740), (1671, 1672)}
    for a in drafted.rows:
        assert CaseType.SEVERAL_SAME_DAY in drafted.tags[a.id]
    assert drafted.scenario.name == "09688-20261028-20261028"


@respx.mock
async def test_a_second_search_is_served_from_the_cache(
    client: GoldenClient, categories: CategoryIndex
) -> None:
    route = respx.get(SEARCH).mock(side_effect=recorded("zai-lab-nddr"))
    day = date(2026, 10, 28)
    await search_and_pair(client, ZAI, categories, scenario_for(ZAI, day, day))
    made = route.call_count
    await search_and_pair(client, ZAI, categories, scenario_for(ZAI, day, day))
    assert route.call_count == made


@respx.mock
async def test_a_stub_becomes_a_single_language_row_with_the_reason(
    client: GoldenClient, categories: CategoryIndex
) -> None:
    respx.get(SEARCH).mock(side_effect=recorded("form-8k-en-only"))
    day = date(2026, 10, 23)
    drafted = await search_and_pair(client, ZAI, categories, scenario_for(ZAI, day, day))
    single = [a for a in drafted.rows if a.status is Status.EN_ONLY]
    assert len(single) == 1
    entry = to_entry(drafted, single[0])
    assert entry.truth.tc is None and entry.truth.absent == "stub"
    assert CaseType.EN_ONLY_STUB in entry.case_types
    assert entry.proposal.status == "en_only"


@respx.mock
async def test_the_delisted_flag_comes_from_the_stock(
    client: GoldenClient, categories: CategoryIndex
) -> None:
    respx.get(SEARCH).mock(side_effect=recorded("zai-lab-nddr"))
    gone = ZAI.model_copy(update={"active": False})
    day = date(2026, 10, 28)
    drafted = await search_and_pair(client, gone, categories, scenario_for(gone, day, day))
    assert all(CaseType.DELISTED in t for t in drafted.tags.values())


def test_an_entry_records_the_claim_unverified_with_the_matchers_view_apart() -> None:
    en = make_doc(
        Lang.EN, 100, datetime(2026, 10, 28, 22, 52, tzinfo=HKT), news_id=100, title="Results"
    )
    tc = make_doc(
        Lang.TC,
        101,
        datetime(2026, 10, 28, 22, 52, tzinfo=HKT),
        news_id=101,
        c_suffix=True,
        title="業績",
    )
    day = date(2026, 10, 28)
    drafted = pair_and_tag(
        SearchOutput([en], [tc], SearchDiagnostics()), ZAI, scenario_for(ZAI, day, day)
    )
    entry = to_entry(drafted, drafted.rows[0])
    assert entry.id == "09688-100" and entry.verified is False
    assert (entry.stock_code, entry.stock_id, entry.stock_name) == ("09688", 1000057951, "ZAI LAB")
    assert entry.truth.en is not None and entry.truth.tc is not None
    assert (entry.truth.en.news_id, entry.truth.tc.news_id) == ("100", "101")
    assert entry.truth.en.released == "2026-10-28 22:52"
    assert entry.proposal.status == "matched" and entry.proposal.evidence
    assert entry.scenario == "09688-20261028-20261028"


# --- choosing rows ----------------------------------------------------------------------------


def synthetic(count: int = 6) -> Drafted:
    docs_en, docs_tc = [], []
    for i in range(count):
        when = datetime(2026, 10, 28, 9 + i, 0, tzinfo=HKT)
        docs_en.append(make_doc(Lang.EN, 100 + 10 * i, when, news_id=100 + 10 * i))
        docs_tc.append(make_doc(Lang.TC, 101 + 10 * i, when, news_id=101 + 10 * i, c_suffix=True))
    day = date(2026, 10, 28)
    return pair_and_tag(
        SearchOutput(docs_en, docs_tc, SearchDiagnostics()), ZAI, scenario_for(ZAI, day, day)
    )


def test_an_explicit_pick_uses_one_based_row_numbers_in_display_order() -> None:
    drafted = synthetic()
    assert choose_rows(drafted, pick=[3, 1, 3], sample=0, seed=0, taken=set()) == [1, 3]


def test_a_pick_outside_the_table_is_an_error() -> None:
    drafted = synthetic()
    for bad in (0, 7, -1):
        with pytest.raises(ValueError, match="row"):
            choose_rows(drafted, pick=[bad], sample=0, seed=0, taken=set())


def test_asking_for_a_pick_and_a_sample_together_is_an_error() -> None:
    with pytest.raises(ValueError, match="either"):
        choose_rows(synthetic(), pick=[1], sample=2, seed=0, taken=set())


def test_nothing_is_chosen_unless_asked() -> None:
    assert choose_rows(synthetic(), pick=[], sample=0, seed=0, taken=set()) == []


def test_a_sample_is_reproducible_and_skips_entries_already_in_the_file() -> None:
    drafted = synthetic()
    first = choose_rows(drafted, pick=[], sample=3, seed=4, taken=set())
    assert first == choose_rows(drafted, pick=[], sample=3, seed=4, taken=set())
    taken = {"09688-" + drafted.rows[first[0] - 1].en.news_id}
    again = choose_rows(drafted, pick=[], sample=3, seed=4, taken=taken)
    assert first[0] not in again and len(again) == 3


# --- fetching the files for a row ------------------------------------------------------------


def pdf_pair(
    en_lines: list[str], tc_lines: list[str]
) -> tuple[Drafted, Document, Document, bytes, bytes]:
    when = datetime(2026, 10, 28, 22, 52, tzinfo=HKT)
    en = make_doc(Lang.EN, 100, when, news_id=100, size_label="84KB")
    tc = make_doc(Lang.TC, 101, when, news_id=101, c_suffix=True, size_label="84KB")
    day = date(2026, 10, 28)
    drafted = pair_and_tag(
        SearchOutput([en], [tc], SearchDiagnostics()), ZAI, scenario_for(ZAI, day, day)
    )
    return drafted, en, tc, make_pdf([en_lines]), make_pdf([tc_lines])


LONG = [
    "Announcement of results for the year ended 31 December 2025 revenue 1,234,567 profit 89,012",
    "dividend 0.35 per share record date 28 October 2026 capital 5,000,000 shares 450,000,000",
    "the board of directors announces the audited consolidated results of the group as follows",
]


@respx.mock
async def test_both_pdfs_are_fetched_hashed_and_compared(client: GoldenClient) -> None:
    drafted, en, tc, en_pdf, tc_pdf = pdf_pair(LONG, LONG)
    respx.get(en.source_url).mock(return_value=httpx.Response(200, content=en_pdf))
    respx.get(tc.source_url).mock(return_value=httpx.Response(200, content=tc_pdf))

    files = await fetch_row_files(
        client,
        drafted.rows[0],
        max_bytes=1_000_000,
        cfg=PairingConfig(content_min_chinese_share=0.0),
    )

    assert files.en is not None and files.tc is not None
    assert files.en.facts.sha256 == hashlib.sha256(en_pdf).hexdigest()
    assert files.en.facts.bytes == len(en_pdf)
    assert files.en.facts.tokens["1234567"] == 1
    assert files.containment == 1.0
    assert files.en.lines and "Announcement" in files.en.lines[0]
    assert files.en.path.name.startswith("EN_2026-10-28_09688_100")
    assert files.tc.path.name.startswith("TC_2026-10-28_09688_101")
    assert files.facts_by_key().keys() == {"en:100", "tc:101"}
    assert files.skipped == []


@respx.mock
async def test_a_web_page_is_not_fetched_and_the_reason_is_kept(client: GoldenClient) -> None:
    when = datetime(2026, 10, 28, 22, 52, tzinfo=HKT)
    en = make_doc(Lang.EN, 100, when, news_id=100, ext="htm", file_type="HTM")
    tc = make_doc(Lang.TC, 101, when, news_id=101, c_suffix=True, ext="htm", file_type="HTM")
    day = date(2026, 10, 28)
    drafted = pair_and_tag(
        SearchOutput([en], [tc], SearchDiagnostics()), ZAI, scenario_for(ZAI, day, day)
    )
    route = respx.route().mock(return_value=httpx.Response(200))
    files = await fetch_row_files(client, drafted.rows[0], max_bytes=1_000_000)
    assert files.en is None and files.tc is None and route.call_count == 0
    assert files.skipped == ["EN 100: a web page, not fetched", "TC 101: a web page, not fetched"]


@respx.mock
async def test_a_file_the_listing_says_is_too_big_is_skipped_without_a_request(
    client: GoldenClient,
) -> None:
    when = datetime(2026, 10, 28, 22, 52, tzinfo=HKT)
    en = make_doc(Lang.EN, 100, when, news_id=100, size_label="45MB")
    tc = make_doc(Lang.TC, 101, when, news_id=101, c_suffix=True, size_label="84KB")
    day = date(2026, 10, 28)
    drafted = pair_and_tag(
        SearchOutput([en], [tc], SearchDiagnostics()), ZAI, scenario_for(ZAI, day, day)
    )
    route = respx.get(tc.source_url).mock(
        return_value=httpx.Response(200, content=make_pdf([LONG]))
    )
    files = await fetch_row_files(client, drafted.rows[0], max_bytes=30 * 1024 * 1024)
    assert files.en is None and files.tc is not None
    assert any("45MB" in s for s in files.skipped)
    assert route.call_count == 1


@respx.mock
async def test_a_file_that_turns_out_too_big_is_skipped_but_a_block_still_ends_the_run(
    tmp_path: Path,
) -> None:
    drafted, en, tc, en_pdf, _ = pdf_pair(LONG, LONG)
    c = GoldenClient(
        json_dir=tmp_path / "j", pdf_dir=tmp_path / "p", sleep=no_sleep, max_bytes=len(en_pdf) - 1
    )
    respx.get(en.source_url).mock(return_value=httpx.Response(200, content=en_pdf))
    respx.get(tc.source_url).mock(return_value=httpx.Response(403))
    with pytest.raises(HelperStopped, match="403"):
        await fetch_row_files(c, drafted.rows[0], max_bytes=1_000_000)
    await c.aclose()


@respx.mock
async def test_a_single_language_row_fetches_only_its_own_file(client: GoldenClient) -> None:
    when = datetime(2026, 10, 28, 22, 52, tzinfo=HKT)
    en = make_doc(Lang.EN, 100, when, news_id=100)
    stub = make_doc(Lang.TC, 101, when, news_id=101, c_suffix=True, ext="htm", stub=True)
    day = date(2026, 10, 28)
    drafted = pair_and_tag(
        SearchOutput([en], [stub], SearchDiagnostics()), ZAI, scenario_for(ZAI, day, day)
    )
    respx.get(en.source_url).mock(return_value=httpx.Response(200, content=make_pdf([LONG])))
    stub_route = respx.get(stub.source_url).mock(return_value=httpx.Response(200))
    files = await fetch_row_files(client, drafted.rows[0], max_bytes=1_000_000)
    assert files.en is not None and files.tc is None and files.containment is None
    assert stub_route.call_count == 0


# --- identical bytes make a bilingual document -----------------------------------------------


def test_identical_bytes_in_both_sections_make_a_bilingual_document() -> None:
    when = datetime(2026, 10, 28, 22, 52, tzinfo=HKT)
    en = make_doc(Lang.EN, 100, when, news_id=100)
    tc = make_doc(Lang.TC, 150, when, news_id=150, c_suffix=True)  # far apart: only `check`
    day = date(2026, 10, 28)
    drafted = pair_and_tag(
        SearchOutput([en], [tc], SearchDiagnostics()), ZAI, scenario_for(ZAI, day, day)
    )
    assert drafted.rows[0].status is Status.CHECK

    same = FileFacts(sha256="a" * 64, bytes=10, tokens={})
    repaired = repair_with_hashes(drafted, {"en:100": same, "tc:150": same})

    (row,) = repaired.rows
    assert row.status is Status.MATCHED and row.bilingual
    assert repaired.tags[row.id] == (CaseType.BILINGUAL_IDENTICAL,)


def test_different_bytes_change_nothing() -> None:
    when = datetime(2026, 10, 28, 22, 52, tzinfo=HKT)
    en = make_doc(Lang.EN, 100, when, news_id=100)
    tc = make_doc(Lang.TC, 150, when, news_id=150, c_suffix=True)
    day = date(2026, 10, 28)
    drafted = pair_and_tag(
        SearchOutput([en], [tc], SearchDiagnostics()), ZAI, scenario_for(ZAI, day, day)
    )
    repaired = repair_with_hashes(
        drafted,
        {
            "en:100": FileFacts(sha256="a" * 64, bytes=1, tokens={}),
            "tc:150": FileFacts(sha256="b" * 64, bytes=1, tokens={}),
        },
    )
    assert repaired.rows == drafted.rows


# --- recording fixtures -----------------------------------------------------------------------


@respx.mock
async def test_recorded_fixtures_replay_the_same_search_with_no_network(
    client: GoldenClient, categories: CategoryIndex, tmp_path: Path
) -> None:
    respx.get(SEARCH).mock(side_effect=recorded("zai-lab-nddr"))
    day = date(2026, 10, 28)
    live = await search_and_pair(client, ZAI, categories, scenario_for(ZAI, day, day))

    folder = save_fixtures(client, live, tmp_path / "golden")
    assert folder == tmp_path / "golden" / "09688-20261028-20261028"
    assert load_scenario(folder) == live.scenario

    respx.reset()
    route = respx.route().mock(return_value=httpx.Response(500))
    offline = GoldenClient(json_dir=folder / "calls", pdf_dir=tmp_path / "unused", budget=0)
    replay = await search_and_pair(offline, ZAI, categories, load_scenario(folder))
    await offline.aclose()

    assert route.call_count == 0
    assert replay.rows == live.rows and replay.tags == live.tags


@respx.mock
async def test_saving_a_scenario_twice_changes_nothing_but_a_clash_is_refused(
    client: GoldenClient, categories: CategoryIndex, tmp_path: Path
) -> None:
    respx.get(SEARCH).mock(side_effect=recorded("zai-lab-nddr"))
    day = date(2026, 10, 28)
    drafted = await search_and_pair(client, ZAI, categories, scenario_for(ZAI, day, day))
    folder = save_fixtures(client, drafted, tmp_path)
    before = {p: p.read_bytes() for p in folder.rglob("*") if p.is_file()}
    save_fixtures(client, drafted, tmp_path)
    assert {p: p.read_bytes() for p in folder.rglob("*") if p.is_file()} == before

    other = ZAI.model_copy(update={"stock_id": 7})
    clash = drafted.__class__(
        scenario=Scenario(drafted.scenario.name, "09688", 7, day, day),
        stock=other,
        search=drafted.search,
        result=drafted.result,
        tags=drafted.tags,
    )
    with pytest.raises(ValueError, match="already holds"):
        save_fixtures(client, clash, tmp_path)


def test_a_scenario_file_is_plain_json(tmp_path: Path) -> None:
    day = date(2026, 10, 28)
    drafted = synthetic()
    folder = save_fixtures(
        GoldenClient(json_dir=tmp_path / "j", pdf_dir=tmp_path / "p"), drafted, tmp_path
    )
    meta = json.loads((folder / "scenario.json").read_text(encoding="utf-8"))
    assert meta == {
        "name": "09688-20261028-20261028",
        "code": "09688",
        "stock_id": 1000057951,
        "from": "2026-10-28",
        "to": str(day),
    }


# --- Chinese text that cannot be decoded -------------------------------------------------------
# The rule itself is tested with the content check (test_content_check.py).


@respx.mock
async def test_a_chinese_pdf_whose_text_cannot_be_decoded_gives_no_figures_and_no_comparison(
    client: GoldenClient,
) -> None:
    drafted, en, tc, en_pdf, tc_pdf = pdf_pair(LONG, LONG)  # Latin text standing in for gibberish
    respx.get(en.source_url).mock(return_value=httpx.Response(200, content=en_pdf))
    respx.get(tc.source_url).mock(return_value=httpx.Response(200, content=tc_pdf))
    files = await fetch_row_files(client, drafted.rows[0], max_bytes=1_000_000)
    assert files.en is not None and files.tc is not None
    assert files.tc.text_status is TextStatus.UNAVAILABLE
    assert files.tc.tokens == {} and files.tc.facts.tokens == {} and files.tc.lines == ()
    assert "Chinese" in files.tc.note
    assert files.containment is None
    assert files.en.tokens  # the English side is unaffected


# --- finding an entry again ------------------------------------------------------------------


def test_an_entry_is_found_again_by_its_english_news_id() -> None:
    drafted = synthetic()
    for n, a in enumerate(drafted.rows, start=1):
        assert find_row(drafted, to_entry(drafted, a)) == n


def test_a_chinese_only_entry_is_found_by_its_chinese_news_id() -> None:
    when = datetime(2026, 10, 28, 22, 52, tzinfo=HKT)
    tc = make_doc(Lang.TC, 101, when, news_id=101, c_suffix=True)
    day = date(2026, 10, 28)
    drafted = pair_and_tag(
        SearchOutput([], [tc], SearchDiagnostics()), ZAI, scenario_for(ZAI, day, day)
    )
    assert find_row(drafted, to_entry(drafted, drafted.rows[0])) == 1


def test_an_entry_whose_documents_are_not_in_the_table_is_an_error() -> None:
    small, large = synthetic(3), synthetic(6)
    newest_of_large = to_entry(large, large.rows[0])  # a news id the small table lacks
    with pytest.raises(LookupError, match="not in"):
        find_row(small, newest_of_large)


def test_an_entry_corrected_to_another_chinese_file_is_still_found_by_its_english_one() -> None:
    drafted = synthetic()
    entry = to_entry(drafted, drafted.rows[2])
    assert entry.truth.tc is not None
    corrected = entry.model_copy(
        update={
            "truth": entry.truth.model_copy(
                update={"tc": entry.truth.tc.model_copy(update={"news_id": "999"})}
            )
        }
    )
    assert find_row(drafted, corrected) == 3


def test_the_same_announcement_is_found_after_pairing_again() -> None:
    drafted = synthetic()
    again = repair_with_hashes(drafted, {})
    for a in drafted.rows:
        assert counterpart(again, a) == a


def test_the_counterpart_follows_the_documents_when_their_pairing_changed() -> None:
    when = datetime(2026, 10, 28, 22, 52, tzinfo=HKT)
    en = make_doc(Lang.EN, 100, when, news_id=100)
    near = make_doc(Lang.TC, 101, when, news_id=101, c_suffix=True)
    far = make_doc(Lang.TC, 150, when, news_id=150, c_suffix=True)
    day = date(2026, 10, 28)
    scenario = scenario_for(ZAI, day, day)
    before = pair_and_tag(SearchOutput([en], [near], SearchDiagnostics()), ZAI, scenario)
    after = pair_and_tag(SearchOutput([en], [far], SearchDiagnostics()), ZAI, scenario)
    found = counterpart(after, before.rows[0])
    assert found.en is not None and found.en.news_id == "100"
    assert found.tc is not None and found.tc.news_id == "150"


def test_a_document_that_disappears_when_pairing_again_is_an_error() -> None:
    first, other = synthetic(3), synthetic(6)
    with pytest.raises(RuntimeError, match="disappeared"):
        counterpart(first, other.rows[0])
