"""Pairing over every recorded Phase 0 scenario (real HKEXnews rows, offline).

The structural checks here are computed from the documents directly, not from the matcher's own
scores, so they can catch the matcher being wrong in the same way twice. The counts are a
regression record, reviewed by hand on 31 October 2026; the golden set (Phase 2.5) is the real
correctness test.
"""

import random
from collections import Counter, defaultdict
from datetime import datetime
from itertools import pairwise
from typing import Any

import pytest

from app.domain.models import Document, Lang
from app.hkex.parse import has_chinese_suffix, parse_row
from app.hkex.reference import CategoryIndex
from app.pairing.matcher import pair_documents
from app.pairing.models import PairingResult, Status
from tests.conftest import scenario_names, scenario_rows


@pytest.fixture(scope="module")
def categories(reference_raw: dict[str, Any]) -> CategoryIndex:
    r = reference_raw
    return CategoryIndex.from_raw(r["tierone_e"], r["tiertwo_e"], r["tierone_c"], r["tiertwo_c"])


def load(name: str, categories: CategoryIndex) -> tuple[list[Document], list[Document]]:
    sides: list[list[Document]] = []
    for lang, key in ((Lang.EN, "en"), (Lang.TC, "zh")):
        docs: list[Document] = []
        for raw in scenario_rows(name, key):
            docs.append(parse_row(raw, lang, categories))  # every recorded row parses
        sides.append(docs)
    return sides[0], sides[1]


NAMES = [n for n in scenario_names() if n not in ("no-results", "english-only-issuer")]


@pytest.fixture(scope="module")
def runs(
    categories: CategoryIndex,
) -> dict[str, tuple[list[Document], list[Document], PairingResult]]:
    out = {}
    for name in NAMES:
        english, chinese = load(name, categories)
        out[name] = (english, chinese, pair_documents(english, chinese))
    return out


def counts(result: PairingResult) -> tuple[int, int, int, int]:
    c = Counter(a.status for a in result.announcements)
    return (c[Status.MATCHED], c[Status.CHECK], c[Status.EN_ONLY], c[Status.TC_ONLY])


# matched, check, en_only, tc_only. `zai-lab-nddr`, `form-8k-en-only`, `a-plus-h-30d`,
# `results-day`, `tencent-30d`, `annual-report-season`, `listing-docs` are fully structural:
# every English document with a Chinese file at +1 in the same minute is matched, every stub
# turns its document into a single-language entry.
EXPECTED = {
    "zai-lab-nddr": (2, 0, 0, 0),
    "form-8k-en-only": (3, 0, 1, 0),
    "a-plus-h-30d": (8, 0, 0, 1),
    "results-day": (7, 0, 8, 0),
    "tencent-30d": (17, 0, 0, 0),
    "annual-report-season": (33, 0, 0, 0),
    "listing-docs": (2, 0, 0, 0),
    "reused-code": (54, 0, 8, 0),
    "large-range": (784, 0, 790, 0),
    # 2015 Hutchison: Rule 22 dealing batches (block layout) are check, never matched.
    "delisted": (676, 1010, 1, 0),
    # 2005: exact number + `_c` + same minute are matched (D-009); 91 more English files than
    # Chinese ones are unexplained (research notes, Open).
    "old-docs": (22, 11, 92, 2),
}


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_status_counts_are_the_reviewed_ones(
    name: str, runs: dict[str, tuple[list[Document], list[Document], PairingResult]]
) -> None:
    assert counts(runs[name][2]) == EXPECTED[name]


def test_every_recorded_scenario_has_a_reviewed_count() -> None:
    assert set(NAMES) == set(EXPECTED)


@pytest.mark.parametrize("name", NAMES)
def test_every_document_and_stub_is_accounted_for(
    name: str, runs: dict[str, tuple[list[Document], list[Document], PairingResult]]
) -> None:
    english, chinese, result = runs[name]
    shown = Counter()
    stubs = 0
    for a in result.announcements:
        for doc in (a.en, a.tc):
            if doc is not None:
                assert not doc.is_stub
                shown[(doc.lang, doc.news_id)] += 1
        stubs += a.stub is not None
    expected = Counter((d.lang, d.news_id) for d in english + chinese if not d.is_stub)
    assert shown == expected
    total_stubs = sum(d.is_stub for d in english + chinese)
    assert stubs + result.diagnostics.orphan_stubs == total_stubs


def test_no_stub_in_the_recorded_data_is_left_unclaimed(
    runs: dict[str, tuple[list[Document], list[Document], PairingResult]],
) -> None:
    assert {
        n: runs[n][2].diagnostics.orphan_stubs for n in NAMES if runs[n][2].diagnostics.orphan_stubs
    } == {}


def peers(
    english: list[Document], chinese: list[Document], result: PairingResult, doc: Document
) -> list[Document]:
    """Unclaimed real documents sharing this document's minute and folder (the D-011 group)."""
    claimed = {id(x) for a in result.announcements if a.stub for x in (a.en, a.tc) if x}
    return [
        d
        for d in english + chinese
        if not d.is_stub
        and id(d) not in claimed
        and d.release_at == doc.release_at
        and d.folder_date == doc.folder_date
    ]


@pytest.mark.parametrize("name", NAMES)
def test_a_matched_pair_never_sits_in_a_same_minute_block(
    name: str, runs: dict[str, tuple[list[Document], list[Document], PairingResult]]
) -> None:
    english, chinese, result = runs[name]
    for a in result.announcements:
        if a.status is not Status.MATCHED or a.bilingual:
            continue
        assert a.en and a.tc
        if a.tc.seq == a.en.seq and has_chinese_suffix(a.tc.path):
            continue  # 2005 numbering: the exact number identifies the pair
        group = peers(english, chinese, result, a.en)
        for lang in (Lang.EN, Lang.TC):
            seqs = sorted(d.seq for d in group if d.lang is lang and d.seq is not None)
            assert not any(y - x == 1 for x, y in pairwise(seqs)), (name, a.id, seqs)


def test_the_hutchison_rule_22_batches_are_all_check(
    runs: dict[str, tuple[list[Document], list[Document], PairingResult]],
) -> None:
    english, chinese, result = runs["delisted"]
    groups: dict[tuple[datetime, Any], list[tuple[int, str, Document]]] = defaultdict(list)
    for lang, docs in ((Lang.EN, english), (Lang.TC, chinese)):
        for d in docs:
            if not d.is_stub and d.seq is not None:
                groups[(d.release_at, d.folder_date)].append((d.seq, lang.value, d))
    blocks = 0
    by_doc = {}
    for a in result.announcements:
        for d in (a.en, a.tc):
            if d is not None:
                by_doc[(d.lang, d.news_id)] = a
    for items in groups.values():
        items.sort(key=lambda i: i[0])
        pattern = "".join("E" if i[1] == "en" else "T" for i in items)
        n = pattern.count("E")
        if n >= 2 and pattern == "E" * n + "T" * n:
            blocks += 1
            for _, _, d in items:
                assert by_doc[(d.lang, d.news_id)].status is Status.CHECK
    assert blocks == 488  # research notes, Q6 correction


@pytest.mark.parametrize(
    "name",
    [
        "zai-lab-nddr",
        "form-8k-en-only",
        "a-plus-h-30d",
        "results-day",
        "tencent-30d",
        "annual-report-season",
        "listing-docs",
        "reused-code",
        "large-range",
    ],
)
def test_modern_matched_pairs_share_minute_and_category_and_follow_the_file_number(
    name: str, runs: dict[str, tuple[list[Document], list[Document], PairingResult]]
) -> None:
    gaps = Counter()
    for a in runs[name][2].announcements:
        if a.status is Status.MATCHED:
            assert a.en and a.tc and a.en.seq is not None and a.tc.seq is not None
            assert a.en.release_at == a.tc.release_at
            assert a.en.category_codes == a.tc.category_codes != ()
            gaps[a.tc.seq - a.en.seq] += 1
    assert gaps
    assert gaps[1] / sum(gaps.values()) >= 0.99, dict(gaps)
    assert set(gaps) <= {1, 2, 3}


def test_a_stubbed_english_document_is_never_paired_with_another_chinese_one(
    runs: dict[str, tuple[list[Document], list[Document], PairingResult]],
) -> None:
    result = runs["large-range"][2]
    stubbed = [a for a in result.announcements if a.stub]
    assert len(stubbed) == 790
    assert all(a.status is Status.EN_ONLY and a.tc is None for a in stubbed)


def test_the_result_does_not_depend_on_input_order(categories: CategoryIndex) -> None:
    english, chinese = load("delisted", categories)
    baseline = [(a.id, a.status) for a in pair_documents(english, chinese).announcements]
    rnd = random.Random(31)
    for _ in range(3):
        rnd.shuffle(english)
        rnd.shuffle(chinese)
        assert [
            (a.id, a.status) for a in pair_documents(english, chinese).announcements
        ] == baseline
