"""Terminal output for the golden helper. Chinese characters are two columns wide."""

import unicodedata
from collections import Counter
from collections.abc import Mapping, Sequence

from app.config import PAIRING
from app.domain.models import Document
from app.domain.timeutil import HKT
from app.pairing.content_check import TextStatus
from app.pairing.models import Announcement, SingleReason
from tests.golden.draft import FileView, RowFiles
from tests.golden.schema import CaseType, Entry

ELLIPSIS = "…"
_COLUMN_GAP = " │ "


def _char_width(ch: str) -> int:
    if unicodedata.combining(ch):
        return 0
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1


def display_width(text: str) -> int:
    return sum(_char_width(ch) for ch in text)


def clip_to_width(text: str, width: int) -> str:
    """Cut `text` to at most `width` columns, ending in an ellipsis; never splits a character."""
    if width <= 0:
        return ""
    if display_width(text) <= width:
        return text
    budget = width - 1
    out = ""
    used = 0
    for ch in text:
        w = _char_width(ch)
        if used + w > budget:
            break
        out += ch
        used += w
    return out + ELLIPSIS


def _pad(text: str, width: int) -> str:
    clipped = clip_to_width(text, width)
    return clipped + " " * (width - display_width(clipped))


def side_by_side(left: Sequence[str], right: Sequence[str], width: int) -> list[str]:
    """Two columns of `width` columns each, shorter side padded, joined by a rule."""
    rows = max(len(left), len(right))
    return [
        _pad(left[i] if i < len(left) else "", width)
        + _COLUMN_GAP
        + _pad(right[i] if i < len(right) else "", width)
        for i in range(rows)
    ]


def figures_line(tokens: Counter[str], limit: int = 8) -> str:
    """The most common figures in a document's first pages, for comparing by eye."""
    if not tokens:
        return "no figures"
    ranked = sorted(tokens.items(), key=lambda item: (-item[1], item[0]))
    shown = "  ".join(f"{token}×{count}" for token, count in ranked[:limit])
    rest = len(ranked) - limit
    return f"{shown}  (+{rest} more)" if rest > 0 else shown


def _seq(doc: object) -> str:
    seq = getattr(doc, "seq", None)
    return "-" if seq is None else str(seq)


def announcement_table(
    announcements: Sequence[Announcement],
    tags: Mapping[str, Sequence[str]],
    width: int = 120,
) -> list[str]:
    """One numbered line per announcement, in the order given. The numbers are for `--pick`."""
    types = [",".join(tags.get(a.id, ())) for a in announcements]
    notes = [_notes(a) for a in announcements]
    type_w = min(max([len("types"), *map(len, types)]), 34)
    note_w = max([len("notes"), *map(len, notes)])
    fixed = f"{'#':>3} {'released':<16} {'status':<7} {'en':>5} {'tc':>5} "
    head = fixed + f"{'types':<{type_w}} {'notes':<{note_w}} title"
    lines = [head]
    room = max(width - len(fixed) - type_w - note_w - 2, 0)
    for n, (a, kind, note) in enumerate(zip(announcements, types, notes, strict=True), start=1):
        when = a.release_at.astimezone(HKT)
        title = (a.en or a.tc).title if (a.en or a.tc) else ""
        line = (
            f"{n:>3} {when:%Y-%m-%d %H:%M} {a.status.value:<7} "
            f"{_seq(a.en):>5} {_seq(a.tc):>5} "
            f"{clip_to_width(kind, type_w):<{type_w}} {note:<{note_w}} {clip_to_width(title, room)}"
        )
        lines.append(line.rstrip())
    return lines


def _notes(a: Announcement) -> str:
    parts = []
    if a.rivals:
        parts.append(f"rivals {len(a.rivals)}")
    if a.stub is not None:
        parts.append("stub")
    if a.separate:
        parts.append("separate")
    if a.bilingual:
        parts.append("bilingual")
    return ",".join(parts)


def _document_line(label: str, doc: Document, width: int) -> str:
    when = doc.release_at.astimezone(HKT)
    line = f"  {label}  {when:%Y-%m-%d %H:%M}  file {_seq(doc)}  news {doc.news_id}  {doc.title}"
    return clip_to_width(line, width)


def _absent_line(label: str, a: Announcement) -> str:
    if a.reason is SingleReason.STUB_IN_OTHER_SECTION:
        return f"  {label}  none: HKEXnews shows a notice instead (a stub), not a version"
    return f"  {label}  none: no document found in the range searched"


def _file_lines(label: str, view: FileView, width: int) -> list[str]:
    facts = view.facts
    lines = [f"  {label} pdf: {view.path}  ({facts.bytes:,} bytes, sha256 {facts.sha256[:8]})"]
    if view.text_status is not TextStatus.OK:
        why = f"{view.note}; " if view.note else ""
        lines.append(f"  {label} text {view.text_status.value}: {why}figures not compared")
    else:
        lines.append(clip_to_width(f"  figures {label}: {figures_line(view.tokens)}", width))
    return lines


def row_detail(
    n: int,
    a: Announcement,
    tags: Sequence[CaseType],
    eid: str,
    files: RowFiles | None,
    width: int = 120,
) -> list[str]:
    """Everything Zarif needs to confirm or correct one drafted entry, and the evidence against it."""
    score = f" (score {a.score})" if a.score is not None else ""
    out = [
        f"row {n} · {eid} · {a.status.value}{score}",
        f"  types: {', '.join(t.value for t in tags)}",
    ]
    for label, doc in (("EN", a.en), ("TC", a.tc)):
        out.append(_document_line(label, doc, width) if doc else _absent_line(label, a))
    out.extend(clip_to_width(f"  evidence: {line}", width) for line in a.evidence)
    if a.rivals:
        out.append("  rivals:")
        out.extend(
            clip_to_width(
                f"    {r.document.lang.value.upper()} file {_seq(r.document)} "
                f"news {r.document.news_id} (score {r.score})  {r.document.title}",
                width,
            )
            for r in a.rivals
        )
    out.extend(
        f"  source {label}: {doc.source_url}" for label, doc in (("EN", a.en), ("TC", a.tc)) if doc
    )
    if a.stub is not None:
        out.append(f"  notice: {a.stub.source_url}")
    if files is None:
        out.append("  no PDFs fetched (use --pick or --sample)")
        return out
    for label, view in (("EN", files.en), ("TC", files.tc)):
        if view:
            out.extend(_file_lines(label, view, width))
    if files.en and files.tc:
        same = files.en.facts.sha256 == files.tc.facts.sha256
        out.append(
            "  bytes: IDENTICAL, one bilingual file published in both sections"
            if same
            else "  bytes: different files"
        )
    if files.containment is not None and files.en and files.tc:
        compared = min(files.en.tokens.total(), files.tc.tokens.total())
        out.append(
            f"  figures in common: {round(files.containment * 100)}% of the figures in the "
            f"smaller set ({compared} figures compared)"
        )
        if compared < PAIRING.content_min_tokens:
            out.append("  warning: too few figures to rely on; compare the documents by eye")
    out.extend(f"  skipped: {reason}" for reason in files.skipped)
    if (files.en and files.en.lines) or (files.tc and files.tc.lines):
        column = max((width - 5) // 2, 10)
        left = ["English, first lines", *(files.en.lines if files.en else ())]
        right = ["Chinese, first lines", *(files.tc.lines if files.tc else ())]
        out.extend("  " + line for line in side_by_side(left, right, column))
    return out


def entry_table(entries: Sequence[Entry], width: int = 120) -> list[str]:
    """One line per golden entry, in file order: a way to walk through them for verification."""
    types = [",".join(t.value for t in e.case_types) for e in entries]
    id_w = max([len("id"), *(len(e.id) for e in entries)])
    type_w = min(max([len("types"), *map(len, types)]), 34)
    fixed = f"{'verified':<8} {'id':<{id_w}} {'proposed':<8} {'types':<{type_w}} title"
    lines = [fixed]
    room = max(width - (8 + 1 + id_w + 1 + 8 + 1 + type_w + 1), 0)
    for e, kind in zip(entries, types, strict=True):
        doc = e.truth.en or e.truth.tc
        title = doc.title if doc else ""
        line = (
            f"{'yes' if e.verified else 'no':<8} {e.id:<{id_w}} {e.proposal.status:<8} "
            f"{clip_to_width(kind, type_w):<{type_w}} {clip_to_width(title, room)}"
        )
        lines.append(line.rstrip())
    return lines
