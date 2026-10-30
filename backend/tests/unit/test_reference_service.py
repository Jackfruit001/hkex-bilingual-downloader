import gzip
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import respx

from app.domain.errors import AppError, ErrorCode
from app.domain.models import Lang
from app.hkex.client import HkexClient
from app.hkex.parse import parse_category_text
from app.hkex.reference import (
    REFERENCE_FILES,
    ReferenceService,
    build_snapshot,
    load_snapshot,
)
from tests.conftest import RAW, raw_json

BASE = "https://www1.hkexnews.hk/ncms/script/eds/"


async def no_sleep(_: float) -> None:
    return None


class Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


@pytest.fixture
async def client() -> AsyncIterator[HkexClient]:
    c = HkexClient(sleep=no_sleep, min_interval_s=0.0, jitter=lambda: 0.0, max_retries=0)
    yield c
    await c.aclose()


@pytest.fixture(scope="module")
def snapshot_file(tmp_path_factory: pytest.TempPathFactory) -> Path:
    raw = {n: raw_json(f"reference/{n}.json") for n in REFERENCE_FILES}
    path = tmp_path_factory.mktemp("snap") / "reference_snapshot.json.gz"
    path.write_bytes(build_snapshot(raw, generated_at=datetime(2026, 10, 30, 12, 0, tzinfo=UTC)))
    return path


def serve_live(fail: bool = False) -> respx.Route:
    def handler(request: httpx.Request) -> httpx.Response:
        if fail:
            return httpx.Response(503)
        name = request.url.path.rsplit("/", 1)[-1]
        return httpx.Response(200, content=(RAW / "reference" / name).read_bytes())

    return respx.get(url__startswith=BASE).mock(side_effect=handler)


def service(
    client: HkexClient, clock: Clock, snapshot: Path | None, ttl: float = 100.0
) -> ReferenceService:
    return ReferenceService(
        client,
        ttl_s=ttl,
        retry_after_failure_s=50.0,
        clock=clock,
        now=lambda: datetime(2026, 10, 30, 13, 0, tzinfo=UTC),
        snapshot_path=snapshot,
    )


# --- snapshot ---


def test_snapshot_is_small_and_round_trips(snapshot_file: Path) -> None:
    assert snapshot_file.stat().st_size < 1_000_000
    data = load_snapshot(snapshot_file)
    assert data.source == "snapshot"
    assert data.as_of == datetime(2026, 10, 30, 12, 0, tzinfo=UTC)
    assert [s.name_en for s in data.stocks.lookup("00700")] == ["TENCENT", "YAOHAN INT'L"]
    assert data.stocks.lookup("00700")[0].name_tc == "騰訊控股"
    assert len(data.stocks.lookup("03333")) == 3
    assert data.stocks.resolve("00013", stock_id=20).active is False
    codes = data.categories.resolve(Lang.TC, parse_category_text("翌日披露報表 - [其他]"))
    assert codes == data.categories.resolve(
        Lang.EN, parse_category_text("Next Day Disclosure Returns - [Others]")
    )


def test_snapshot_has_the_same_directory_as_the_raw_lists(snapshot_file: Path) -> None:
    data = load_snapshot(snapshot_file)
    assert len(data.stocks) == 17399 + 884


def test_a_damaged_snapshot_is_reported(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json.gz"
    bad.write_bytes(gzip.compress(b"{not json"))
    with pytest.raises(AppError) as exc:
        load_snapshot(bad)
    assert exc.value.code is ErrorCode.HKEX_UNAVAILABLE


# --- live loading, cache and fallback ---


@respx.mock
async def test_first_use_loads_the_eight_reference_files_live(
    client: HkexClient, snapshot_file: Path
) -> None:
    route = serve_live()
    data = await service(client, Clock(), snapshot_file).get()
    assert data.source == "live"
    assert route.call_count == 8
    assert data.stocks.resolve("09688").name_en == "ZAI LAB"


@respx.mock
async def test_data_is_reused_until_the_ttl_expires(
    client: HkexClient, snapshot_file: Path
) -> None:
    route = serve_live()
    clock = Clock()
    svc = service(client, clock, snapshot_file, ttl=100.0)
    await svc.get()
    clock.t = 99.0
    await svc.get()
    assert route.call_count == 8
    clock.t = 101.0
    await svc.get()
    assert route.call_count == 16


@respx.mock
async def test_concurrent_callers_share_one_load(client: HkexClient, snapshot_file: Path) -> None:
    import asyncio

    route = serve_live()
    svc = service(client, Clock(), snapshot_file)
    results = await asyncio.gather(*(svc.get() for _ in range(5)))
    assert route.call_count == 8
    assert all(r is results[0] for r in results)


@respx.mock
async def test_falls_back_to_the_snapshot_when_hkexnews_is_unreachable(
    client: HkexClient, snapshot_file: Path
) -> None:
    serve_live(fail=True)
    data = await service(client, Clock(), snapshot_file).get()
    assert data.source == "snapshot"
    assert data.stocks.resolve("09688").stock_id == 1000057951


@respx.mock
async def test_while_on_the_snapshot_live_loading_is_not_retried_on_every_request(
    client: HkexClient, snapshot_file: Path
) -> None:
    route = serve_live(fail=True)
    clock = Clock()
    svc = service(client, clock, snapshot_file)
    await svc.get()
    calls_after_first = route.call_count
    clock.t = 10.0
    await svc.get()
    assert route.call_count == calls_after_first
    clock.t = 60.0  # past retry_after_failure_s
    await svc.get()
    assert route.call_count > calls_after_first


@respx.mock
async def test_recovers_to_live_data_when_hkexnews_returns(
    client: HkexClient, snapshot_file: Path
) -> None:
    serve_live(fail=True)
    clock = Clock()
    svc = service(client, clock, snapshot_file)
    assert (await svc.get()).source == "snapshot"
    respx.reset()
    serve_live()
    clock.t = 60.0
    assert (await svc.get()).source == "live"


@respx.mock
async def test_stale_live_data_is_kept_when_a_refresh_fails(
    client: HkexClient, snapshot_file: Path
) -> None:
    serve_live()
    clock = Clock()
    svc = service(client, clock, snapshot_file, ttl=100.0)
    first = await svc.get()
    respx.reset()
    serve_live(fail=True)
    clock.t = 150.0
    again = await svc.get()
    assert again is first and again.source == "live"


@respx.mock
async def test_with_no_snapshot_the_error_is_raised(client: HkexClient) -> None:
    serve_live(fail=True)
    with pytest.raises(AppError) as exc:
        await service(client, Clock(), None).get()
    assert exc.value.code is ErrorCode.HKEX_UNAVAILABLE


@respx.mock
async def test_a_truncated_live_list_is_not_accepted(
    client: HkexClient, snapshot_file: Path
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        name = request.url.path.rsplit("/", 1)[-1]
        if name.startswith("activestock"):
            return httpx.Response(200, json=[{"i": 1, "c": "00001", "n": "X"}])
        return httpx.Response(200, content=(RAW / "reference" / name).read_bytes())

    respx.get(url__startswith=BASE).mock(side_effect=handler)
    data = await service(client, Clock(), snapshot_file).get()
    assert data.source == "snapshot"


def test_reference_files_are_the_eight_the_probe_recorded() -> None:
    assert len(REFERENCE_FILES) == 8
    for name in REFERENCE_FILES:
        assert isinstance(
            json.loads((RAW / "reference" / f"{name}.json").read_text(encoding="utf-8")), list
        )


def test_the_bundled_snapshot_is_present_and_usable() -> None:
    from app.hkex.reference import DEFAULT_SNAPSHOT

    data = load_snapshot(DEFAULT_SNAPSHOT)
    assert data.source == "snapshot"
    assert len(data.stocks) > 17000
    assert data.stocks.resolve("09688").name_en == "ZAI LAB"
