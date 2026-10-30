"""Content check (SPEC §4.5): compare the figures in an English PDF with a Chinese one.

Pure functions plus one process boundary. pypdf has no timeout and a crafted or broken PDF can
make it spin, so text extraction runs in a short-lived worker process that is killed at the
time limit. No network: the caller supplies the verified PDF bytes.
"""

import asyncio
import multiprocessing
import multiprocessing.connection as mpc
import re
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from io import BytesIO

from pypdf import PdfReader

from app.config import PAIRING, PairingConfig
from app.domain.models import Lang
from app.pairing.models import ContentVerdict

_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?%?")
# Full-width digits, percent sign and full stop (U+FF10 to U+FF19, U+FF05, U+FF0E) read as ASCII.
_FULL_WIDTH = {0xFF10 + i: str(i) for i in range(10)} | {0xFF05: "%", 0xFF0E: "."}
_MONTH_NAMES = (
    "january february march april may june july august september october november december"
)
_MONTHS = {name: str(number) for number, name in enumerate(_MONTH_NAMES.split(), start=1)}
_MONTH = re.compile(r"\b(" + "|".join(_MONTHS) + r"|oct|nov|dec)\b\.?", re.IGNORECASE)
_ABBREVIATIONS = {"oct": "10", "nov": "11", "dec": "12"}


def fingerprint(text: str) -> Counter[str]:
    """The figures in a text: numbers with commas removed, single digits dropped.

    English month names add their number, so "28 October 2026" holds 28, 10 and 2026 and
    compares with "2026年10月28日".
    """
    folded = text.translate(_FULL_WIDTH)
    found = [t.replace(",", "") for t in _NUMBER.findall(folded)]
    for match in _MONTH.finditer(folded):
        word = match.group(1).lower()
        found.append(_MONTHS.get(word) or _ABBREVIATIONS[word])
    return Counter(t for t in found if sum(c.isdigit() for c in t) >= 2)


def containment(en: Counter[str], tc: Counter[str]) -> float:
    """Shared figures as a share of the smaller fingerprint (multiset containment)."""
    smaller = min(en.total(), tc.total())
    return (en & tc).total() / smaller if smaller else 0.0


def best_match(
    en_news_id: str,
    en: Counter[str],
    candidates: Mapping[str, Counter[str]],
    cfg: PairingConfig = PAIRING,
) -> ContentVerdict | None:
    """Score one English document against its candidate Chinese ones (by `NEWS_ID`).

    Conclusive only if the best score is high, clearly ahead of the second best, and the
    English fingerprint has enough figures to mean anything (SPEC §4.5 step 5).
    """
    if not candidates:
        return None
    ranked = sorted(
        ((containment(en, fp), news_id) for news_id, fp in candidates.items()),
        key=lambda item: (-item[0], item[1]),
    )
    best, tc_news_id = ranked[0]
    second = ranked[1][0] if len(ranked) > 1 else 0.0
    tokens = en.total()
    conclusive = (
        best >= cfg.content_conclusive_score
        and best - second >= cfg.content_conclusive_gap
        and tokens >= cfg.content_min_tokens
    )
    return ContentVerdict(en_news_id, tc_news_id, best, second, tokens, conclusive)


# --- text extraction in a worker process ---------------------------------------------------------


class TextStatus(StrEnum):
    OK = "ok"
    UNAVAILABLE = "unavailable"  # almost no text: a scanned document
    TIMEOUT = "timeout"
    ERROR = "error"


@dataclass(frozen=True)
class ExtractedText:
    status: TextStatus
    text: str = ""
    detail: str = ""


_CHINESE = re.compile(r"[㐀-䶿一-鿿豈-﫿]")


def chinese_share(text: str) -> float:
    """Share of the non-space characters that are Chinese."""
    chars = "".join(text.split())
    return len(_CHINESE.findall(chars)) / len(chars) if chars else 0.0


def readable(lang: Lang, extracted: ExtractedText, cfg: PairingConfig = PAIRING) -> ExtractedText:
    """Text that can be compared, or `UNAVAILABLE` with the reason.

    Many Chinese PDFs embed a font pypdf cannot decode: the extracted "text" is long enough to
    pass the length test but is gibberish with a few stray digits, so its figures say nothing.
    A Chinese document with almost no Chinese characters in its text is therefore unavailable.
    """
    if extracted.status is not TextStatus.OK or lang is not Lang.TC:
        return extracted
    share = chinese_share(extracted.text)
    if share < cfg.content_min_chinese_share:
        return ExtractedText(
            TextStatus.UNAVAILABLE,
            extracted.text,
            f"only {share:.1%} of the characters are Chinese; the PDF's text can't be decoded",
        )
    return extracted


def _extract(pdf: bytes, pages: int) -> str:
    reader = PdfReader(BytesIO(pdf))
    return "\n".join((page.extract_text() or "") for page in reader.pages[:pages])


def _worker(conn: mpc.Connection, pdf: bytes, pages: int) -> None:
    try:
        conn.send(("ok", _extract(pdf, pages)))
    except Exception as exc:  # pypdf raises many types for broken files; none may escape
        conn.send(("error", type(exc).__name__))
    finally:
        conn.close()


def extract_text(
    pdf: bytes,
    *,
    cfg: PairingConfig = PAIRING,
    pages: int | None = None,
    timeout_s: float | None = None,
    target: Callable[[mpc.Connection, bytes, int], None] = _worker,
) -> ExtractedText:
    """Text from the first pages of a PDF, within a time limit (SPEC §4.5 step 2)."""
    limit = cfg.content_timeout_s if timeout_s is None else timeout_s
    ctx = multiprocessing.get_context("spawn")  # same behaviour on Linux, macOS and Windows
    receiver, sender = ctx.Pipe(duplex=False)
    process = ctx.Process(
        target=target, args=(sender, pdf, pages or cfg.content_pages), daemon=True
    )
    process.start()
    sender.close()
    try:
        if not receiver.poll(limit):
            return ExtractedText(TextStatus.TIMEOUT, detail=f"no answer in {limit:g} s")
        try:
            kind, payload = receiver.recv()
        except EOFError:
            return ExtractedText(TextStatus.ERROR, detail="the extraction worker stopped")
    finally:
        receiver.close()
        if process.is_alive():
            process.terminate()
        process.join(2)
    if kind != "ok":
        return ExtractedText(TextStatus.ERROR, detail=str(payload))
    if len(str(payload).strip()) < cfg.content_min_chars:
        return ExtractedText(TextStatus.UNAVAILABLE, text=str(payload))
    return ExtractedText(TextStatus.OK, text=str(payload))


async def extract_text_async(pdf: bytes, **kwargs: object) -> ExtractedText:
    """`extract_text` without blocking the event loop."""
    return await asyncio.to_thread(extract_text, pdf, **kwargs)  # type: ignore[arg-type]
