"""Build the bundled reference snapshot from the recorded HKEXnews reference files.

    uv run --project backend python scripts/build_snapshot.py --generated-at 2026-10-30

The snapshot is only a fallback for when HKEXnews' stock and category lists cannot be loaded;
the app uses live data whenever it can. Rebuild it after refreshing the recordings with
`scripts/probe_hkex.py reference`.
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.hkex.reference import DEFAULT_SNAPSHOT, REFERENCE_FILES, build_snapshot  # noqa: E402

RAW = ROOT / "backend" / "tests" / "fixtures" / "raw" / "reference"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generated-at", required=True, help="date the recordings were made, YYYY-MM-DD (HKT)")
    args = parser.parse_args()
    generated_at = datetime.fromisoformat(args.generated_at).replace(tzinfo=ZoneInfo("Asia/Hong_Kong"))
    raw = {name: json.loads((RAW / f"{name}.json").read_text(encoding="utf-8")) for name in REFERENCE_FILES}
    data = build_snapshot(raw, generated_at)
    DEFAULT_SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_SNAPSHOT.write_bytes(data)
    print(f"wrote {DEFAULT_SNAPSHOT.relative_to(ROOT)}: {len(data):,} bytes, generated {generated_at.isoformat()}")


if __name__ == "__main__":
    main()
