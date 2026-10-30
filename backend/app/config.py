"""Settings and tunable constants. Environment variables override the defaults."""

import os
from dataclasses import dataclass

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
