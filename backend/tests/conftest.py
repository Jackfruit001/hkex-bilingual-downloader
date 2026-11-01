"""Shared helpers for tests that replay recorded HKEXnews responses (Phase 0 fixtures)."""

import json
import re
from pathlib import Path
from typing import Any

import pytest

from app.domain.models import Document, Lang
from app.hkex.parse import RowError, parse_row

RAW = Path(__file__).parent / "fixtures" / "raw"
GOLDEN_CALLS = Path(__file__).parent / "fixtures" / "golden"


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


def _rows(result: Any) -> list[dict[str, Any]]:
    rows = json.loads(result) if isinstance(result, str) and result != "null" else []
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def recorded_documents() -> list[Document]:
    """Every distinct document in every recorded search response (probe and golden calls).

    The language comes from the file name (`en_1.json`, `zh_1.json`) or the recorded request
    (`lang` is `EN` or `ZH`). Rows that do not parse are left out, as the search code does.
    """
    found: dict[tuple[Lang, str], Document] = {}

    def add(lang: Lang, result: Any) -> None:
        for row in _rows(result):
            try:
                doc = parse_row(row, lang)
            except RowError:
                continue
            found.setdefault((lang, doc.path), doc)

    for path in sorted(RAW.glob("*/*.json")):
        m = re.fullmatch(r"(en|zh)_\d+\.json", path.name)
        if m:
            add(
                Lang.EN if m.group(1) == "en" else Lang.TC,
                json.loads(path.read_text("utf-8")).get("result"),
            )
    for path in sorted(GOLDEN_CALLS.glob("*/calls/*.json")):
        call = json.loads(path.read_text("utf-8"))
        add(Lang.TC if call["params"].get("lang") == "ZH" else Lang.EN, call["body"].get("result"))
    return list(found.values())
