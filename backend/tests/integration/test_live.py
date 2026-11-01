"""Opt-in smoke test against the real HKEXnews. Run with: uv run pytest -m live"""

import zipfile
from datetime import date
from pathlib import Path

import pytest

from app.domain.models import Lang
from app.downloads.fetcher import Fetcher
from app.downloads.zipper import build_zip
from app.hkex.client import HkexClient
from app.hkex.reference import ReferenceService
from app.hkex.search import search_both
from app.naming.filenames import name_documents

pytestmark = pytest.mark.live


async def test_zai_lab_on_28_october_2026_has_two_pairs() -> None:
    client = HkexClient()
    try:
        reference = await ReferenceService(client).get()
        assert reference.source == "live"
        stock = reference.stocks.resolve("09688")
        out = await search_both(
            client, stock, date(2026, 10, 28), date(2026, 10, 28), reference.categories
        )
    finally:
        await client.aclose()
    assert out.diagnostics.warnings == []
    assert [d.seq for d in out.english] == [1739, 1671]
    assert [d.seq for d in out.chinese] == [1740, 1672]
    assert all(d.lang is Lang.TC and d.path.endswith("_c.pdf") for d in out.chinese)
    assert all(
        a.category_codes == b.category_codes != ()
        for a, b in zip(out.english, out.chinese, strict=True)
    )


async def test_a_real_pair_is_downloaded_verified_and_zipped(tmp_path: Path) -> None:
    """Gate 3: two real PDFs, one at a time, at least a second apart; the ZIP opens."""
    client = HkexClient(max_concurrency=1, min_interval_s=1.0)
    try:
        reference = await ReferenceService(client).get()
        stock = reference.stocks.resolve("09688").stock
        out = await search_both(
            client, stock, date(2026, 10, 28), date(2026, 10, 28), reference.categories
        )
        names = name_documents([*out.english, *out.chinese], "09688")
        en, tc = out.english[0], out.chinese[0]
        fetcher = Fetcher(client, directory=tmp_path / "cache")
        files = [(names[d.path], await fetcher.fetch(d.path)) for d in (en, tc)]
    finally:
        await client.aclose()
    target = tmp_path / "pair.zip"
    build_zip(target, files)
    with zipfile.ZipFile(target) as archive:
        assert archive.testzip() is None
        assert sorted(archive.namelist()) == sorted([*(n for n, _ in files), "sources.csv"])
        for name, verified in files:
            assert archive.read(name) == verified.file.read_bytes()
            assert archive.read(name).startswith(b"%PDF-")
