"""A fake titleSearchServlet that behaves as verified in Phase 0 (research notes §9)."""

import json
from datetime import date, datetime, timedelta
from typing import Any

import httpx


def make_row(
    news_id: int,
    when: datetime,
    *,
    seq: int | None = None,
    chinese: bool = False,
    code: str = "09688",
    title: str | None = None,
    category: str | None = None,
) -> dict[str, Any]:
    """A servlet row in the verified shape. `seq` defaults to the news id."""
    number = seq if seq is not None else news_id
    stem = f"{when:%Y%m%d}{number:05d}" + ("_c" if chinese else "")
    return {
        "FILE_INFO": "84KB",
        "NEWS_ID": str(news_id),
        "SHORT_TEXT": "",
        "TOTAL_COUNT": "0",
        "DOD_WEB_PATH": "",
        "STOCK_NAME": "ZAI LAB",
        "TITLE": title or ("測試公告" if chinese else "Test announcement"),
        "FILE_TYPE": "PDF",
        "DATE_TIME": f"{when:%d/%m/%Y %H:%M}",
        "LONG_TEXT": category if category is not None else "",
        "STOCK_CODE": code,
        "FILE_LINK": f"/listedco/listconews/sehk/{when:%Y/%m%d}/{stem}.pdf",
    }


def spread_rows(
    count: int, first_day: date, days: int, *, chinese: bool = False, start_id: int = 1
) -> list[dict[str, Any]]:
    """`count` rows spread evenly over `days` days starting at `first_day`, newest id last."""
    rows = []
    for i in range(count):
        day = first_day + timedelta(days=i * days // count)
        when = datetime(day.year, day.month, day.day, 9, i % 60)
        rows.append(make_row(start_id + i, when, chinese=chinese))
    return rows


class FakeServlet:
    """Serves rows for `lang=EN` / `lang=ZH`, newest first, cumulative `rowRange`."""

    def __init__(
        self,
        english: list[dict[str, Any]],
        chinese: list[dict[str, Any]],
        *,
        echo: dict[str, str] | None = None,
        ignore_row_range: bool = False,
    ) -> None:
        self.rows = {"EN": english, "ZH": chinese}
        self.echo = echo or {"EN": "E", "ZH": "C"}
        self.ignore_row_range = ignore_row_range
        self.requests: list[dict[str, str]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        self.requests.append(params)
        lang = params["lang"]
        lo = datetime.strptime(params["fromDate"], "%Y%m%d").date()
        hi = datetime.strptime(params["toDate"], "%Y%m%d").date()
        wanted = [
            r
            for r in self.rows[lang]
            if lo <= datetime.strptime(r["DATE_TIME"][:10], "%d/%m/%Y").date() <= hi
        ]
        wanted.sort(
            key=lambda r: (datetime.strptime(r["DATE_TIME"], "%d/%m/%Y %H:%M"), r["NEWS_ID"]),
            reverse=True,
        )
        n = int(params["rowRange"])
        served = wanted[:100] if self.ignore_row_range else wanted[:n]
        body = {
            "result": json.dumps(served) if served else "null",
            "hasNextRow": len(served) < len(wanted),
            "sortList": "[[0,0]]",
            "rowRange": n,
            "lang": self.echo[lang],
            "loadedRecord": len(served),
            "recordCnt": len(wanted),
        }
        return httpx.Response(200, json=body)

    def asked_for(self, lang: str) -> list[dict[str, str]]:
        return [p for p in self.requests if p["lang"] == lang]
