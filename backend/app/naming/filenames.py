"""Filenames, ZIP names and the download header (SPEC §5). Pure: no I/O, no clock.

`{LANG}_{YYYY-MM-DD}-{CODE}-{TITLE}.pdf`, where the date is the document's own Hong Kong date and
the title comes from that document's language. Everything a client can influence ends up in
`slugify` or `sanitize_given_name`, so a name that leaves this module is safe on Windows, macOS
and Linux.
"""

import re
import unicodedata
from collections.abc import Iterable
from datetime import date, datetime
from urllib.parse import quote

from pathvalidate import sanitize_filename

from app.config import NAMING, NamingConfig
from app.domain.models import Document, Lang
from app.domain.timeutil import HKT
from app.hkex.parse import clean_text
from app.naming.titlecase import to_title_case

_FORBIDDEN = frozenset('<>:"/\\|?*')
_STRIP = "-._ "
_CODE = re.compile(r"[0-9]{5}")
_LANG_TAG = {Lang.EN: "EN", Lang.TC: "TC"}
_PDF = ".pdf"


def _check_code(code: str) -> None:
    if not _CODE.fullmatch(code):
        raise ValueError(f"Not a 5-digit stock code: {code!r}")


def _hkt_date(published: datetime) -> date:
    if published.tzinfo is None:
        raise ValueError("The publication time needs a time zone")
    return published.astimezone(HKT).date()


def slugify(title: str) -> str:
    """Unescape, NFC, forbidden and control characters to spaces, words joined by hyphens."""
    text = "".join(
        " " if c in _FORBIDDEN or unicodedata.category(c) == "Cc" else c for c in clean_text(title)
    )
    return re.sub(r"-{2,}", "-", "-".join(text.split())).strip(_STRIP)


def _fit(slug: str, prefix: str, suffix: str, extension: str, cfg: NamingConfig) -> str:
    """Cut the title to the limits: at the last hyphen that fits, else at a character boundary."""
    slug = slug or cfg.untitled
    chars = len(prefix) + len(suffix) + len(extension)
    size = len((prefix + suffix + extension).encode())
    cut = 0  # the longest prefix of the slug that fits
    for ch in slug:
        chars += 1
        size += len(ch.encode())
        if chars > cfg.max_filename_chars or size > cfg.max_filename_bytes:
            break
        cut += 1
    if cut >= len(slug):
        return slug
    hyphen = slug.rfind("-", 1, cut + 1)
    body = slug[: hyphen if hyphen > 0 else cut].rstrip(_STRIP)
    return body or cfg.untitled


def _safe(name: str) -> str:
    """The last check: valid on every platform pathvalidate knows (a no-op for our own names)."""
    return sanitize_filename(name, platform="universal")


def build_filename(
    lang: Lang,
    published: datetime,
    code: str,
    title: str,
    *,
    suffix: str = "",
    cfg: NamingConfig = NAMING,
) -> str:
    _check_code(code)
    text = clean_text(title)
    if lang is Lang.EN:
        text = to_title_case(text, cfg)
    prefix = f"{_LANG_TAG[lang]}_{_hkt_date(published).isoformat()}-{code}-"
    body = _fit(slugify(text), prefix, suffix, _PDF, cfg)
    return _safe(f"{prefix}{body}{suffix}{_PDF}")


def filename_for(doc: Document, code: str, cfg: NamingConfig = NAMING) -> str:
    return build_filename(doc.lang, doc.release_at, code, doc.title, cfg=cfg)


def _publication_order(doc: Document) -> tuple[datetime, int, str]:
    return doc.release_at, doc.seq if doc.seq is not None else 10**12, doc.path


def name_documents(
    docs: Iterable[Document], code: str, cfg: NamingConfig = NAMING
) -> dict[str, str]:
    """A distinct filename for every downloadable document, keyed by its path.

    Pass every document of the stock for the days concerned, whatever the filters: a document
    must get the same name whatever is shown. When two different files would get the same name,
    the later ones in publication order (release time, then file number) get `-(2)`, `-(3)`.
    Stubs and entries that are not `.pdf` files are never downloaded and take no number. A file
    listed twice (a cancelled entry and its replacement) is one document.
    """
    _check_code(code)
    unique: dict[str, Document] = {}
    for doc in sorted(docs, key=_publication_order):
        if not doc.is_stub and doc.path.lower().endswith(_PDF):
            unique.setdefault(doc.path, doc)
    names: dict[str, str] = {}
    taken: set[str] = set()
    for doc in unique.values():
        name, number = filename_for(doc, code, cfg), 1
        while name in taken:
            number += 1
            name = build_filename(
                doc.lang, doc.release_at, code, doc.title, suffix=f"-({number})", cfg=cfg
            )
        taken.add(name)
        names[doc.path] = name
    return names


def sanitize_given_name(name: str, cfg: NamingConfig = NAMING) -> tuple[str, bool]:
    """A filename sent back by a client, made safe; the flag says whether anything changed."""
    stem = name[: -len(_PDF)] if name.lower().endswith(_PDF) else name
    clean = _safe(_fit(slugify(stem), "", "", _PDF, cfg) + _PDF)
    return clean, clean != name


def pair_zip_name(
    published: datetime, code: str, title: str, *, english: bool = True, cfg: NamingConfig = NAMING
) -> str:
    """`EN-TC_{date}-{code}-{title}.zip`, from the English title (the Chinese one if missing)."""
    _check_code(code)
    text = clean_text(title)
    if english:
        text = to_title_case(text, cfg)
    prefix = f"EN-TC_{_hkt_date(published).isoformat()}-{code}-"
    return _safe(f"{prefix}{_fit(slugify(text), prefix, '', '.zip', cfg)}.zip")


def bulk_zip_name(code: str, start: date, end: date) -> str:
    _check_code(code)
    return f"HKEX_{code}_{start.isoformat()}_to_{end.isoformat()}.zip"


def content_disposition(filename: str) -> str:
    """`attachment` with an ASCII fallback and the real name percent-encoded (RFC 6266)."""
    fallback = "".join(
        c if c.isascii() and c.isprintable() and c not in '"\\' else "_" for c in filename
    )
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(filename, safe='')}"
