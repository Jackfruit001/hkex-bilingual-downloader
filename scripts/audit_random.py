"""Audit the app on random active stocks over the last 90 days (PLAN 6.3, SPEC §10.8).

    uv run --project backend python scripts/audit_random.py --stocks 30 --seed 1

For each stock: search both sections, pair, and verify one confirmed pair end to end (both PDFs
downloaded and checked, ZIP built). A few `check` entries get the content check. Writes
docs/audit-report.md. Live and polite: one request at a time, at least a second apart.
Failures are reported, never hidden.
"""

import argparse
import asyncio
import random
import sys
import tempfile
import time
import zipfile
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.domain.errors import AppError  # noqa: E402
from app.domain.models import Lang, Stock  # noqa: E402
from app.domain.timeutil import today_hkt  # noqa: E402
from app.downloads.fetcher import Fetcher  # noqa: E402
from app.downloads.zipper import build_zip  # noqa: E402
from app.hkex.client import HkexClient  # noqa: E402
from app.hkex.reference import ReferenceData, ReferenceService  # noqa: E402
from app.hkex.search import search_both  # noqa: E402
from app.naming.filenames import name_documents  # noqa: E402
from app.pairing.content_check import (  # noqa: E402
    TextStatus,
    best_match,
    extract_text_async,
    fingerprint,
    readable,
)
from app.pairing.matcher import pair_documents  # noqa: E402
from app.pairing.models import Status  # noqa: E402

DAYS = 90
MAX_CONTENT_CHECKS = 8


def ordinary(code: str) -> bool:
    n = int(code)
    return n < 4000 or 6000 <= n < 10000


async def audit_stock(
    client: HkexClient,
    fetcher: Fetcher,
    reference: ReferenceData,
    stock: Stock,
    state: dict[str, int],
) -> dict[str, object]:
    row: dict[str, object] = {"code": stock.code, "name": stock.name_en}
    end = today_hkt()
    start = end - timedelta(days=DAYS)
    began = time.monotonic()
    try:
        found = await search_both(client, stock, start, end, reference.categories)
    except AppError as exc:
        row["error"] = f"{exc.code.value}: {exc.message}"
        return row
    paired = pair_documents(found.english, found.chinese, searched=(start, end))
    counts = paired.diagnostics.by_status
    row.update(
        en=len(found.english), tc=len(found.chinese), seconds=round(time.monotonic() - began, 1)
    )
    row.update({s.value: counts.get(s.value, 0) for s in Status})
    row["warnings"] = "; ".join(found.diagnostics.warnings + list(paired.diagnostics.warnings))

    names = name_documents([*found.english, *found.chinese], stock.code)
    pair = next(
        (
            a
            for a in paired.announcements
            if a.status is Status.MATCHED
            and a.en
            and a.tc
            and a.en.path in names
            and a.tc.path in names
        ),
        None,
    )
    if pair and pair.en and pair.tc:
        try:
            files = [(names[d.path], await fetcher.fetch(d.path)) for d in (pair.en, pair.tc)]
            with tempfile.TemporaryDirectory() as tmp:
                target = Path(tmp) / "pair.zip"
                build_zip(target, files)
                with zipfile.ZipFile(target) as z:
                    assert z.testzip() is None
            row["pair_download"] = "ok"
        except (AppError, AssertionError) as exc:
            row["pair_download"] = f"FAILED: {exc}"
    else:
        row["pair_download"] = "no confirmed pair to test"

    check = next(
        (a for a in paired.announcements if a.status is Status.CHECK and a.en and a.tc), None
    )
    if check and check.en and check.tc and state["checks"] < MAX_CONTENT_CHECKS:
        state["checks"] += 1
        try:
            texts = [
                readable(
                    lang, await extract_text_async((await fetcher.fetch(d.path)).file.read_bytes())
                )
                for lang, d in ((Lang.EN, check.en), (Lang.TC, check.tc))
            ]
            if all(t.status is TextStatus.OK for t in texts):
                verdict = best_match(
                    "en", fingerprint(texts[0].text), {"tc": fingerprint(texts[1].text)}
                )
                row["content_check"] = (
                    f"{verdict.score:.0%}, conclusive={verdict.conclusive}" if verdict else "n/a"
                )
            else:
                row["content_check"] = "unavailable"
        except AppError as exc:
            row["content_check"] = f"FAILED: {exc.code.value}"
    return row


def write_report(rows: list[dict[str, object]], seed: int, out: Path) -> None:
    ok = [r for r in rows if "error" not in r]

    def total(key: str) -> int:
        return sum(int(str(r.get(key, 0))) for r in ok)

    downloads = [str(r.get("pair_download", "")) for r in ok]
    lines = [
        "# Audit report",
        "",
        f"Random active stocks, last {DAYS} days, seed {seed}, "
        f"run on {today_hkt().isoformat()} (Hong Kong time).",
        "",
        f"- Stocks audited: {len(rows)}; searches that failed: {len(rows) - len(ok)}",
        f"- Announcements: {sum(total(k) for k in ('matched', 'check', 'en_only', 'tc_only'))}"
        f" ({total('matched')} matched, {total('check')} check, "
        f"{total('en_only')} English only, {total('tc_only')} Chinese only)",
        f"- Pair downloads verified: {downloads.count('ok')}; "
        f"failed: {sum(d.startswith('FAILED') for d in downloads)}",
        "",
        "| Code | Company | EN | TC | Matched | Check | EN only | TC only "
        "| Pair download | Content check | Notes |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        if "error" in r:
            lines.append(f"| {r['code']} | {r['name']} | | | | | | | | | {r['error']} |")
            continue
        cells = [
            r["code"],
            r["name"],
            r["en"],
            r["tc"],
            r["matched"],
            r["check"],
            r["en_only"],
            r["tc_only"],
            r["pair_download"],
            r.get("content_check", ""),
            r["warnings"],
        ]
        lines.append("| " + " | ".join(str(c) for c in cells) + " |")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


async def main(count: int, seed: int, out: Path) -> None:
    client = HkexClient(max_concurrency=1, min_interval_s=1.0)
    try:
        reference = await ReferenceService(client).get()
        rng = random.Random(seed)
        active = reference.stocks.active()
        common = [s for s in active if ordinary(s.code)]
        other = [s for s in active if not ordinary(s.code)]
        picks = rng.sample(common, count - max(count // 6, 1)) + rng.sample(
            other, max(count // 6, 1)
        )
        fetcher = Fetcher(client)
        state = {"checks": 0}
        rows = []
        for stock in picks:
            print(f"auditing {stock.code} {stock.name_en}", flush=True)
            rows.append(await audit_stock(client, fetcher, reference, stock, state))
            write_report(rows, seed, out)  # keep partial results if the run is stopped
    finally:
        await client.aclose()
    print(f"wrote {out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stocks", type=int, default=30)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--out", type=Path, default=ROOT / "docs" / "audit-report.md")
    args = parser.parse_args()
    asyncio.run(main(args.stocks, args.seed, args.out))
