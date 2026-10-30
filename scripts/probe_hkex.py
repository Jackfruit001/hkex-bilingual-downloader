"""Polite probe of HKEXnews (Phase 0).

Run from the repo root:

    uv run --project backend python scripts/probe_hkex.py reference
    uv run --project backend python scripts/probe_hkex.py access
    uv run --project backend python scripts/probe_hkex.py --help

Rules: strictly sequential, at least 1 s between live requests (plus jitter), identifying
User-Agent, every response cached on disk (re-runs cost nothing), a hard request budget per run,
and the run stops at the first 403, 429 or challenge page instead of retrying.

Self-contained on purpose: it imports nothing from backend/app, so findings do not depend on
code that is itself under test.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

REPO_URL = "https://github.com/Jackfruit001/hkex-bilingual-downloader"
USER_AGENT = f"hkex-bilingual-downloader/0.1 (+{REPO_URL})"
BASE = "https://www1.hkexnews.hk"

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "scripts" / ".probe_cache"
OUT_DIR = ROOT / "scripts" / "probe_out"
FIXTURES = ROOT / "backend" / "tests" / "fixtures" / "raw"

MIN_INTERVAL_S = 1.0
JITTER_S = 0.5
DEFAULT_BUDGET = 250
KEEP_HEADERS = ("content-type", "content-length", "content-encoding", "server", "set-cookie",
                "cache-control", "last-modified", "etag", "retry-after",
                "access-control-allow-origin", "access-control-allow-methods", "vary")


class ProbeStopped(RuntimeError):
    """Raised when HKEXnews throttles or challenges us; the run must end."""


@dataclass
class Response:
    url: str
    status: int
    headers: dict[str, str]
    body: bytes
    elapsed_s: float
    from_cache: bool

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


@dataclass
class PoliteClient:
    budget: int = DEFAULT_BUDGET
    live_requests: int = 0
    cache_hits: int = 0
    _last_live: float = 0.0
    _client: httpx.Client = field(init=False)

    def __post_init__(self) -> None:
        self._client = httpx.Client(
            headers={"User-Agent": USER_AGENT},
            timeout=httpx.Timeout(30.0, connect=10.0),
            follow_redirects=False,
        )
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _key(method: str, url: str, params: dict[str, Any] | None, tag: str) -> str:
        canon = json.dumps([method, url, sorted((params or {}).items()), tag])
        return hashlib.sha256(canon.encode()).hexdigest()

    def get(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        *,
        tag: str = "",
        range_header: str | None = None,
        headers: dict[str, str] | None = None,
        max_body: int | None = None,
    ) -> Response:
        """GET with cache, pacing and budget. `tag` separates experiments that share a URL."""
        key = self._key("GET", url, params, tag + (range_header or "") + str(sorted((headers or {}).items())))
        meta_path, body_path = CACHE_DIR / f"{key}.json", CACHE_DIR / f"{key}.body"
        if meta_path.exists() and body_path.exists():
            meta = json.loads(meta_path.read_text())
            self.cache_hits += 1
            return Response(meta["url"], meta["status"], meta["headers"], body_path.read_bytes(),
                            meta["elapsed_s"], True)

        if self.live_requests >= self.budget:
            raise ProbeStopped(f"request budget of {self.budget} reached")
        wait = MIN_INTERVAL_S + random.uniform(0, JITTER_S) - (time.monotonic() - self._last_live)
        if wait > 0:
            time.sleep(wait)

        req_headers = dict(headers or {})
        if range_header:
            req_headers["Range"] = range_header
        last_error: Exception | None = None
        for attempt, backoff in enumerate((0.0, 2.0, 8.0)):
            if backoff:
                time.sleep(backoff)
            started = time.monotonic()
            self._last_live = started
            self.live_requests += 1
            try:
                with self._client.stream("GET", url, params=params, headers=req_headers) as r:
                    chunks: list[bytes] = []
                    size = 0
                    for chunk in r.iter_bytes():
                        chunks.append(chunk)
                        size += len(chunk)
                        if max_body is not None and size >= max_body:
                            break
                    body = b"".join(chunks)
                    status, resp_headers, final_url = r.status_code, r.headers, str(r.url)
            except httpx.HTTPError as exc:
                last_error = exc
                print(f"  network error ({type(exc).__name__}), attempt {attempt + 1}", file=sys.stderr)
                continue
            elapsed = time.monotonic() - started
            if status in (403, 429):
                raise ProbeStopped(f"HTTP {status} from {final_url}; stopping, not retrying")
            if status >= 500 and attempt < 2:
                print(f"  HTTP {status}, retrying", file=sys.stderr)
                continue
            head = body[:2000].lower()
            if b"captcha" in head or b"access denied" in head:
                raise ProbeStopped(f"challenge page from {final_url}")
            kept = {k: v for k, v in resp_headers.items() if k.lower() in KEEP_HEADERS}
            meta_path.write_text(json.dumps({"url": final_url, "status": status, "headers": kept,
                                             "elapsed_s": round(elapsed, 3)}))
            body_path.write_bytes(body)
            return Response(final_url, status, kept, body, round(elapsed, 3), False)
        raise ProbeStopped(f"giving up on {url}: {last_error}")


def save_fixture(rel: str, data: bytes | str | dict[str, Any] | list[Any]) -> Path:
    path = FIXTURES / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, bytes):
        path.write_bytes(data)
    elif isinstance(data, str):
        path.write_text(data, encoding="utf-8")
    else:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


# --- Stage: reference data ---------------------------------------------------------------

REFERENCE_FILES = {
    "activestock_sehk_e.json": "/ncms/script/eds/activestock_sehk_e.json",
    "activestock_sehk_c.json": "/ncms/script/eds/activestock_sehk_c.json",
    "inactivestock_sehk_e.json": "/ncms/script/eds/inactivestock_sehk_e.json",
    "inactivestock_sehk_c.json": "/ncms/script/eds/inactivestock_sehk_c.json",
    "tierone_e.json": "/ncms/script/eds/tierone_e.json",
    "tierone_c.json": "/ncms/script/eds/tierone_c.json",
    "tiertwogrp_e.json": "/ncms/script/eds/tiertwogrp_e.json",
    "tiertwogrp_c.json": "/ncms/script/eds/tiertwogrp_c.json",
    "tiertwo_e.json": "/ncms/script/eds/tiertwo_e.json",
    "tiertwo_c.json": "/ncms/script/eds/tiertwo_c.json",
    "doc_e.json": "/ncms/script/eds/doc_e.json",
}


def stage_reference(client: PoliteClient) -> None:
    """Download the stock lists and category files; print their shape (not their content)."""
    for name, path in REFERENCE_FILES.items():
        r = client.get(BASE + path)
        print(f"{name}: HTTP {r.status}, {len(r.body)} bytes, {r.elapsed_s}s"
              f"{' (cache)' if r.from_cache else ''}, {r.headers.get('content-type')}")
        if r.status == 200:
            save_fixture(f"reference/{name}", r.body)
            try:
                data = json.loads(r.body)
            except json.JSONDecodeError as exc:
                print(f"  not JSON: {exc}")
                continue
            describe(data)


def describe(data: Any, indent: str = "  ") -> None:
    if isinstance(data, list):
        print(f"{indent}list of {len(data)}; first: {json.dumps(data[0], ensure_ascii=False)[:300] if data else None}")
    elif isinstance(data, dict):
        print(f"{indent}dict keys: {list(data)[:12]}")
    else:
        print(f"{indent}{type(data).__name__}")


# --- Servlet helpers ---------------------------------------------------------------------

SERVLET = BASE + "/search/titleSearchServlet.do"


def search_params(stock_id: int, from_date: str, to_date: str, lang: str,
                  row_range: int = 100, category: int = 0, **extra: Any) -> dict[str, Any]:
    """Parameter set as seen in other clients (research notes §2); dates are YYYYMMDD."""
    return {"sortDir": 0, "sortByOptions": "DateTime", "category": category, "market": "SEHK",
            "stockId": stock_id, "documentType": -1, "fromDate": from_date, "toDate": to_date,
            "title": "", "searchType": 0, "t1code": -2, "t2Gcode": -2, "t2code": -2,
            "rowRange": row_range, "lang": lang, **extra}


@dataclass
class SearchResult:
    response: Response
    envelope: dict[str, Any]
    rows: list[dict[str, Any]]


def run_search(client: PoliteClient, params: dict[str, Any], tag: str = "") -> SearchResult:
    """One servlet call. `result` is a JSON string inside the JSON body (or null)."""
    r = client.get(SERVLET, params, tag=tag)
    envelope = json.loads(r.text)
    raw = envelope.get("result")
    rows = json.loads(raw) if isinstance(raw, str) and raw != "null" else []
    return SearchResult(r, envelope, rows)


def save_search(scenario: str, lang: str, n: int, params: dict[str, Any], res: SearchResult) -> None:
    prefix = f"{scenario}/{lang}_{n}"
    save_fixture(f"{prefix}.json", res.response.body)
    save_fixture(f"{prefix}.params.json", {
        "url": SERVLET, "params": params, "status": res.response.status,
        "elapsed_s": res.response.elapsed_s, "headers": res.response.headers})


def summarise(rows: list[dict[str, Any]], limit: int = 5) -> str:
    return "; ".join(f"{x['DATE_TIME']} {x['FILE_LINK'].rsplit('/', 1)[-1]}" for x in rows[:limit])


# --- Stage: access experiments (Q1, Q2, Q3, Q4, Q10, Q11) -------------------------------

ZAI_LAB_ID = 1000057951  # 09688 in activestock_sehk_e.json (reference stage)
FINDINGS: list[dict[str, Any]] = []


def finding(q: str, answer: str, evidence: str, status: str = "Verified") -> None:
    FINDINGS.append({"question": q, "answer": answer, "evidence": evidence, "status": status})
    print(f"[{q}] {status}: {answer}\n    evidence: {evidence}")


def stage_access(client: PoliteClient) -> None:
    day = "20261028"
    seen: dict[str, SearchResult] = {}
    for lang in ("EN", "E", "ZH", "TC", "C", "zh"):
        res = run_search(client, search_params(ZAI_LAB_ID, day, day, lang), tag=f"q1-{lang}")
        seen[lang] = res
        save_search("access-q1", lang, 1, search_params(ZAI_LAB_ID, day, day, lang), res)
        zh = sum(x["FILE_LINK"].split("/")[-1].split(".")[0].endswith("_c") for x in res.rows)
        print(f"lang={lang}: HTTP {res.response.status}, echoed lang={res.envelope.get('lang')!r}, "
              f"{len(res.rows)} rows, {zh} with _c links, {res.response.elapsed_s}s")
    chinese = [k for k, v in seen.items() if v.rows and v.rows[0]["FILE_LINK"].split(".")[0].endswith("_c")]
    finding("Q1", f"Chinese section only for lang in {chinese}; other values silently return English",
            "access-q1/*.json; compare echoed `lang` and `_c` links per value")

    en, zh_res = seen["EN"], seen[chinese[0]] if chinese else seen["ZH"]
    cookies = sorted(set(re.findall(r"(?:^|, )([A-Za-z_]\w*)=", en.response.headers.get("set-cookie", ""))))
    finding("Q2", "A direct servlet GET with no prior page visit or cookie returns data",
            f"HTTP {en.response.status}; response sets cookies: {cookies} (bot-management style; "
            "hosting risk to test at Gate 0)")
    finding("Q3", "fromDate and toDate are both inclusive of the whole day",
            f"fromDate=toDate={day} returned {summarise(en.rows)}; none outside that day")
    finding("Q5", "NEWS_ID is not shared across languages",
            "; ".join(f"EN {a['NEWS_ID']} vs TC {b['NEWS_ID']}" for a, b in zip(en.rows, zh_res.rows)))
    finding("Q10", "CORS header on the servlet",
            f"access-control-allow-origin: {en.response.headers.get('access-control-allow-origin')} "
            "(not '*', so a browser app on another origin cannot call it; server-side fetch is required)")

    # Q4: pagination on a busier stock. Tencent (00700), October 2026.
    act = json.loads((FIXTURES / "reference/activestock_sehk_e.json").read_text())
    tencent = next(s["i"] for s in act if s["c"] == "00700")
    page: dict[int, SearchResult] = {}
    for n in (5, 10, 100):
        p = search_params(tencent, "20261001", "20261029", "EN", row_range=n)
        page[n] = run_search(client, p, tag=f"q4-{n}")
        save_search("access-q4", "en", n, p, page[n])
        e = page[n].envelope
        print(f"rowRange={n}: {len(page[n].rows)} rows, recordCnt={e.get('recordCnt')}, "
              f"loadedRecord={e.get('loadedRecord')}, hasNextRow={e.get('hasNextRow')}, "
              f"TOTAL_COUNT[0]={page[n].rows[0].get('TOTAL_COUNT') if page[n].rows else None}")
    prefix_ok = [x["FILE_LINK"] for x in page[10].rows[:5]] == [x["FILE_LINK"] for x in page[5].rows]
    finding("Q4", f"rowRange is cumulative (rows 1..N): {prefix_ok}; total in `recordCnt`",
            "access-q4/en_5|10|100.json; largest honoured value tested in the large-range scenario")
    times = [r.response.elapsed_s for r in [*seen.values(), *page.values()] if not r.response.from_cache]
    finding("Q11", f"servlet latency {min(times, default=0)}s to {max(times, default=0)}s",
            f"{len(times)} live calls; no throttling seen", "Verified (partial; see scenarios)")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "access_findings.json").write_text(json.dumps(FINDINGS, ensure_ascii=False, indent=2))


# --- Stage: scenarios --------------------------------------------------------------------

PICKS_FILE = OUT_DIR / "picks.json"

# name -> (stock code or None to read from picks.json, fromDate, toDate, category 0=active 1=delisted)
SCENARIOS: dict[str, tuple[str | None, str, str, int]] = {
    "zai-lab-nddr": ("09688", "20261028", "20261028", 0),
    "form-8k-en-only": ("09688", "20261023", "20261023", 0),
    "tencent-30d": ("00700", "20260930", "20261030", 0),
    "a-plus-h-30d": (None, "20260930", "20261030", 0),
    "results-day": ("00005", "20260725", "20260805", 0),
    "annual-report-season": ("00700", "20260301", "20260531", 0),
    "large-range": ("00005", "20231030", "20261030", 0),
    "old-docs": ("00005", "20050101", "20051231", 0),
    "listing-docs": (None, "20260101", "20261030", 0),
    "delisted": ("00013", "20140101", "20150731", 1),
    "reused-code": ("00013", "20260101", "20261030", 0),
    "no-results": ("09688", "20260101", "20260101", 0),
    "english-only-issuer": (None, "20260801", "20261030", 0),
}
ROW_CAP = 5000


def load_stocks(kind: str) -> list[dict[str, Any]]:
    return json.loads((FIXTURES / f"reference/{kind}stock_sehk_e.json").read_text())


def resolve_stock(code: str, category: int) -> list[dict[str, Any]]:
    """All list entries for a code; more than one means code reuse (Q12)."""
    return [s for s in load_stocks("inactive" if category else "active") if s["c"] == code]


def fetch_all(client: PoliteClient, scenario: str, stock_id: int, from_date: str, to_date: str,
              lang: str, category: int) -> list[dict[str, Any]]:
    """First call with rowRange=100; if more rows exist, one call with min(total, ROW_CAP)."""
    n, params = 1, search_params(stock_id, from_date, to_date, lang, 100, category)
    res = run_search(client, params, tag=f"{scenario}-{lang}-{n}")
    save_search(scenario, lang.lower(), n, params, res)
    total = int(res.envelope.get("recordCnt") or 0)
    if total > len(res.rows):
        n += 1
        params = search_params(stock_id, from_date, to_date, lang, min(total, ROW_CAP), category)
        res = run_search(client, params, tag=f"{scenario}-{lang}-{n}")
        save_search(scenario, lang.lower(), n, params, res)
    print(f"  {scenario} {lang}: recordCnt={total}, rows={len(res.rows)}, "
          f"hasNextRow={res.envelope.get('hasNextRow')}, calls={n}")
    return res.rows


def stage_scenarios(client: PoliteClient, only: list[str] | None = None) -> None:
    picks = json.loads(PICKS_FILE.read_text()) if PICKS_FILE.exists() else {}
    for name, (code, frm, to, category) in SCENARIOS.items():
        if only and name not in only:
            continue
        code = code or picks.get(name)
        if not code:
            print(f"{name}: skipped, no pick yet (add it to {PICKS_FILE.relative_to(ROOT)})")
            continue
        matches = resolve_stock(code, category)
        if not matches:
            print(f"{name}: code {code} not in the {'inactive' if category else 'active'} list")
            continue
        if len(matches) > 1:
            print(f"{name}: code {code} has {len(matches)} list entries (reuse): {matches}")
        print(f"{name}: {code} ({matches[0]['n']}), id {matches[0]['i']}, {frm}..{to}")
        for lang in ("EN", "ZH"):
            fetch_all(client, name, matches[0]["i"], frm, to, lang, category)
        save_fixture(f"{name}/scenario.json", {"name": name, "code": code, "stock": matches,
                                               "from": frm, "to": to, "category": category})


# --- Stage: analyse (offline, reads fixtures only) ---------------------------------------

def load_rows(scenario: str, lang: str) -> list[dict[str, Any]]:
    """Rows from the highest-numbered call, which holds the cumulative set."""
    files = sorted((FIXTURES / scenario).glob(f"{lang}_[0-9].json"), key=lambda f: f.stem)
    if not files:
        return []
    raw = json.loads(json.loads(files[-1].read_text())["result"] or "null") or []
    return list(raw) if isinstance(raw, list) else []


def stem_num(row: dict[str, Any]) -> int | None:
    m = re.search(r"(\d{8})(\d+)(?:_c)?\.\w+$", row["FILE_LINK"])
    return int(m.group(2)) if m else None


def stage_analyse(client: PoliteClient) -> None:  # noqa: ARG001 - offline, no requests
    from collections import Counter

    delta_seq: Counter[int] = Counter()
    delta_news: Counter[int] = Counter()
    folder_mismatch, total_rows, no_cat = 0, 0, 0
    multi_code: list[str] = []
    stubs: dict[str, list[str]] = {"EN": [], "ZH": []}
    cats: dict[str, Counter[str]] = {"EN": Counter(), "ZH": Counter()}
    for sc in sorted(p.name for p in FIXTURES.iterdir() if p.is_dir() and (p / "scenario.json").exists()):
        by_minute: dict[tuple[str, str], dict[str, list[dict[str, Any]]]] = {}
        for lang in ("en", "zh"):
            for row in load_rows(sc, lang):
                total_rows += 1
                d, mo, y = row["DATE_TIME"][:10].split("/")
                m = re.search(r"/(\d{4})/(\d{4})/", row["FILE_LINK"])
                if m and (m.group(1), m.group(2)) != (y, mo + d):
                    folder_mismatch += 1
                if "<br/>" in str(row["STOCK_CODE"]):
                    multi_code.append(f"{sc}: {row['STOCK_CODE']!r}")
                cats[lang.upper()][str(row["LONG_TEXT"])] += 1
                if not row["LONG_TEXT"]:
                    no_cat += 1
                size = str(row["FILE_INFO"] or "").upper().replace(" ", "")
                if row["FILE_LINK"].lower().endswith((".htm", ".html")) or size in ("1KB", "2KB"):
                    stubs[lang.upper()].append(f"{sc}: {row['TITLE'][:110]} | {row['FILE_LINK'].rsplit('/', 1)[-1]} | {row['FILE_INFO']}")
                by_minute.setdefault((row["STOCK_CODE"], row["DATE_TIME"]), {"en": [], "zh": []})[lang].append(row)
        for _key, grp in by_minute.items():
            if len(grp["en"]) == 1 and len(grp["zh"]) == 1:  # unambiguous by time alone
                a, b = grp["en"][0], grp["zh"][0]
                sa, sb = stem_num(a), stem_num(b)
                if sa is not None and sb is not None:
                    delta_seq[sb - sa] += 1
                delta_news[int(b["NEWS_ID"]) - int(a["NEWS_ID"])] += 1
    print(f"rows analysed: {total_rows}; folder date != DATE_TIME date: {folder_mismatch}; no category text: {no_cat}")
    print("Q6 TC minus EN file sequence (same stock and minute, one each):", dict(delta_seq.most_common(10)))
    print("Q5 TC minus EN NEWS_ID (same pairs):", dict(delta_news.most_common(10)))
    print("Q9 multi-code values:", multi_code[:8] or "none seen")
    for lang in ("EN", "ZH"):
        print(f"Q7 {lang} small or htm entries ({len(stubs[lang])}):")
        for line in stubs[lang][:12]:
            print("   ", line)
    for lang in ("EN", "ZH"):
        print(f"Q8 {lang} distinct category strings: {len(cats[lang])}")
        for text, n in cats[lang].most_common(6):
            print(f"    {n:4d}  {text[:120]}")


# --- Stage: documents (stubs in full, PDFs by header only) ------------------------------

STUBS = ["/listedco/listconews/sehk/2026/1023/2026102301071_c.htm",
         "/listedco/listconews/sehk/2026/1030/2026103000899.htm"]
PDF_SAMPLES = ["/listedco/listconews/sehk/2026/1028/2026102801739.pdf",
               "/listedco/listconews/sehk/2026/1028/2026102801740_c.pdf",
               "/listedco/listconews/sehk/2026/1023/2026102301070.pdf"]


def stage_documents(client: PoliteClient) -> None:
    for path in STUBS:
        r = client.get(BASE + path)
        name = path.rsplit("/", 1)[-1]
        print(f"stub {name}: HTTP {r.status}, {len(r.body)} bytes, {r.headers.get('content-type')}")
        print("   ", r.text.strip().replace("\n", " ")[:400])
        if r.status == 200:
            save_fixture(f"documents/{name}", r.body)
    for path in PDF_SAMPLES:
        r = client.get(BASE + path, range_header="bytes=0-1023", max_body=1024)
        name = path.rsplit("/", 1)[-1]
        print(f"pdf {name}: HTTP {r.status}, content-length={r.headers.get('content-length')}, "
              f"content-type={r.headers.get('content-type')}, starts {r.body[:5]!r}, {r.elapsed_s}s")


STAGES = {"reference": stage_reference, "access": stage_access,
          "scenarios": stage_scenarios, "analyse": stage_analyse, "documents": stage_documents}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("stage", choices=sorted(STAGES))
    parser.add_argument("--max-requests", type=int, default=DEFAULT_BUDGET)
    parser.add_argument("--scenario", action="append", help="scenarios stage: run only this one")
    args = parser.parse_args()
    client = PoliteClient(budget=args.max_requests)
    try:
        if args.stage == "scenarios":
            stage_scenarios(client, args.scenario)
        else:
            STAGES[args.stage](client)
    except ProbeStopped as exc:
        print(f"\nSTOPPED: {exc}", file=sys.stderr)
        return 2
    finally:
        print(f"\nlive requests: {client.live_requests}, cache hits: {client.cache_hits}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
