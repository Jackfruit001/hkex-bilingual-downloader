"""Reading and appending golden entries, and the file facts kept beside them.

Appending only ever adds text at the end. An entry that is already in the file is skipped, so
Zarif's edits and comments are never rewritten.
"""

import json
from collections.abc import Iterable, Mapping
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from tests.golden.schema import Entry

GOLDEN_DIR = Path(__file__).parent
PAIRS = GOLDEN_DIR / "pairs.yaml"
FACTS = GOLDEN_DIR / "fingerprints.json"

HEADER = """\
# Golden pairing set (SPEC section 10.4). Drafted by scripts/golden_helper.py, verified by Zarif.
#
# Each entry is a claim to confirm. `truth` says which English and Chinese documents belong
# together (or that one side is missing and why). Open both PDFs; check the stock code, the dates
# and the figures. If the claim is right set `verified: true`; if it is wrong, correct `truth`
# first (news ids matter, path and title are for reading). `proposal` is only what the matcher
# said when the entry was drafted. It is not evidence and the golden test ignores it.
#
# Never edit `id`. Run `uv run --project backend python scripts/golden_helper.py coverage` to see
# what is still missing.
"""


class _Dumper(yaml.SafeDumper):
    """Quotes digit-only text, so a stock code like 00700 is never read back as a number."""


def _represent_str(dumper: yaml.SafeDumper, value: str) -> yaml.ScalarNode:
    style = "'" if value.isdigit() else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=style)


_Dumper.add_representer(str, _represent_str)


def load_entries(path: Path = PAIRS) -> list[Entry]:
    if not path.exists():
        return []
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError(f"{path.name} must hold a list of entries")
    entries = [Entry.model_validate(item) for item in raw]
    seen: set[str] = set()
    for e in entries:
        if e.id in seen:
            raise ValueError(f"{path.name} has two entries with the id {e.id}")
        seen.add(e.id)
    return entries


def append_entries(path: Path, entries: Iterable[Entry]) -> list[str]:
    """Add the entries whose ids are not in the file yet; return the ids added."""
    have = {e.id for e in load_entries(path)}
    new: list[Entry] = []
    for entry in entries:
        if entry.id not in have:
            have.add(entry.id)
            new.append(entry)
    if not new:
        return []
    body = yaml.dump(
        [e.model_dump(mode="json") for e in new],
        Dumper=_Dumper,
        sort_keys=False,
        allow_unicode=True,
        width=120,
    )
    text = path.read_text(encoding="utf-8") if path.exists() else HEADER
    if text and not text.endswith("\n"):
        text += "\n"
    path.write_text(text + body, encoding="utf-8")
    return [e.id for e in new]


# --- file facts -------------------------------------------------------------------------------


class FileFacts(BaseModel):
    """What the golden test may know about a PDF without the PDF: bytes hash and figures."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bytes: int
    tokens: dict[str, int]  # the content-check fingerprint of the first pages


def load_facts(path: Path = FACTS) -> dict[str, FileFacts]:
    """Facts keyed `<lang>:<news_id>`."""
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {key: FileFacts.model_validate(value) for key, value in raw.items()}


def merge_facts(path: Path, new: Mapping[str, FileFacts]) -> None:
    """Add facts; keep the rest. A document whose bytes changed is an error, not an update."""
    facts = load_facts(path)
    for key, value in new.items():
        if key in facts and facts[key].sha256 != value.sha256:
            raise ValueError(f"{key} is already recorded with different bytes")
        facts[key] = value
    lines = [
        f"{json.dumps(key)}:"
        + json.dumps(
            facts[key].model_dump(), sort_keys=True, ensure_ascii=False, separators=(",", ":")
        )
        for key in sorted(facts)
    ]
    body = ",\n".join(lines)
    path.write_text("{\n" + body + "\n}\n" if lines else "{}\n", encoding="utf-8")
