import asyncio
from collections.abc import AsyncIterator

import httpx
import pytest
import respx

from app.domain.errors import AppError, ErrorCode
from app.hkex.client import HkexClient

URL = "https://www1.hkexnews.hk/search/titleSearchServlet.do"


class FakeTime:
    """Deterministic clock; sleeping advances it and records the delay."""

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


@pytest.fixture
async def client(ft: FakeTime) -> AsyncIterator[HkexClient]:
    c = HkexClient(
        sleep=ft.sleep,
        clock=ft.clock,
        jitter=lambda: 0.0,
        min_interval_s=0.0,
        base_backoff_s=1.0,
        max_retries=3,
    )
    yield c
    await c.aclose()


@respx.mock
async def test_returns_parsed_json(client: HkexClient) -> None:
    respx.get(URL).mock(return_value=httpx.Response(200, json={"recordCnt": 2}))
    assert await client.get_json(URL, {"lang": "ZH"}) == {"recordCnt": 2}
    assert respx.calls.last.request.url.params["lang"] == "ZH"


@respx.mock
async def test_sends_the_identifying_user_agent(client: HkexClient) -> None:
    respx.get(URL).mock(return_value=httpx.Response(200, json={}))
    await client.get_json(URL)
    ua = respx.calls.last.request.headers["user-agent"]
    assert ua.startswith("hkex-bilingual-downloader/") and "github.com" in ua


@respx.mock
async def test_server_error_then_success_is_retried_with_backoff(
    client: HkexClient, ft: FakeTime
) -> None:
    route = respx.get(URL).mock(
        side_effect=[httpx.Response(500), httpx.Response(200, json={"ok": 1})]
    )
    assert await client.get_json(URL) == {"ok": 1}
    assert route.call_count == 2
    assert ft.sleeps == [1.0]


@respx.mock
async def test_backoff_doubles_each_attempt(client: HkexClient, ft: FakeTime) -> None:
    respx.get(URL).mock(
        side_effect=[
            httpx.Response(503),
            httpx.Response(502),
            httpx.Response(500),
            httpx.Response(200, json={}),
        ]
    )
    await client.get_json(URL)
    assert ft.sleeps == [1.0, 2.0, 4.0]


@respx.mock
async def test_429_waits_for_retry_after(client: HkexClient, ft: FakeTime) -> None:
    respx.get(URL).mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "7"}),
            httpx.Response(200, json={}),
        ]
    )
    await client.get_json(URL)
    assert ft.sleeps == [7.0]


@respx.mock
async def test_retry_after_is_capped(client: HkexClient, ft: FakeTime) -> None:
    respx.get(URL).mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "3600"}),
            httpx.Response(200, json={}),
        ]
    )
    await client.get_json(URL)
    assert ft.sleeps == [30.0]


@respx.mock
async def test_persistent_429_becomes_rate_limited_after_all_retries(client: HkexClient) -> None:
    route = respx.get(URL).mock(return_value=httpx.Response(429))
    with pytest.raises(AppError) as exc:
        await client.get_json(URL)
    assert exc.value.code is ErrorCode.HKEX_RATE_LIMITED
    assert route.call_count == 4  # first try plus three retries


@respx.mock
async def test_timeouts_are_retried_then_reported_as_unavailable(client: HkexClient) -> None:
    route = respx.get(URL).mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(AppError) as exc:
        await client.get_json(URL)
    assert exc.value.code is ErrorCode.HKEX_UNAVAILABLE
    assert "didn't respond" in exc.value.message
    assert route.call_count == 4


@respx.mock
async def test_connection_reset_then_success(client: HkexClient) -> None:
    respx.get(URL).mock(
        side_effect=[httpx.RemoteProtocolError("reset"), httpx.Response(200, json={"ok": True})]
    )
    assert await client.get_json(URL) == {"ok": True}


@respx.mock
async def test_html_page_with_status_200_is_not_treated_as_data(client: HkexClient) -> None:
    respx.get(URL).mock(
        return_value=httpx.Response(
            200, text="<html>Access Denied</html>", headers={"content-type": "text/html"}
        )
    )
    with pytest.raises(AppError) as exc:
        await client.get_json(URL)
    assert exc.value.code is ErrorCode.HKEX_UNAVAILABLE


@respx.mock
async def test_forbidden_is_not_retried(client: HkexClient) -> None:
    route = respx.get(URL).mock(return_value=httpx.Response(403))
    with pytest.raises(AppError) as exc:
        await client.get_json(URL)
    assert exc.value.code is ErrorCode.HKEX_UNAVAILABLE
    assert exc.value.details == {"status": 403}
    assert route.call_count == 1


@respx.mock
async def test_redirects_are_not_followed(client: HkexClient) -> None:
    route = respx.get(URL).mock(
        return_value=httpx.Response(302, headers={"location": "https://evil.example/"})
    )
    with pytest.raises(AppError) as exc:
        await client.get_json(URL)
    assert exc.value.code is ErrorCode.HKEX_UNAVAILABLE
    assert route.call_count == 1


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.example/search/titleSearchServlet.do",
        "http://www1.hkexnews.hk/search/titleSearchServlet.do",
        "https://www1.hkexnews.hk.evil.example/x",
        "https://user@evil.example@www1.hkexnews.hk/",
        "file:///etc/passwd",
    ],
)
async def test_refuses_anything_outside_the_hkexnews_allowlist(
    client: HkexClient, url: str
) -> None:
    with pytest.raises(ValueError, match="allowlist"):
        await client.get_json(url)


@respx.mock
async def test_requests_are_spaced_by_the_minimum_interval(ft: FakeTime) -> None:
    c = HkexClient(sleep=ft.sleep, clock=ft.clock, jitter=lambda: 0.0, min_interval_s=0.25)
    respx.get(URL).mock(return_value=httpx.Response(200, json={}))
    try:
        await c.get_json(URL)
        await c.get_json(URL)
        await c.get_json(URL)
    finally:
        await c.aclose()
    assert ft.sleeps == [0.25, 0.25]


@respx.mock
async def test_concurrency_never_exceeds_the_limit(ft: FakeTime) -> None:
    in_flight = 0
    peak = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.01)
        in_flight -= 1
        return httpx.Response(200, json={})

    respx.get(URL).mock(side_effect=handler)
    c = HkexClient(
        sleep=ft.sleep, clock=ft.clock, jitter=lambda: 0.0, min_interval_s=0.0, max_concurrency=2
    )
    try:
        await asyncio.gather(*(c.get_json(URL) for _ in range(8)))
    finally:
        await c.aclose()
    assert peak == 2


@respx.mock
async def test_counts_requests_and_retries(client: HkexClient) -> None:
    respx.get(URL).mock(side_effect=[httpx.Response(500), httpx.Response(200, json={})])
    await client.get_json(URL)
    assert (client.requests_made, client.retries_made) == (2, 1)
