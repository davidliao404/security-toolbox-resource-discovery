from __future__ import annotations

import argparse
import json

from .execution import run_discovery


def run_fixture_demo(seeds_path, fixture_path) -> dict:
    return run_discovery(seeds_path=seeds_path, mode="fixture", fixture_path=fixture_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run offline FOFA resource discovery PoC.")
    parser.add_argument("--seeds", required=True, help="Path to seeds JSON file.")
    parser.add_argument("--mode", choices=["fixture", "dry-run", "live"], default="fixture")
    parser.add_argument("--fixture", help="Path to FOFA-like fixture JSON file.")
    parser.add_argument("--fofa-email", help="FOFA account email for live mode.")
    parser.add_argument("--fofa-key", help="FOFA API key for live mode.")
    parser.add_argument("--allow-live-fofa", action="store_true", help="Explicitly enable live FOFA API calls.")
    args = parser.parse_args()
    payload = run_discovery(
        seeds_path=args.seeds,
        mode=args.mode,
        fixture_path=args.fixture,
        fofa_email=args.fofa_email,
        fofa_key=args.fofa_key,
        allow_live_fofa=args.allow_live_fofa,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
