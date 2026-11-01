"""Title Case for all-caps English titles (SPEC §5, D-004). Pure: no I/O, no clock."""

import re

from app.config import NAMING, NamingConfig

_ROMAN = re.compile(r"^(?:XXX|X{0,2}(?:IX|IV|V?I{0,3}))$")  # I to XXX
_PARTS = re.compile(r"([-/&.,;:])")  # hyphenated and joined parts are cased one by one
_OPENERS = "(["


def upper_share(text: str) -> float:
    """Share of the ASCII letters that are upper case; 0.0 when there are none."""
    letters = [c for c in text if c.isascii() and c.isalpha()]
    return sum(c.isupper() for c in letters) / len(letters) if letters else 0.0


def is_mostly_upper(text: str, cfg: NamingConfig = NAMING) -> bool:
    return upper_share(text) >= cfg.upper_share_min


def _is_roman(word: str) -> bool:
    return bool(word) and bool(_ROMAN.match(word))


def _case_word(
    word: str, *, first: bool, before_shares: bool, allow_small: bool, cfg: NamingConfig
) -> str:
    upper = word.upper()
    if upper in cfg.acronyms or _is_roman(upper):
        return upper
    if before_shares and len(word) == 1:
        return upper  # H Shares, A Shares
    if allow_small and not first and word.lower() in cfg.lower_words:
        return word.lower()
    return word[0].upper() + word[1:].lower()


def _case_core(core: str, *, first: bool, before_shares: bool, cfg: NamingConfig) -> str:
    parts = _PARTS.split(core)
    if len(parts) == 1:
        return _case_word(core, first=first, before_shares=before_shares, allow_small=True, cfg=cfg)
    return "".join(
        part
        if i % 2 or not part
        else _case_word(part, first=False, before_shares=False, allow_small=False, cfg=cfg)
        for i, part in enumerate(parts)
    )


def _core_of(token: str) -> tuple[str, str, str] | None:
    """Leading punctuation, the part from the first to the last letter, trailing punctuation."""
    letters = [i for i, c in enumerate(token) if c.isalpha()]
    if not letters:
        return None
    return token[: letters[0]], token[letters[0] : letters[-1] + 1], token[letters[-1] + 1 :]


def to_title_case(text: str, cfg: NamingConfig = NAMING) -> str:
    """Re-case an all-caps English title; titles that are mixed-case are returned as published."""
    if cfg.title_case_mode != "title" or not is_mostly_upper(text, cfg):
        return text
    tokens = re.findall(r"\S+|\s+", text)
    words = [t for t in tokens if not t.isspace()]
    out: list[str] = []
    seen = 0
    first = True  # the first word, and the word after a " - " separator
    for token in tokens:
        if token.isspace():
            out.append(token)
            continue
        seen += 1
        pieces = None if any(c.isdigit() for c in token) else _core_of(token)
        if pieces is None:
            out.append(token)  # digits (8-K, Q3, FY2025) and punctuation stay as published
        else:
            lead, core, trail = pieces
            following = _core_of(words[seen]) if seen < len(words) else None
            before_shares = following is not None and following[1].lower() in {"share", "shares"}
            out.append(
                lead
                + _case_core(
                    core,
                    first=first or any(c in _OPENERS for c in lead),
                    before_shares=before_shares,
                    cfg=cfg,
                )
                + trail
            )
        first = token == "-"  # the " - " separator of SPEC §5
    return "".join(out)
