"""The helper's live access: cached, paced, budgeted, and it stops at the first sign of a block."""

import json
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import respx

from app.domain.errors import AppError, ErrorCode
from tests.golden.fetch import (
    BudgetReached,
    FileTooLarge,
    GoldenClient,
    HelperStopped,
    size_label_bytes,
)
from tests.support import make_pdf

SEARCH = "https://www1.hkexnews.hk/search/titleSearchServlet.do"
PDF_URL = "https://www1.hkexnews.hk/listedco/listconews/sehk/2026/1028/2026102801739.pdf"


class FakeTime:
    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.fixture
def ft() -> FakeTime:
    return FakeTime()


def make_client(tmp_path: Path, ft: FakeTime, **kw: object) -> GoldenClient:
    return GoldenClient(
        json_dir=tmp_path / "json",
        pdf_dir=tmp_path / "pdf",
        sleep=ft.sleep,
        clock=ft.clock,
        **kw,  # type: ignore[arg-type]
    )


@pytest.fixture
async def client(tmp_path: Path, ft: FakeTime) -> AsyncIterator[GoldenClient]:
    c = make_client(tmp_path, ft)
    yield c
    await c.aclose()


PDF = make_pdf([["Hello 2026"]])


# --- search responses -------------------------------------------------------------------------


@respx.mock
async def test_a_search_is_fetched_once_and_then_served_from_disk(
    tmp_path: Path, ft: FakeTime
) -> None:
    route = respx.get(SEARCH).mock(return_value=httpx.Response(200, json={"recordCnt": 2}))
    first = make_client(tmp_path, ft)
    assert await first.get_json(SEARCH, {"lang": "EN", "rowRange": 100}) == {"recordCnt": 2}
    await first.aclose()

    second = make_client(tmp_path, ft)
    assert await second.get_json(SEARCH, {"rowRange": 100, "lang": "EN"}) == {"recordCnt": 2}
    await second.aclose()
    assert route.call_count == 1
    assert second.requests_made == 0


@respx.mock
async def test_different_parameters_are_different_cache_entries(client: GoldenClient) -> None:
    route = respx.get(SEARCH).mock(return_value=httpx.Response(200, json={}))
    await client.get_json(SEARCH, {"lang": "EN"})
    await client.get_json(SEARCH, {"lang": "ZH"})
    assert route.call_count == 2


@respx.mock
async def test_every_answered_call_is_recorded_whether_cached_or_live(
    tmp_path: Path, ft: FakeTime
) -> None:
    respx.get(SEARCH).mock(return_value=httpx.Response(200, json={"n": 1}))
    first = make_client(tmp_path, ft)
    await first.get_json(SEARCH, {"lang": "EN"})
    await first.aclose()
    second = make_client(tmp_path, ft)
    await second.get_json(SEARCH, {"lang": "EN"})
    await second.aclose()
    for c in (first, second):
        assert len(c.calls) == 1
        call = c.calls[0]
        assert call.url == SEARCH and call.params == {"lang": "EN"} and call.body == {"n": 1}
        assert (tmp_path / "json" / f"{call.key}.json").exists()


@respx.mock
async def test_the_cache_file_holds_the_request_beside_the_response(
    client: GoldenClient, tmp_path: Path
) -> None:
    respx.get(SEARCH).mock(return_value=httpx.Response(200, json={"n": 1}))
    await client.get_json(SEARCH, {"lang": "EN"})
    (file,) = (tmp_path / "json").glob("*.json")
    assert json.loads(file.read_text(encoding="utf-8")) == {
        "url": SEARCH,
        "params": {"lang": "EN"},
        "body": {"n": 1},
    }


@respx.mock
async def test_a_budget_of_zero_means_offline_and_a_miss_makes_no_request(
    tmp_path: Path, ft: FakeTime
) -> None:
    route = respx.get(SEARCH).mock(return_value=httpx.Response(200, json={}))
    offline = make_client(tmp_path, ft, budget=0)
    with pytest.raises(BudgetReached):
        await offline.get_json(SEARCH, {"lang": "EN"})
    await offline.aclose()
    assert route.call_count == 0


@respx.mock
async def test_the_budget_counts_live_requests_only(tmp_path: Path, ft: FakeTime) -> None:
    route = respx.get(SEARCH).mock(return_value=httpx.Response(200, json={}))
    c = make_client(tmp_path, ft, budget=1)
    await c.get_json(SEARCH, {"n": 1})
    await c.get_json(SEARCH, {"n": 1})  # cached: free
    with pytest.raises(BudgetReached):
        await c.get_json(SEARCH, {"n": 2})
    await c.aclose()
    assert route.call_count == 1


@respx.mock
async def test_live_requests_are_at_least_a_second_apart(
    client: GoldenClient, ft: FakeTime
) -> None:
    respx.get(SEARCH).mock(return_value=httpx.Response(200, json={}))
    respx.get(PDF_URL).mock(return_value=httpx.Response(200, content=PDF))
    await client.get_json(SEARCH, {"n": 1})
    await client.get_pdf(PDF_URL, "a.pdf")
    await client.get_json(SEARCH, {"n": 2})
    assert sum(ft.sleeps) >= 2.0
    assert all(s >= 0.99 for s in ft.sleeps)


@respx.mock
async def test_the_first_429_ends_the_run_without_a_retry(client: GoldenClient) -> None:
    route = respx.get(SEARCH).mock(return_value=httpx.Response(429, headers={"Retry-After": "1"}))
    with pytest.raises(AppError) as caught:
        await client.get_json(SEARCH, {"n": 1})
    assert caught.value.code is ErrorCode.HKEX_RATE_LIMITED
    assert route.call_count == 1


@respx.mock
async def test_the_first_403_ends_the_run(client: GoldenClient) -> None:
    route = respx.get(SEARCH).mock(return_value=httpx.Response(403))
    with pytest.raises(AppError):
        await client.get_json(SEARCH, {"n": 1})
    assert route.call_count == 1


@respx.mock
async def test_a_challenge_page_with_status_200_ends_the_run_and_is_not_cached(
    client: GoldenClient, tmp_path: Path
) -> None:
    route = respx.get(SEARCH).mock(return_value=httpx.Response(200, text="<html>challenge</html>"))
    with pytest.raises(AppError):
        await client.get_json(SEARCH, {"n": 1})
    assert route.call_count == 1
    assert not list((tmp_path / "json").glob("*.json"))


@respx.mock
async def test_the_request_identifies_the_tool(client: GoldenClient) -> None:
    respx.get(SEARCH).mock(return_value=httpx.Response(200, json={}))
    await client.get_json(SEARCH)
    assert respx.calls.last.request.headers["user-agent"].startswith("hkex-bilingual-downloader/")


# --- PDFs -------------------------------------------------------------------------------------


@respx.mock
async def test_a_pdf_is_fetched_once_and_cached_under_the_name_given(
    tmp_path: Path, ft: FakeTime
) -> None:
    route = respx.get(PDF_URL).mock(return_value=httpx.Response(200, content=PDF))
    first = make_client(tmp_path, ft)
    assert await first.get_pdf(PDF_URL, "EN_a.pdf") == PDF
    await first.aclose()
    assert (tmp_path / "pdf" / "EN_a.pdf").read_bytes() == PDF

    second = make_client(tmp_path, ft)
    assert await second.get_pdf(PDF_URL, "EN_a.pdf") == PDF
    await second.aclose()
    assert route.call_count == 1


@respx.mock
async def test_a_url_off_the_allowlist_is_refused_before_any_request(client: GoldenClient) -> None:
    route = respx.route().mock(return_value=httpx.Response(200, content=PDF))
    for url in (
        "https://example.com/a.pdf",
        "http://www1.hkexnews.hk/a.pdf",
        "https://www1.hkexnews.hk.evil.test/a.pdf",
    ):
        with pytest.raises(ValueError, match="allowlist"):
            await client.get_pdf(url, "x.pdf")
    assert route.call_count == 0


@respx.mock
async def test_a_redirect_is_not_followed(client: GoldenClient) -> None:
    respx.get(PDF_URL).mock(
        return_value=httpx.Response(302, headers={"Location": "https://example.com/a.pdf"})
    )
    with pytest.raises(HelperStopped, match="302"):
        await client.get_pdf(PDF_URL, "x.pdf")


@respx.mock
@pytest.mark.parametrize("status", [403, 404, 429, 500])
async def test_any_bad_status_ends_the_run_and_caches_nothing(
    client: GoldenClient, tmp_path: Path, status: int
) -> None:
    route = respx.get(PDF_URL).mock(return_value=httpx.Response(status))
    with pytest.raises(HelperStopped, match=str(status)):
        await client.get_pdf(PDF_URL, "x.pdf")
    assert route.call_count == 1
    assert not list((tmp_path / "pdf").glob("*"))


@respx.mock
async def test_an_html_page_where_a_pdf_was_expected_ends_the_run(
    client: GoldenClient, tmp_path: Path
) -> None:
    respx.get(PDF_URL).mock(return_value=httpx.Response(200, text="<html>blocked</html>"))
    with pytest.raises(HelperStopped, match="not a PDF"):
        await client.get_pdf(PDF_URL, "x.pdf")
    assert not list((tmp_path / "pdf").glob("*"))


@respx.mock
async def test_a_body_shorter_than_content_length_is_incomplete_and_not_cached(
    client: GoldenClient, tmp_path: Path
) -> None:
    respx.get(PDF_URL).mock(
        return_value=httpx.Response(
            200, content=PDF, headers={"Content-Length": str(len(PDF) + 50)}
        )
    )
    with pytest.raises(HelperStopped, match="incomplete"):
        await client.get_pdf(PDF_URL, "x.pdf")
    assert not list((tmp_path / "pdf").glob("*"))


@respx.mock
async def test_a_file_over_the_size_cap_is_skipped_not_fatal(tmp_path: Path, ft: FakeTime) -> None:
    respx.get(PDF_URL).mock(return_value=httpx.Response(200, content=PDF + b"0" * 500))
    c = make_client(tmp_path, ft, max_bytes=100)
    with pytest.raises(FileTooLarge):
        await c.get_pdf(PDF_URL, "x.pdf")
    await c.aclose()
    assert not list((tmp_path / "pdf").glob("*"))
    assert not issubclass(FileTooLarge, HelperStopped)


@respx.mock
async def test_a_pdf_miss_over_budget_makes_no_request(tmp_path: Path, ft: FakeTime) -> None:
    route = respx.get(PDF_URL).mock(return_value=httpx.Response(200, content=PDF))
    c = make_client(tmp_path, ft, budget=0)
    with pytest.raises(BudgetReached):
        await c.get_pdf(PDF_URL, "x.pdf")
    await c.aclose()
    assert route.call_count == 0


@respx.mock
async def test_pdf_requests_count_against_the_same_budget(tmp_path: Path, ft: FakeTime) -> None:
    respx.get(SEARCH).mock(return_value=httpx.Response(200, json={}))
    respx.get(PDF_URL).mock(return_value=httpx.Response(200, content=PDF))
    c = make_client(tmp_path, ft, budget=1)
    await c.get_json(SEARCH, {"n": 1})
    with pytest.raises(BudgetReached):
        await c.get_pdf(PDF_URL, "x.pdf")
    await c.aclose()


@respx.mock
async def test_a_cached_pdf_is_still_checked_so_a_bad_file_is_never_trusted(
    tmp_path: Path, ft: FakeTime
) -> None:
    (tmp_path / "pdf").mkdir()
    (tmp_path / "pdf" / "x.pdf").write_bytes(b"<html>left over</html>")
    route = respx.get(PDF_URL).mock(return_value=httpx.Response(200, content=PDF))
    c = make_client(tmp_path, ft)
    assert await c.get_pdf(PDF_URL, "x.pdf") == PDF
    await c.aclose()
    assert route.call_count == 1
    assert (tmp_path / "pdf" / "x.pdf").read_bytes() == PDF


async def test_a_cache_name_cannot_escape_the_cache_folder(client: GoldenClient) -> None:
    with pytest.raises(ValueError, match="name"):
        await client.get_pdf(PDF_URL, "../evil.pdf")


# --- size labels ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("84KB", 84 * 1024),
        ("1.5MB", int(1.5 * 1024 * 1024)),
        ("2MB", 2 * 1024 * 1024),
        ("1 GB", 1024**3),
        ("512B", 512),
        ("Multi-Files", None),
        ("", None),
    ],
)
def test_size_labels_become_bytes(label: str, expected: int | None) -> None:
    assert size_label_bytes(label) == expected
