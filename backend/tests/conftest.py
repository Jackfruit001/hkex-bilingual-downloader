"""Shared helpers for tests that replay recorded HKEXnews responses (Phase 0 fixtures)."""

import json
from pathlib import Path
from typing import Any

import pytest

RAW = Path(__file__).parent / "fixtures" / "raw"


def raw_json(relative: str) -> Any:
    return json.loads((RAW / relative).read_text(encoding="utf-8"))


def scenario_rows(scenario: str, lang: str) -> list[dict[str, Any]]:
    """Rows from the last recorded call for a language (the cumulative set)."""
    files = sorted((RAW / scenario).glob(f"{lang}_[0-9].json"), key=lambda f: f.stem)
    if not files:
        return []
    result = json.loads(files[-1].read_text(encoding="utf-8")).get("result")
    rows = json.loads(result) if result and result != "null" else []
    return list(rows)


def scenario_names() -> list[str]:
    return sorted(p.name for p in RAW.iterdir() if (p / "scenario.json").exists())


@pytest.fixture(scope="session")
def reference_raw() -> dict[str, Any]:
    names = [
        "activestock_sehk_e",
        "activestock_sehk_c",
        "inactivestock_sehk_e",
        "inactivestock_sehk_c",
        "tierone_e",
        "tierone_c",
        "tiertwo_e",
        "tiertwo_c",
    ]
    return {n: raw_json(f"reference/{n}.json") for n in names}
