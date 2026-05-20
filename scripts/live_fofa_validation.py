from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from resource_discovery.live_validation import run_live_validation


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a scoped live FOFA-compatible validation.")
    parser.add_argument("--domain", required=True, help="Authorized root domain for live validation.")
    parser.add_argument(
        "--output-dir",
        default="artifacts/live-validation",
        help="Ignored directory for live validation seeds and snapshots.",
    )
    parser.add_argument("--page-limit", type=int, default=1, help="Maximum pages per generated query.")
    parser.add_argument("--result-limit", type=int, default=50, help="Maximum results per generated query.")
    args = parser.parse_args()

    summary = run_live_validation(
        args.domain,
        output_dir=args.output_dir,
        page_limit=args.page_limit,
        result_limit=args.result_limit,
    )
    sys.stdout.write(json.dumps(summary, ensure_ascii=False, indent=2))
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
