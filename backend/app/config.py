"""Settings and tunable constants. Environment variables override the defaults."""

import os
from dataclasses import dataclass
from datetime import date
from typing import Literal

REPO_URL = "https://github.com/Jackfruit001/hkex-bilingual-downloader"
VERSION = "0.1.0"


@dataclass(frozen=True)
class Settings:
    user_agent: str = f"hkex-bilingual-downloader/{VERSION} (+{REPO_URL})"
    connect_timeout_s: float = 10.0
    read_timeout_s: float = 30.0
    timezone: str = "Asia/Hong_Kong"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(user_agent=os.environ.get("HKEX_USER_AGENT", cls.user_agent))


settings = Settings.from_env()


@dataclass(frozen=True)
class PairingConfig:
    """Pairing weights and thresholds (SPEC §4.2 and §4.3). Tune on the golden set only."""

    # S1, release time
    same_minute: int = 3
    within_minutes: int = 5
    near_minutes_points: int = 1
    # S2, headline categories
    categories_identical: int = 3
    categories_overlap: int = 1
    categories_disjoint: int = -4
    # S3, file numbers (same date folder)
    file_exact: int = 4  # TC = EN + 1, or the same number with `_c` added (2005)
    file_near: int = 2
    file_near_window: int = 3
    # Folders before this date are assumed to use "same number plus _c" numbering unless the
    # data says otherwise (research notes Q6: seen in 2005, not in 2014 to 2015; cut-over Open).
    # Pre-2007 pairs are never matched on structure (D-009 fallback), so the cautious reading wins.
    same_number_before: date = date(2007, 6, 25)
    # S4, NEWS_ID of the TC document is the EN one plus 1 (weak)
    news_id_next: int = 1
    # S6, long numbers in titles
    title_numbers_agree: int = 1
    title_numbers_conflict: int = -2
    title_number_min_digits: int = 3
    # candidates and classification
    candidate_window: int = 5  # file numbers either side
    check_min_score: int = 4
    match_min_score: int = 9
    # D-009: a category text exists but no code resolves (a retired category); needs S1 and S3 too
    match_min_score_no_category: int = 7
    margin: int = 3
    exhaustive_max_side: int = 8
    # separate submissions (SPEC §4.4)
    separate_days: int = 14
    separate_min_score: int = 3
    separate_codes: frozenset[str] = frozenset({"40100"})  # Annual Report
    separate_code_prefixes: tuple[str, ...] = ("3",)  # tier one 30000, Listing Documents
    # content check (SPEC §4.5)
    content_conclusive_score: float = 0.6
    content_conclusive_gap: float = 0.2
    content_min_tokens: int = 5
    content_pages: int = 3
    content_min_chars: int = 200  # fewer means a scanned document
    # Share of Chinese characters a Chinese PDF's text needs to be trusted. 21 of 62 real files had
    # at most 2.8% (undecodable embedded font) and 41 had at least 14.5% (research notes §9).
    content_min_chinese_share: float = 0.08
    content_timeout_s: float = 10.0


PAIRING = PairingConfig()

TitleCaseMode = Literal["title", "as_published"]


@dataclass(frozen=True)
class NamingConfig:
    """Filename rules (SPEC §5)."""

    # "title" re-cases all-caps English titles; "as_published" keeps the HKEX casing (D-004).
    title_case_mode: TitleCaseMode = "title"
    # Title Case only runs when at least this share of the ASCII letters is upper case.
    upper_share_min: float = 0.7
    # Kept upper case. The SPEC list, plus those seen in all-caps recorded titles (HSBC, CKH, CK,
    # GSK, CNY, AUD, MREL) and four more currency codes of the HKD, RMB and USD kind.
    acronyms: frozenset[str] = frozenset(
        {
            "AGM", "EGM", "SGM", "ESG", "CEO", "CFO", "INED", "PRC", "HK", "HKD", "RMB", "USD",
            "US", "UK", "EU", "SEC", "SFC", "CSRC", "HKEX", "SEHK", "GEM", "IPO", "ADS", "ADR",
            "ETF", "REIT", "CBBC", "RSU", "ESOP", "PLC", "LLC", "NV", "SA", "AG",
            "HSBC", "CKH", "CK", "GSK", "CNY", "AUD", "MREL", "EUR", "GBP", "JPY", "SGD",
        }
    )  # fmt: skip
    # Lower case unless first, after an opening bracket, or after a " - " separator.
    lower_words: frozenset[str] = frozenset(
        {
            "a", "an", "the", "and", "but", "or", "nor", "as", "at", "by", "for", "from", "in",
            "into", "of", "off", "on", "onto", "per", "to", "up", "upon", "via", "vs", "with",
        }
    )  # fmt: skip
    # The whole filename, prefix and extension included (fits Windows, macOS and download paths).
    max_filename_bytes: int = 180
    max_filename_chars: int = 120
    untitled: str = "Untitled"


NAMING = NamingConfig()
