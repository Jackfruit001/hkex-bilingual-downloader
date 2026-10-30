"""Settings and tunable constants. Environment variables override the defaults."""

import os
from dataclasses import dataclass
from datetime import date

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
    # Pre-2007 pairs need the exact relation to be matched (D-009), so the cautious reading wins.
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
    # D-009: neither document has categories (pre-2007); needs S1 and S3 as well
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
    content_timeout_s: float = 10.0


PAIRING = PairingConfig()
