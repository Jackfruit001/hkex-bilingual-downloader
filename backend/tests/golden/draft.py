"""The golden helper's pipeline (Phase 2.4): search, pair, tag, choose rows, fetch, draft entries.

`scripts/golden_helper.py` only parses arguments and prints; everything testable is here. The
draft entry's `truth` is the matcher's pairing written down as a claim; whether it is true is
for a person with both PDFs open to say (see `schema`).
"""

import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from app.config import PAIRING, PairingConfig
from app.domain.models import Document, Lang, Stock
from app.domain.timeutil import HKT
from app.hkex.reference import CategoryIndex
from app.hkex.search import SearchOutput, search_both
from app.pairing.content_check import (
    TextStatus,
    containment,
    extract_text_async,
    fingerprint,
    readable,
)
from app.pairing.matcher import document_format, pair_documents
from app.pairing.models import (
    Announcement,
    ContentEvidence,
    Format,
    PairingResult,
    SingleReason,
    Status,
)
from tests.golden.fetch import (
    FileTooLarge,
    GoldenClient,
    RecordedCall,
    size_label_bytes,
    write_call,
)
from tests.golden.quiet import quiet_worker
from tests.golden.schema import CaseType, DocRef, Entry, Proposal, Truth, entry_id
from tests.golden.store import FileFacts
from tests.golden.tagging import Candidate, stratified_sample, tag_announcements

PREVIEW_LINES = 8
_FORMAT_NAME = {
    Format.WEB_PAGE: "a web page",
    Format.MULTI_FILE: "a multi-file document",
    Format.OTHER: "a non-PDF file",
}


@dataclass(frozen=True)
class Scenario:
    name: str
    code: str
    stock_id: int
    start: date
    end: date

    @classmethod
    def for_stock(cls, stock: Stock, start: date, end: date) -> "Scenario":
        return cls(
            f"{stock.code}-{start:%Y%m%d}-{end:%Y%m%d}", stock.code, stock.stock_id, start, end
        )


@dataclass(frozen=True)
class Drafted:
    scenario: Scenario
    stock: Stock
    search: SearchOutput
    result: PairingResult
    tags: dict[str, tuple[CaseType, ...]]

    @property
    def rows(self) -> list[Announcement]:
        """The announcements in table order (newest first); row numbers are positions + 1."""
        return list(self.result.announcements)


def pair_and_tag(
    search: SearchOutput,
    stock: Stock,
    scenario: Scenario,
    content: ContentEvidence | None = None,
) -> Drafted:
    result = pair_documents(
        search.english, search.chinese, content=content, searched=(scenario.start, scenario.end)
    )
    tags = tag_announcements(result.announcements, stock_active=stock.active)
    return Drafted(scenario, stock, search, result, tags)


async def search_and_pair(
    client: GoldenClient, stock: Stock, categories: CategoryIndex, scenario: Scenario
) -> Drafted:
    search = await search_both(client, stock, scenario.start, scenario.end, categories)
    return pair_and_tag(search, stock, scenario)


# --- entries ----------------------------------------------------------------------------------


def _ref(doc: Document) -> DocRef:
    return DocRef(
        news_id=doc.news_id,
        path=doc.path,
        title=doc.title,
        released=f"{doc.release_at.astimezone(HKT):%Y-%m-%d %H:%M}",
    )


def _truth(a: Announcement) -> Truth:
    absent = None
    if a.status in (Status.EN_ONLY, Status.TC_ONLY):
        absent = "stub" if a.reason is SingleReason.STUB_IN_OTHER_SECTION else "not_found"
    return Truth(en=_ref(a.en) if a.en else None, tc=_ref(a.tc) if a.tc else None, absent=absent)


def to_entry(drafted: Drafted, a: Announcement) -> Entry:
    truth = _truth(a)
    stock = drafted.stock
    return Entry(
        id=entry_id(stock.code, truth),
        stock_code=stock.code,
        stock_id=stock.stock_id,
        stock_name=stock.name_en,
        scenario=drafted.scenario.name,
        case_types=list(drafted.tags[a.id]),
        truth=truth,
        proposal=Proposal(status=a.status.value, score=a.score, evidence=list(a.evidence)),
    )


def find_row(drafted: Drafted, entry: Entry) -> int:
    """The 1-based table row holding an entry's documents: by the English document, else the Chinese."""
    en_id = entry.truth.en.news_id if entry.truth.en else None
    tc_id = entry.truth.tc.news_id if entry.truth.tc else None
    rows = drafted.rows
    for n, a in enumerate(rows, start=1):
        if en_id and a.en and a.en.news_id == en_id:
            return n
    for n, a in enumerate(rows, start=1):
        if tc_id and a.tc and a.tc.news_id == tc_id:
            return n
    raise LookupError(f"{entry.id} is not in the {drafted.scenario.name} table")


def counterpart(final: Drafted, original: Announcement) -> Announcement:
    """The same announcement after pairing again (its id can change if the pairing did)."""
    for a in final.rows:
        if original.en and a.en and a.en.news_id == original.en.news_id:
            return a
    for a in final.rows:
        if original.tc and a.tc and a.tc.news_id == original.tc.news_id:
            return a
    raise RuntimeError(f"announcement {original.id} disappeared when pairing again")


def choose_rows(
    drafted: Drafted, *, pick: Sequence[int], sample: int, seed: int, taken: set[str]
) -> list[int]:
    """Row numbers to draft: the ones named, or a stratified sample, never an existing entry."""
    if pick and sample:
        raise ValueError("Use either --pick or --sample, not both.")
    rows = drafted.rows
    if pick:
        for n in pick:
            if not 1 <= n <= len(rows):
                raise ValueError(f"row {n} is not in the table (rows 1 to {len(rows)})")
        return sorted(set(pick))
    if sample <= 0:
        return []
    by_id: dict[str, int] = {}
    candidates = []
    for n, a in enumerate(rows, start=1):
        eid = entry_id(drafted.stock.code, _truth(a))
        if eid in taken:
            continue
        by_id[eid] = n
        tags = drafted.tags[a.id]
        strata = frozenset({*(t.value for t in tags), f"status:{a.status.value}"})
        busy = CaseType.SEVERAL_SAME_DAY in tags or CaseType.SEVERAL_SAME_MINUTE in tags
        candidates.append(Candidate(eid, strata, busy))
    return sorted(by_id[eid] for eid in stratified_sample(candidates, sample, seed))


# --- files ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class FileView:
    lang: Lang
    news_id: str
    path: Path
    facts: FileFacts
    text_status: TextStatus
    lines: tuple[str, ...]
    tokens: Counter[str]
    note: str = ""  # why the text is not usable, when it is not


@dataclass(frozen=True)
class RowFiles:
    en: FileView | None
    tc: FileView | None
    containment: float | None
    skipped: list[str]

    def facts_by_key(self) -> dict[str, FileFacts]:
        return {f"{v.lang.value}:{v.news_id}": v.facts for v in (self.en, self.tc) if v is not None}


def _cache_name(doc: Document) -> str:
    code = doc.stock_codes[0] if doc.stock_codes else "-"
    return f"{doc.lang.value.upper()}_{doc.release_at.astimezone(HKT):%Y-%m-%d}_{code}_{doc.news_id}.pdf"


async def _view(
    client: GoldenClient,
    doc: Document,
    max_bytes: int,
    skipped: list[str],
    cfg: PairingConfig,
) -> FileView | None:
    label = f"{doc.lang.value.upper()} {doc.news_id}"
    fmt = document_format(doc)
    if fmt is not Format.PDF:
        skipped.append(f"{label}: {_FORMAT_NAME[fmt]}, not fetched")
        return None
    size = size_label_bytes(doc.size_label)
    if size is not None and size > max_bytes:
        skipped.append(f"{label}: listed as {doc.size_label}, over the {max_bytes >> 20} MB limit")
        return None
    name = _cache_name(doc)
    try:
        data = await client.get_pdf(doc.source_url, name)
    except FileTooLarge:
        skipped.append(f"{label}: over the {max_bytes >> 20} MB limit")
        return None
    extracted = readable(
        doc.lang, await extract_text_async(data, target=quiet_worker, cfg=cfg), cfg
    )
    status, note = extracted.status, extracted.detail
    tokens = fingerprint(extracted.text) if status is TextStatus.OK else Counter()
    lines = (
        ()
        if note
        else tuple(ln.strip() for ln in extracted.text.splitlines() if ln.strip())[:PREVIEW_LINES]
    )
    facts = FileFacts(sha256=hashlib.sha256(data).hexdigest(), bytes=len(data), tokens=dict(tokens))
    return FileView(
        doc.lang, doc.news_id, client.pdf_path(name), facts, status, lines, tokens, note
    )


async def fetch_row_files(
    client: GoldenClient,
    a: Announcement,
    *,
    max_bytes: int,
    cfg: PairingConfig = PAIRING,
) -> RowFiles:
    """Fetch and read the PDFs of one announcement. Stubs are notices, not versions: never fetched."""
    skipped: list[str] = []
    en = await _view(client, a.en, max_bytes, skipped, cfg) if a.en else None
    tc = await _view(client, a.tc, max_bytes, skipped, cfg) if a.tc else None
    score = containment(en.tokens, tc.tokens) if en and tc and en.tokens and tc.tokens else None
    return RowFiles(en, tc, score, skipped)


def sha256_by_document(facts: Mapping[str, FileFacts]) -> dict[tuple[Lang, str], str]:
    """The bytes hashes the matcher takes (SPEC S5), from facts keyed `<lang>:<news_id>`."""
    return {
        (Lang(key.split(":", 1)[0]), key.split(":", 1)[1]): value.sha256
        for key, value in facts.items()
    }


def repair_with_hashes(drafted: Drafted, facts: Mapping[str, FileFacts]) -> Drafted:
    """Pair again knowing which fetched files are byte for byte identical (SPEC S5)."""
    return pair_and_tag(
        drafted.search,
        drafted.stock,
        drafted.scenario,
        ContentEvidence(sha256=sha256_by_document(facts)),
    )


# --- fixtures ---------------------------------------------------------------------------------


def _meta(s: Scenario) -> dict[str, object]:
    return {
        "name": s.name,
        "code": s.code,
        "stock_id": s.stock_id,
        "from": s.start.isoformat(),
        "to": s.end.isoformat(),
    }


def load_scenario(folder: Path) -> Scenario:
    meta = json.loads((folder / "scenario.json").read_text(encoding="utf-8"))
    return Scenario(
        meta["name"],
        meta["code"],
        meta["stock_id"],
        date.fromisoformat(meta["from"]),
        date.fromisoformat(meta["to"]),
    )


def save_fixtures(client: GoldenClient, drafted: Drafted, root: Path) -> Path:
    """Keep the search responses this run used, so the golden test replays them offline.

    Use one client per scenario: every call it answered is recorded.
    """
    folder = root / drafted.scenario.name
    meta_file = folder / "scenario.json"
    meta = _meta(drafted.scenario)
    if meta_file.exists() and json.loads(meta_file.read_text(encoding="utf-8")) != meta:
        raise ValueError(f"{folder.name} already holds a different scenario")
    folder.mkdir(parents=True, exist_ok=True)
    meta_file.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    seen: dict[str, RecordedCall] = {}
    for call in client.calls:
        seen.setdefault(call.key, call)
    for call in seen.values():
        write_call(folder / "calls", call)
    return folder
