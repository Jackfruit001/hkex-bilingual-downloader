"""Reading and appending golden entries without disturbing what Zarif has edited."""

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from tests.golden.schema import CaseType, DocRef, Entry, Proposal, Truth
from tests.golden.store import (
    FileFacts,
    append_entries,
    load_entries,
    load_facts,
    merge_facts,
)


def make_entry(news_id: str, **overrides: object) -> Entry:
    en = DocRef(
        news_id=news_id, path="/a/1.pdf", title="Results: 中期業績", released="2026-10-28 22:52"
    )
    tc = DocRef(
        news_id=str(int(news_id) + 1),
        path="/a/2_c.pdf",
        title="業績公告",
        released="2026-10-28 22:52",
    )
    fields: dict[str, object] = {
        "id": f"09688-{news_id}",
        "stock_code": "09688",
        "stock_id": 1000057951,
        "stock_name": "ZAI LAB",
        "scenario": "s",
        "case_types": [CaseType.ORDINARY],
        "truth": Truth(en=en, tc=tc),
        "proposal": Proposal(
            status="matched", score=14, evidence=["Published together at 22:52 HKT."]
        ),
    }
    return Entry(**(fields | overrides))  # type: ignore[arg-type]


def test_appending_to_a_missing_file_creates_it_with_a_guide_and_the_entries(
    tmp_path: Path,
) -> None:
    path = tmp_path / "pairs.yaml"
    added = append_entries(path, [make_entry("100"), make_entry("200")])
    assert added == ["09688-100", "09688-200"]
    assert path.read_text(encoding="utf-8").startswith("#")
    assert [e.id for e in load_entries(path)] == ["09688-100", "09688-200"]


def test_entries_survive_a_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "pairs.yaml"
    original = make_entry("100", notes="check the figures")
    append_entries(path, [original])
    assert load_entries(path) == [original]


def test_chinese_text_is_written_as_text_not_escapes(tmp_path: Path) -> None:
    path = tmp_path / "pairs.yaml"
    append_entries(path, [make_entry("100")])
    assert "業績公告" in path.read_text(encoding="utf-8")


def test_digit_only_text_is_quoted_so_no_yaml_reader_turns_a_code_into_a_number(
    tmp_path: Path,
) -> None:
    path = tmp_path / "pairs.yaml"
    append_entries(path, [make_entry("100", stock_code="09688", id="09688-100")])
    text = path.read_text(encoding="utf-8")
    assert "stock_code: '09688'" in text
    assert "news_id: '100'" in text


def test_existing_text_is_never_rewritten(tmp_path: Path) -> None:
    path = tmp_path / "pairs.yaml"
    append_entries(path, [make_entry("100")])
    edited = path.read_text(encoding="utf-8").replace(
        "verified: false", "verified: true  # opened both"
    )
    edited += "# a comment Zarif added\n"
    path.write_text(edited, encoding="utf-8")

    append_entries(path, [make_entry("200")])

    after = path.read_text(encoding="utf-8")
    assert after.startswith(edited)
    first, second = load_entries(path)
    assert first.verified is True and second.verified is False


def test_a_file_without_a_final_newline_is_still_appended_to_safely(tmp_path: Path) -> None:
    path = tmp_path / "pairs.yaml"
    append_entries(path, [make_entry("100")])
    path.write_text(path.read_text(encoding="utf-8").rstrip("\n"), encoding="utf-8")
    append_entries(path, [make_entry("200")])
    assert [e.id for e in load_entries(path)] == ["09688-100", "09688-200"]


def test_an_entry_that_already_exists_is_skipped_and_left_as_edited(tmp_path: Path) -> None:
    path = tmp_path / "pairs.yaml"
    append_entries(path, [make_entry("100", notes="Zarif's note")])
    before = path.read_text(encoding="utf-8")
    added = append_entries(path, [make_entry("100"), make_entry("200")])
    assert added == ["09688-200"]
    assert path.read_text(encoding="utf-8").startswith(before)
    assert load_entries(path)[0].notes == "Zarif's note"


def test_appending_nothing_leaves_the_file_alone(tmp_path: Path) -> None:
    path = tmp_path / "pairs.yaml"
    assert append_entries(path, []) == []
    assert not path.exists()


def test_the_same_entry_twice_in_one_call_is_added_once(tmp_path: Path) -> None:
    path = tmp_path / "pairs.yaml"
    assert append_entries(path, [make_entry("100"), make_entry("100")]) == ["09688-100"]


def test_a_missing_file_loads_as_no_entries(tmp_path: Path) -> None:
    assert load_entries(tmp_path / "none.yaml") == []


def test_an_empty_file_loads_as_no_entries(tmp_path: Path) -> None:
    path = tmp_path / "pairs.yaml"
    path.write_text("# only a comment\n", encoding="utf-8")
    assert load_entries(path) == []


def test_duplicate_ids_in_the_file_are_an_error(tmp_path: Path) -> None:
    path = tmp_path / "pairs.yaml"
    entry = make_entry("100").model_dump(mode="json")
    path.write_text(yaml.safe_dump([entry, entry], allow_unicode=True), encoding="utf-8")
    with pytest.raises(ValueError, match="09688-100"):
        load_entries(path)


def test_a_bad_entry_in_the_file_is_an_error(tmp_path: Path) -> None:
    path = tmp_path / "pairs.yaml"
    entry = make_entry("100").model_dump(mode="json")
    entry["verifed"] = True
    path.write_text(yaml.safe_dump([entry]), encoding="utf-8")
    with pytest.raises(ValidationError):
        load_entries(path)


def test_a_file_that_is_not_a_list_is_an_error(tmp_path: Path) -> None:
    path = tmp_path / "pairs.yaml"
    path.write_text("a: 1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="list"):
        load_entries(path)


# --- file facts sidecar ---------------------------------------------------------------------


def facts(sha: str = "a" * 64, tokens: dict[str, int] | None = None) -> FileFacts:
    return FileFacts(sha256=sha, bytes=1234, tokens=tokens or {"2026": 3, "28": 1})


def test_facts_are_written_sorted_one_file_per_line(tmp_path: Path) -> None:
    path = tmp_path / "facts.json"
    merge_facts(path, {"tc:2": facts(), "en:1": facts("b" * 64)})
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "{" and lines[-1] == "}"
    assert lines[1].startswith('"en:1"') and lines[2].startswith('"tc:2"')
    assert load_facts(path) == {"en:1": facts("b" * 64), "tc:2": facts()}


def test_merging_keeps_existing_facts(tmp_path: Path) -> None:
    path = tmp_path / "facts.json"
    merge_facts(path, {"en:1": facts()})
    merge_facts(path, {"tc:2": facts("c" * 64)})
    assert set(load_facts(path)) == {"en:1", "tc:2"}


def test_the_same_facts_merged_again_change_nothing(tmp_path: Path) -> None:
    path = tmp_path / "facts.json"
    merge_facts(path, {"en:1": facts()})
    before = path.read_bytes()
    merge_facts(path, {"en:1": facts()})
    assert path.read_bytes() == before


def test_different_bytes_for_the_same_document_are_an_error(tmp_path: Path) -> None:
    path = tmp_path / "facts.json"
    merge_facts(path, {"en:1": facts()})
    with pytest.raises(ValueError, match="en:1"):
        merge_facts(path, {"en:1": facts("d" * 64)})


def test_missing_facts_load_as_empty(tmp_path: Path) -> None:
    assert load_facts(tmp_path / "none.json") == {}


def test_a_sha256_must_look_like_one() -> None:
    with pytest.raises(ValidationError):
        FileFacts(sha256="nothex", bytes=1, tokens={})
