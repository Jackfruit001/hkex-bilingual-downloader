"""Raw servlet row -> `Document`. Pure and lenient about types, strict about identity."""

import html
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Any

from app.domain.models import Document, Flag, Lang
from app.domain.timeutil import parse_hkex_datetime

if TYPE_CHECKING:
    from app.hkex.reference import CategoryIndex

SOURCE_BASE = "https://www1.hkexnews.hk"

# Verified stub titles (research notes §5). Matched on lower-cased text with spaces collapsed.
_STUB_FRAGMENTS: dict[Lang, str] = {
    Lang.EN: "published by the issuer in the chinese section of this website",
    Lang.TC: "剛在本網站英文版面發布一項公告",
}


class RowError(ValueError):
    """A row that cannot be turned into a document; the caller counts it and moves on."""


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def clean_text(value: Any) -> str:
    """HTML-unescape, NFC, collapse all whitespace (including U+00A0 and U+3000)."""
    return " ".join(unicodedata.normalize("NFC", html.unescape(_text(value))).split())


def _split_multi(value: Any) -> list[str]:
    parts = re.split(r"<br\s*/?>", _text(value), flags=re.IGNORECASE)
    return [clean_text(p) for p in parts if clean_text(p)]


_PATH = re.compile(
    r"^/listedco/listconews/(?:sehk|gem)/(\d{4})/(\d{2})(\d{2})/(?:[^/]+/)*([^/]+)$", re.IGNORECASE
)
_STEM = re.compile(r"^(?:ltn)?\d{8}(\d+?)(?:_c)?$", re.IGNORECASE)


def parse_file_path(path: str) -> tuple[date | None, int | None]:
    """Folder date and running number from a file path; (None, None) for shapes without them."""
    m = _PATH.match(path)
    if not m:
        return None, None
    year, month, day, name = m.groups()
    try:
        folder = date(int(year), int(month), int(day))
    except ValueError:
        return None, None
    stem = name.rsplit(".", 1)[0]
    sm = _STEM.match(stem)
    return folder, int(sm.group(1)) if sm else None


def has_chinese_suffix(path: str) -> bool:
    """True when the file stem ends in `_c`, the marker of the Chinese section."""
    return bool(re.search(r"_c\.[A-Za-z0-9]+$", path))


@dataclass(frozen=True)
class ParsedCategory:
    prefix: str
    parent: str
    children: tuple[str, ...]


_PREFIX = re.compile(r"^\(((?:[^()\[\]]|\[[^\]]*\])*)\)\s*")
_PARENT_CHILDREN = re.compile(r"^(.*?) - \[(.*)\]$")


def parse_category_text(text: str) -> ParsedCategory:
    """`(Prefix) Parent - [A / B]` -> prefix, parent, children (text must already be unescaped).

    Raw HKEX text escapes every slash, so the only spaced slash is the category separator.
    """
    text = text.strip()
    prefix = ""
    m = _PREFIX.match(text)
    if m:
        prefix, text = m.group(1).strip(), text[m.end() :]
    pm = _PARENT_CHILDREN.match(text)
    if pm:
        return ParsedCategory(
            prefix, pm.group(1).strip(), tuple(c.strip() for c in pm.group(2).split(" / "))
        )
    return ParsedCategory(prefix, text, ())


def _flags(prefix: str, title: str) -> frozenset[Flag]:
    flags: set[Flag] = set()
    p = prefix.lower()
    if p.startswith("cancel") or "作廢" in p or p.startswith("取消"):
        flags.add(Flag.CANCELLED)
    elif (p.startswith("headline") and "revis" in p) or p.startswith("修改後標題"):
        flags.add(Flag.HEADLINES_REVISED)
    if title.lower().startswith("(revised)") or title.startswith("(經修訂)"):
        flags.add(Flag.REVISED)
    return frozenset(flags)


def _file_type(raw_type: str, path: str) -> str:
    kind = raw_type.strip().upper()
    if kind:
        return kind
    ext = path.rsplit(".", 1)[-1].upper() if "." in path.rsplit("/", 1)[-1] else ""
    return ext


def is_stub_title(title: str, lang: Lang) -> bool:
    return _STUB_FRAGMENTS[lang] in title.lower()


def parse_row(
    raw: Mapping[str, Any], lang: Lang, categories: "CategoryIndex | None" = None
) -> Document:
    path = _text(raw.get("FILE_LINK")).strip()
    news_id = _text(raw.get("NEWS_ID")).strip()
    when = _text(raw.get("DATE_TIME")).strip()
    for name, value in (("FILE_LINK", path), ("NEWS_ID", news_id), ("DATE_TIME", when)):
        if not value:
            raise RowError(f"Row has no {name}")
    try:
        release_at = parse_hkex_datetime(when)
    except ValueError as exc:
        raise RowError(f"Row has a bad DATE_TIME: {exc}") from exc

    title = clean_text(raw.get("TITLE"))
    category_text = clean_text(raw.get("LONG_TEXT"))
    parsed = parse_category_text(category_text)
    codes = categories.resolve(lang, parsed) if categories else ()
    folder_date, seq = parse_file_path(path)
    return Document(
        path=path,
        lang=lang,
        release_at=release_at,
        stock_codes=tuple(
            c.zfill(5) if c.isdigit() else c for c in _split_multi(raw.get("STOCK_CODE"))
        ),
        stock_names=tuple(_split_multi(raw.get("STOCK_NAME"))),
        title=title,
        category_text=category_text,
        category_prefix=parsed.prefix,
        category_codes=codes,
        file_type=_file_type(_text(raw.get("FILE_TYPE")), path),
        size_label=clean_text(raw.get("FILE_INFO")),
        folder_date=folder_date,
        seq=seq,
        is_stub=is_stub_title(title, lang),
        flags=_flags(parsed.prefix, title),
        news_id=news_id,
        source_url=SOURCE_BASE + path if path.startswith("/") else path,
    )
