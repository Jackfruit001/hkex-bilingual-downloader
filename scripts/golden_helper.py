"""Draft golden pairing entries for Zarif to verify (Phase 2.4, SPEC §10.4).

Run from the repo root:

    uv run --project backend python scripts/golden_helper.py draft 09688 2026-10-28 2026-10-28
    uv run --project backend python scripts/golden_helper.py draft 00700 2026-10-01 2026-10-31 --pick 3,7
    uv run --project backend python scripts/golden_helper.py draft 00700 2026-10-01 2026-10-31 --sample 6 --seed 1
    uv run --project backend python scripts/golden_helper.py show 09688-12386841
    uv run --project backend python scripts/golden_helper.py list --unverified
    uv run --project backend python scripts/golden_helper.py coverage

`list` prints every entry, one line each. `show` reprints the evidence for one entry in pairs.yaml (its recorded search, and its PDFs from
the cache; `--live` fetches any that are missing).

`draft` searches HKEXnews for the stock and dates (Hong Kong dates), pairs the results with the
app's matcher and prints every announcement with its case types. Nothing else happens until you
name rows (`--pick`) or ask for a stratified `--sample`; then it fetches those rows' PDFs, prints
them side by side with the evidence against the pairing as well as for it, and appends draft
entries to `backend/tests/golden/pairs.yaml` with `verified: false`. Entries already in the file
are never touched. The matcher's view is recorded as `proposal`; whether it is true is for you to
say with both PDFs open.

Live access is polite and bounded: one request at a time, at least a second apart, an identifying
User-Agent, a budget of live requests per run (`--budget`), and the run stops at the first
refusal, block page or redirect. Everything is cached under scripts/.golden_cache (not committed),
so repeats are free; `--offline` forbids live requests altogether. PDFs are never committed: only
their hashes and figure fingerprints are kept (backend/tests/golden/fingerprints.json), and the
search responses a written entry used (backend/tests/fixtures/golden/<scenario>/).
"""

import argparse
import asyncio
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.domain.errors import AppError  # noqa: E402
from app.domain.timeutil import today_hkt  # noqa: E402
from app.domain.validation import (  # noqa: E402
    normalise_stock_code,
    parse_iso_date,
    validate_date_range,
)
from app.hkex.reference import DEFAULT_SNAPSHOT, load_snapshot  # noqa: E402
from tests.golden.draft import (  # noqa: E402
    RowFiles,
    Scenario,
    choose_rows,
    counterpart,
    fetch_row_files,
    find_row,
    load_scenario,
    repair_with_hashes,
    save_fixtures,
    search_and_pair,
    to_entry,
)
from tests.golden.fetch import (  # noqa: E402
    DEFAULT_BUDGET,
    DEFAULT_MAX_BYTES,
    BudgetReached,
    GoldenClient,
    HelperStopped,
)
from tests.golden.render import announcement_table, entry_table, row_detail  # noqa: E402
from tests.golden.schema import CaseType  # noqa: E402
from tests.golden.store import FACTS, PAIRS, append_entries, load_entries, merge_facts  # noqa: E402
from tests.golden.tagging import coverage  # noqa: E402

CACHE = ROOT / "scripts" / ".golden_cache"
FIXTURES = ROOT / "backend" / "tests" / "fixtures" / "golden"


async def show(args: argparse.Namespace) -> int:
    """Reprint the evidence for one entry already in pairs.yaml, from its recorded search."""
    entry = next((e for e in load_entries(PAIRS) if e.id == args.entry_id), None)
    if entry is None:
        raise ValueError(f"no entry {args.entry_id} in {PAIRS.name}")
    folder = FIXTURES / entry.scenario
    try:
        scenario = load_scenario(folder)
    except OSError as exc:
        raise ValueError(f"no recorded search for {entry.scenario} under {FIXTURES}") from exc
    reference = load_snapshot(DEFAULT_SNAPSHOT)
    stock = reference.stocks.resolve(scenario.code, scenario.stock_id).stock
    width = shutil.get_terminal_size((120, 20)).columns
    client = GoldenClient(
        json_dir=folder / "calls",
        pdf_dir=CACHE / "pdf",
        budget=args.budget if args.live else 0,
        max_bytes=args.max_mb * 1024 * 1024,
    )
    try:
        drafted = await search_and_pair(client, stock, reference.categories, scenario)
        n = find_row(drafted, entry)
        try:
            files = await fetch_row_files(client, drafted.rows[n - 1], max_bytes=args.max_mb << 20)
        except BudgetReached as exc:
            print(f"A PDF for this entry is not in the cache ({exc}).", file=sys.stderr)
            print("Run again with --live to fetch it (one request per PDF).", file=sys.stderr)
            return 2
        final = repair_with_hashes(drafted, files.facts_by_key())
        announcement = counterpart(final, drafted.rows[n - 1])
        print(f"{stock.code} {stock.name_en}; entry {entry.id} (verified: {entry.verified})")
        print()
        print(
            "\n".join(
                row_detail(n, announcement, final.tags[announcement.id], entry.id, files, width)
            )
        )
        en_id = entry.truth.en.news_id if entry.truth.en else None
        tc_id = entry.truth.tc.news_id if entry.truth.tc else None
        shown_en = announcement.en.news_id if announcement.en else None
        shown_tc = announcement.tc.news_id if announcement.tc else None
        print(
            f"\nentry truth: English news {en_id}, Chinese news {tc_id}, absent {entry.truth.absent}"
        )
        if (en_id, tc_id) != (shown_en, shown_tc):
            print(
                f"note: the matcher's pair above is English news {shown_en}, Chinese news {shown_tc}"
            )
        if entry.notes:
            print(f"notes: {entry.notes}")
        return 0
    finally:
        await client.aclose()


async def draft(args: argparse.Namespace) -> int:
    code = normalise_stock_code(args.code)
    start, end = parse_iso_date(args.start), parse_iso_date(args.end)
    validate_date_range(start, end, today_hkt())
    reference = load_snapshot(DEFAULT_SNAPSHOT)  # bundled copy: no reference-list requests
    resolution = reference.stocks.resolve(code, args.stock_id)
    stock = resolution.stock
    width = shutil.get_terminal_size((120, 20)).columns

    print(
        f"{stock.code} {stock.name_en} ({'listed' if stock.active else 'delisted'}), {start} to {end} HKT"
    )
    for other in resolution.alternatives:
        print(f"  note: code {code} was also {other.name_en} (id {other.stock_id}); use --stock-id")

    client = GoldenClient(
        json_dir=CACHE / "json",
        pdf_dir=CACHE / "pdf",
        budget=0 if args.offline else args.budget,
        max_bytes=args.max_mb * 1024 * 1024,
    )
    try:
        drafted = await search_and_pair(
            client, stock, reference.categories, Scenario.for_stock(stock, start, end)
        )
        diag = drafted.search.diagnostics
        print(
            f"{len(drafted.search.english)} English and {len(drafted.search.chinese)} Chinese "
            f"documents; {len(drafted.rows)} announcements "
            f"{dict(drafted.result.diagnostics.by_status)}; {client.requests_made} live requests"
        )
        for warning in (*diag.warnings, *drafted.result.diagnostics.warnings):
            print(f"  warning: {warning}")
        print()
        print("\n".join(announcement_table(drafted.rows, drafted.tags, width)))

        taken = {e.id for e in load_entries(PAIRS)}
        rows = choose_rows(drafted, pick=args.pick, sample=args.sample, seed=args.seed, taken=taken)
        if not rows:
            print("\nNothing chosen. Use --pick N,N or --sample N to draft entries.")
            return 0

        files: dict[int, RowFiles] = {}
        facts = {}
        for n in rows:
            files[n] = await fetch_row_files(
                client, drafted.rows[n - 1], max_bytes=args.max_mb << 20
            )
            facts.update(files[n].facts_by_key())
        final = repair_with_hashes(drafted, facts) if facts else drafted

        entries = []
        for n in rows:
            announcement = counterpart(final, drafted.rows[n - 1])
            entry = to_entry(final, announcement)
            entries.append(entry)
            print()
            print(
                "\n".join(
                    row_detail(
                        n,
                        announcement,
                        [CaseType(t) for t in entry.case_types],
                        entry.id,
                        files[n],
                        width,
                    )
                )
            )

        print()
        if args.dry_run:
            print(f"dry run: {len(entries)} entries drafted, nothing written")
            return 0
        added = append_entries(PAIRS, entries)
        merge_facts(FACTS, facts)
        if added:
            folder = save_fixtures(client, final, FIXTURES)
            print(
                f"added {len(added)} entries to {PAIRS.relative_to(ROOT)}, recorded {folder.relative_to(ROOT)}"
            )
            print("Next: open both PDFs for each, correct `truth` if wrong, set `verified: true`.")
        skipped = len(entries) - len(added)
        if skipped:
            print(f"{skipped} entries were already in the file and were left as they are")
        return 0
    finally:
        await client.aclose()


def show_coverage() -> int:
    c = coverage(load_entries(PAIRS))
    print(
        f"entries {c.entries} (verified {c.verified})   issuers {c.issuers_all} (verified {c.issuers_verified})"
    )
    print(f"\n{'case type':<26}{'verified':>9}{'all':>6}")
    for case, (verified, total) in c.by_case.items():
        print(f"{case.value:<26}{verified:>9}{total:>6}")
    print("\nGaps against SPEC section 10.4:" if c.gaps else "\nNo gaps: SPEC section 10.4 is met.")
    for gap in c.gaps:
        print(f"  - {gap}")
    if c.accepted:
        print("\nAccepted gaps (README limitations):")
        for note in c.accepted:
            print(f"  - {note}")
    return 0


def list_entries(args: argparse.Namespace) -> int:
    entries = [e for e in load_entries(PAIRS) if not (args.unverified and e.verified)]
    width = shutil.get_terminal_size((120, 20)).columns
    print("\n".join(entry_table(entries, width)))
    print(f"\n{len(entries)} entries")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    d = sub.add_parser("draft", help="search, pair and draft entries for one stock and date range")
    d.add_argument("code", help="stock code, for example 00700")
    d.add_argument("start", help="first date, YYYY-MM-DD (Hong Kong)")
    d.add_argument("end", help="last date, YYYY-MM-DD (Hong Kong)")
    d.add_argument(
        "--stock-id", type=int, help="HKEXnews id, for a code held by several securities"
    )
    d.add_argument(
        "--pick",
        type=lambda s: [int(x) for x in s.split(",") if x],
        default=[],
        help="row numbers, e.g. 1,4",
    )
    d.add_argument("--sample", type=int, default=0, help="a stratified sample of this many rows")
    d.add_argument("--seed", type=int, default=0)
    d.add_argument("--dry-run", action="store_true", help="show the drafts but write nothing")
    d.add_argument("--offline", action="store_true", help="use the cache only; no live requests")
    d.add_argument(
        "--budget", type=int, default=DEFAULT_BUDGET, help="live requests allowed this run"
    )
    d.add_argument(
        "--max-mb", type=int, default=DEFAULT_MAX_BYTES >> 20, help="skip PDFs larger than this"
    )
    s = sub.add_parser("show", help="reprint the evidence for one entry in pairs.yaml")
    s.add_argument("entry_id", help="an `id` from pairs.yaml, for example 09688-12386841")
    s.add_argument("--live", action="store_true", help="fetch PDFs that are not in the cache")
    s.add_argument(
        "--budget", type=int, default=DEFAULT_BUDGET, help="live requests allowed this run"
    )
    s.add_argument(
        "--max-mb", type=int, default=DEFAULT_MAX_BYTES >> 20, help="skip PDFs larger than this"
    )
    sub.add_parser("coverage", help="what the golden set still lacks (SPEC section 10.4)")
    ls = sub.add_parser("list", help="every entry in pairs.yaml, one line each")
    ls.add_argument("--unverified", action="store_true", help="only entries not yet verified")
    args = parser.parse_args()
    try:
        if args.command == "coverage":
            return show_coverage()
        if args.command == "list":
            return list_entries(args)
        if args.command == "show":
            return asyncio.run(show(args))
        return asyncio.run(draft(args))
    except (AppError, HelperStopped, ValueError) as exc:
        message = exc.message if isinstance(exc, AppError) else str(exc)
        print(f"\nstopped: {message}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
