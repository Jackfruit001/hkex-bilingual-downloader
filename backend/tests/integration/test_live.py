"""Opt-in smoke test against the real HKEXnews. Run with: uv run pytest -m live"""

from datetime import date

import pytest

from app.domain.models import Lang
from app.hkex.client import HkexClient
from app.hkex.reference import ReferenceService
from app.hkex.search import search_both

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
