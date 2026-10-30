"""The golden entry schema (SPEC §10.4): what Zarif verifies, and what the golden test reads."""

from typing import Any

import pytest
from pydantic import ValidationError

from tests.golden.schema import (
    REQUIRED_CASE_TYPES,
    CaseType,
    DocRef,
    Entry,
    Proposal,
    Truth,
    entry_id,
)


def ref(news_id: str, lang: str = "en") -> DocRef:
    return DocRef(
        news_id=news_id,
        path=f"/listedco/listconews/sehk/2026/1028/2026102801739{'_c' if lang == 'tc' else ''}.pdf",
        title="Test" if lang == "en" else "測試",
        released="2026-10-28 22:52",
    )


def entry(truth: Truth, **overrides: Any) -> Entry:
    fields: dict[str, Any] = {
        "id": "x",
        "stock_code": "09688",
        "stock_id": 1000057951,
        "stock_name": "ZAI LAB",
        "scenario": "09688-20261028-20261028",
        "case_types": [CaseType.ORDINARY],
        "truth": truth,
        "proposal": Proposal(status="matched", score=14, evidence=["same minute"]),
    }
    return Entry(**(fields | overrides))


def test_the_required_case_types_are_the_twelve_in_spec_10_4() -> None:
    assert len(REQUIRED_CASE_TYPES) == 12
    assert set(REQUIRED_CASE_TYPES) <= set(CaseType)
    assert CaseType.BLOCK_LAYOUT not in REQUIRED_CASE_TYPES
    assert CaseType.SINGLE_NOT_FOUND not in REQUIRED_CASE_TYPES


def test_a_new_entry_is_unverified() -> None:
    assert entry(Truth(en=ref("1"), tc=ref("2", "tc"))).verified is False


def test_a_pair_is_valid_without_an_absent_reason() -> None:
    truth = Truth(en=ref("1"), tc=ref("2", "tc"))
    assert truth.absent is None


def test_a_pair_with_an_absent_reason_is_rejected() -> None:
    with pytest.raises(ValidationError, match="both versions"):
        Truth(en=ref("1"), tc=ref("2", "tc"), absent="stub")


@pytest.mark.parametrize("present", ["en", "tc"])
def test_a_single_language_entry_needs_a_reason(present: str) -> None:
    with pytest.raises(ValidationError, match="reason"):
        Truth(**{present: ref("1", present)})


@pytest.mark.parametrize("reason", ["stub", "not_found"])
def test_a_single_language_entry_with_a_reason_is_valid(reason: str) -> None:
    assert Truth(en=ref("1"), absent=reason).tc is None  # type: ignore[arg-type]


def test_an_entry_with_no_document_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Truth(absent="stub")


def test_an_unknown_reason_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Truth(en=ref("1"), absent="lost")  # type: ignore[arg-type]


def test_a_misspelt_field_is_an_error_not_a_silent_unverified_entry() -> None:
    with pytest.raises(ValidationError, match="verifed"):
        entry(Truth(en=ref("1"), tc=ref("2", "tc")), verifed=True)


def test_an_unknown_case_type_is_rejected() -> None:
    with pytest.raises(ValidationError):
        entry(Truth(en=ref("1"), tc=ref("2", "tc")), case_types=["ordinary", "weird"])


def test_the_entry_needs_at_least_one_case_type() -> None:
    with pytest.raises(ValidationError):
        entry(Truth(en=ref("1"), tc=ref("2", "tc")), case_types=[])


def test_the_id_of_a_pair_uses_the_english_news_id() -> None:
    assert entry_id("09688", Truth(en=ref("111"), tc=ref("112", "tc"))) == "09688-111"


def test_the_id_of_an_english_only_entry_uses_the_english_news_id() -> None:
    assert entry_id("09688", Truth(en=ref("111"), absent="stub")) == "09688-111"


def test_the_id_of_a_chinese_only_entry_says_so() -> None:
    assert entry_id("00939", Truth(tc=ref("222", "tc"), absent="stub")) == "00939-tc-222"


def test_the_stock_code_keeps_its_leading_zeros_as_text() -> None:
    assert entry(Truth(en=ref("1"), tc=ref("2", "tc"))).stock_code == "09688"
    with pytest.raises(ValidationError):
        entry(Truth(en=ref("1"), tc=ref("2", "tc")), stock_code="9688")
