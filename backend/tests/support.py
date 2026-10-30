"""A fake titleSearchServlet that behaves as verified in Phase 0 (research notes §9)."""

import json
from datetime import date, datetime, timedelta
from typing import Any

import httpx

from app.domain.models import Document, Flag, Lang
from app.domain.timeutil import HKT


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


# --- pairing -------------------------------------------------------------------------------

STUB_TITLES = {
    Lang.EN: "The issuer has published an announcement in the Chinese section of this website",
    Lang.TC: "發行人剛在本網站英文版面發布一項公告，相應中文版本或會／或不會在本版面發布。",
}


def make_doc(
    lang: Lang,
    seq: int | None,
    when: datetime,
    *,
    news_id: int | None = None,
    categories: tuple[str, ...] = ("50200",),
    title: str | None = None,
    stub: bool = False,
    flags: frozenset[Flag] = frozenset(),
    c_suffix: bool = False,
    old_style: bool = False,
    ext: str = "pdf",
    file_type: str = "PDF",
    size_label: str = "84KB",
    code: str = "09688",
) -> Document:
    """A normalised document for pairing tests. `seq=None` makes a shared-page path (dod)."""
    when = when.replace(tzinfo=HKT) if when.tzinfo is None else when
    folder = f"/listedco/listconews/sehk/{when:%Y/%m%d}"
    if seq is None:
        path = f"/listedco/listconews/sehk/dod/{lang.value if lang is Lang.EN else 'tc'}.html"
        folder_date = None
    else:
        stem = f"ltn{when:%Y%m%d}{seq:03d}" if old_style else f"{when:%Y%m%d}{seq:05d}"
        path = f"{folder}/{stem}{'_c' if c_suffix else ''}.{ext}"
        folder_date = when.date()
    default_title = STUB_TITLES[lang] if stub else ("測試公告" if lang is Lang.TC else "Test")
    return Document(
        path=path,
        lang=lang,
        release_at=when,
        stock_codes=(code,),
        stock_names=("ZAI LAB",),
        title=title or default_title,
        category_text="",
        category_codes=categories,
        file_type=file_type,
        size_label=size_label,
        folder_date=folder_date,
        seq=seq,
        is_stub=stub,
        flags=flags,
        news_id=str(news_id if news_id is not None else (seq or 0)),
        source_url=f"https://www1.hkexnews.hk{path}",
    )


def make_pdf(pages: list[list[str]]) -> bytes:
    """A minimal valid PDF with Helvetica text, one list of lines per page (no dependencies)."""
    objects: list[bytes] = [b"<< /Type /Catalog /Pages 2 0 R >>"]
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(len(pages)))
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode())
    font = 3 + 2 * len(pages)
    for i, lines in enumerate(pages):
        content_id = 4 + 2 * i
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Contents {content_id} 0 R /Resources << /Font << /F1 {font} 0 R >> >> >>"
            ).encode()
        )
        body = (
            "BT /F1 12 Tf 14 TL 50 740 Td "
            + " ".join(
                f"({line.replace(chr(92), chr(92) * 2).replace('(', chr(92) + '(').replace(')', chr(92) + ')')}) Tj T*"
                for line in lines
            )
            + " ET"
        )
        objects.append(f"<< /Length {len(body)} >>\nstream\n{body}\nendstream".encode())
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return bytes(out)
