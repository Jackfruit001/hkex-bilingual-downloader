"""The golden test (SPEC §10.4, Phase 2.6): the matcher against hand-verified pairs. Offline.

Every verified entry in `tests/golden/pairs.yaml` is judged against what the matcher makes of the
recorded search results for its scenario (`tests/fixtures/golden/`, replayed with no live
requests). Only `truth` is read; the entry's `proposal` is ignored.

Two runs are judged, and both must show no wrong `matched`:

- structural: the matcher's rules, plus identical-bytes evidence (S5) from `fingerprints.json`;
- with content check: the same, plus the content check (S7) that "Check contents" would add,
  computed from the figures recorded in `fingerprints.json`.

Run with `-s` to see the metrics table:
`uv run pytest tests/integration/test_golden.py -s`
"""

import asyncio
from pathlib import Path

import pytest

from app.hkex.reference import DEFAULT_SNAPSHOT, load_snapshot
from app.pairing.models import Announcement
from tests.golden.draft import load_scenario, pair_and_tag, repair_with_hashes, search_and_pair
from tests.golden.fetch import GoldenClient
from tests.golden.outcome import Outcome, Report, content_evidence, judge_all, render
from tests.golden.store import load_entries, load_facts

FIXTURES = Path(__file__).parents[1] / "fixtures" / "golden"
STRUCTURAL = "structural"
WITH_CONTENT = "with content check"

ENTRIES = [e for e in load_entries() if e.verified]

# Wrong `matched` results known and open, as (run, entry id). Each needs a reason and is dropped when
# it is fixed: the marker is strict, so a fixed entry fails the run until it is removed.
KNOWN_WRONG = {
    (WITH_CONTENT, "00005-303146"): (
        "M-014: HSBC, 31 March 2005. The D-009 fallback keeps the pair a check, but 'Check contents' "
        "confirms English file 96 with Chinese file 96 (92% of figures match) because the matcher "
        "lists no rival: the right partner, Chinese file 95, scores 3 and the check candidates "
        "start at 4. The two scrip forms share their figures. Open after Gate 2."
    ),
}


async def replay(scenario_folder: Path, tmp: Path) -> tuple[list[Announcement], list[Announcement]]:
    reference = load_snapshot(DEFAULT_SNAPSHOT)
    scenario = load_scenario(scenario_folder)
    stock = reference.stocks.resolve(scenario.code, scenario.stock_id).stock
    client = GoldenClient(json_dir=scenario_folder / "calls", pdf_dir=tmp, budget=0)
    try:
        drafted = await search_and_pair(client, stock, reference.categories, scenario)
    finally:
        await client.aclose()
    facts = load_facts()
    structural = repair_with_hashes(drafted, facts)
    with_content = pair_and_tag(
        structural.search,
        structural.stock,
        structural.scenario,
        content_evidence(structural.result, facts),
    )
    return list(structural.result.announcements), list(with_content.result.announcements)


@pytest.fixture(scope="module")
def runs(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Report]:
    tmp = tmp_path_factory.mktemp("golden-pdfs")
    structural: dict[str, list[Announcement]] = {}
    with_content: dict[str, list[Announcement]] = {}
    for name in sorted({e.scenario for e in ENTRIES}):
        structural[name], with_content[name] = asyncio.run(replay(FIXTURES / name, tmp))
    return {
        STRUCTURAL: Report(tuple(judge_all(ENTRIES, structural))),
        WITH_CONTENT: Report(tuple(judge_all(ENTRIES, with_content))),
    }


def _cases() -> list[object]:
    cases: list[object] = []
    for run in (STRUCTURAL, WITH_CONTENT):
        for e in ENTRIES:
            reason = KNOWN_WRONG.get((run, e.id))
            marks = [pytest.mark.xfail(strict=True, reason=reason)] if reason else []
            cases.append(pytest.param(run, e.id, id=f"{run}: {e.id}", marks=marks))
    return cases


@pytest.mark.parametrize(("run", "entry_id"), _cases())
def test_no_entry_is_confirmed_wrongly(runs: dict[str, Report], run: str, entry_id: str) -> None:
    judgement = next(j for j in runs[run].judgements if j.entry_id == entry_id)
    assert judgement.outcome is not Outcome.MATCHED_WRONG, judgement.detail


def test_the_known_failures_name_entries_that_are_in_the_golden_set() -> None:
    assert {entry_id for _, entry_id in KNOWN_WRONG} <= {e.id for e in ENTRIES}


# Pairs whose two headlines carry the same revision marker in both languages: `(Revised)` and
# `(經修訂)` in the title, `(Headline Revised)` and `(修改後標題)` in the category prefix.
REVISED_PAIRS = ("00013-2104022", "06909-12089411", "08223-12110929", "08223-12104235")


@pytest.mark.parametrize("run", [STRUCTURAL, WITH_CONTENT])
@pytest.mark.parametrize("entry_id", REVISED_PAIRS)
def test_a_pair_revised_in_both_languages_is_confirmed(
    runs: dict[str, Report], run: str, entry_id: str
) -> None:
    judgement = next(j for j in runs[run].judgements if j.entry_id == entry_id)
    assert judgement.outcome is Outcome.MATCHED_RIGHT, judgement.detail


def test_the_golden_set_is_big_enough_to_mean_something() -> None:
    assert len(ENTRIES) >= 50
    assert len({e.stock_code for e in ENTRIES}) >= 12


@pytest.mark.parametrize("run", [STRUCTURAL, WITH_CONTENT])
def test_every_verified_entry_is_found_in_the_replay(runs: dict[str, Report], run: str) -> None:
    assert [(j.entry_id, j.detail) for j in runs[run].missing] == []


def test_the_metrics_table_lists_every_entry_that_is_not_confirmed(
    runs: dict[str, Report],
) -> None:
    text = render(runs, issuers=len({e.stock_code for e in ENTRIES}))
    print("\n" + text)
    for j in runs[STRUCTURAL].judgements:
        confirmed_in_both = all(
            r.outcome is Outcome.MATCHED_RIGHT
            for run in runs.values()
            for r in run.judgements
            if r.entry_id == j.entry_id
        )
        assert (j.entry_id in text) is not confirmed_in_both
