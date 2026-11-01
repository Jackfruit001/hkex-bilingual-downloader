"""`HKEX_MODE=fixtures`: serve recorded HKEXnews responses so the app runs without the network.

Used by the browser tests and for demos. Search results are every row recorded under
`tests/fixtures/raw` for a stock, filtered by the dates asked for; every PDF is a blank page.
"""

import io
import json
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

import httpx
from pypdf import PdfWriter

RAW = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "raw"


def _placeholder_pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def _recorded_rows() -> dict[tuple[int, str], dict[str, dict[str, Any]]]:
    """Every recorded row per (stock, section), merged over all recordings, by NEWS_ID."""
    found: dict[tuple[int, str], dict[str, dict[str, Any]]] = {}
    for params_file in sorted(RAW.glob("*/*.params.json")):
        params = json.loads(params_file.read_text("utf-8"))["params"]
        section = "ZH" if str(params["lang"]).upper() in {"ZH", "C", "TC"} else "EN"
        body = json.loads(
            params_file.with_name(params_file.name.replace(".params", "")).read_text("utf-8")
        )
        result = body.get("result")
        for row in json.loads(result) if isinstance(result, str) else (result or []):
            found.setdefault((int(params["stockId"]), section), {})[str(row["NEWS_ID"])] = row
    return found


def _yyyymmdd(date_time: str) -> str:
    day, month, year = date_time.split(" ")[0].split("/")
    return f"{year}{month}{day}"


def fixture_transport() -> httpx.MockTransport:
    rows = _recorded_rows()
    pdf = _placeholder_pdf()

    def handle(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("titleSearchServlet.do"):
            query = {k: v[0] for k, v in parse_qs(request.url.query.decode()).items()}
            section = "ZH" if query["lang"] == "ZH" else "EN"
            wanted = [
                row
                for row in rows.get((int(query["stockId"]), section), {}).values()
                if query["fromDate"] <= _yyyymmdd(row["DATE_TIME"]) <= query["toDate"]
            ]
            wanted.sort(key=lambda r: (_yyyymmdd(r["DATE_TIME"]), r["DATE_TIME"]), reverse=True)
            shown = wanted[: int(query["rowRange"])]
            return httpx.Response(
                200,
                json={
                    "result": json.dumps(shown),
                    "recordCnt": len(wanted),
                    "loadedRecord": len(shown),
                    "hasNextRow": len(shown) < len(wanted),
                    "rowRange": int(query["rowRange"]),
                    "lang": "C" if section == "ZH" else "E",
                },
            )
        if "/ncms/script/eds/" in path:
            file = RAW / "reference" / path.rsplit("/", 1)[-1]
            return httpx.Response(200, content=file.read_bytes())
        if path.endswith(".pdf"):
            return httpx.Response(200, content=pdf, headers={"content-length": str(len(pdf))})
        return httpx.Response(404)

    return httpx.MockTransport(handle)
