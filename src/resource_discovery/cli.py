from __future__ import annotations

import argparse
import json
from pathlib import Path

from .execution import run_discovery
from .task_store import FileTaskStore


def run_fixture_demo(seeds_path, fixture_path) -> dict:
    return run_discovery(seeds_path=seeds_path, mode="fixture", fixture_path=fixture_path)


def run_and_maybe_save(
    seeds_path,
    mode="fixture",
    fixture_path=None,
    fofa_email=None,
    fofa_key=None,
    allow_live_fofa=False,
    save_dir=None,
) -> dict:
    payload = run_discovery(
        seeds_path=seeds_path,
        mode=mode,
        fixture_path=fixture_path,
        fofa_email=fofa_email,
        fofa_key=fofa_key,
        allow_live_fofa=allow_live_fofa,
    )
    if save_dir is not None:
        saved_path = FileTaskStore(save_dir).save(payload)
        payload = {**payload, "saved_snapshot_path": _display_path(saved_path)}
    return payload


def list_snapshots(save_dir, tenant_id) -> list[dict]:
    return FileTaskStore(save_dir).list(tenant_id)


def load_snapshot(save_dir, tenant_id, task_id) -> dict:
    return FileTaskStore(save_dir).load(tenant_id, task_id)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run offline FOFA resource discovery PoC.")
    parser.add_argument("--seeds", required=True, help="Path to seeds JSON file.")
    parser.add_argument("--mode", choices=["fixture", "dry-run", "live"], default="fixture")
    parser.add_argument("--fixture", help="Path to FOFA-like fixture JSON file.")
    parser.add_argument("--fofa-email", help="FOFA account email for live mode.")
    parser.add_argument("--fofa-key", help="FOFA API key for live mode.")
    parser.add_argument("--allow-live-fofa", action="store_true", help="Explicitly enable live FOFA API calls.")
    parser.add_argument("--save-dir", help="Directory for persisted task snapshots.")
    parser.add_argument("--list-snapshots", action="store_true", help="List persisted task snapshot summaries.")
    parser.add_argument("--show-snapshot", help="Load and print a persisted task snapshot by task ID.")
    parser.add_argument("--tenant-id", help="Tenant ID for listing or showing snapshots.")
    args = parser.parse_args()
    if args.list_snapshots:
        payload = list_snapshots(_required_save_dir(args.save_dir), _required_tenant_id(args.tenant_id))
    elif args.show_snapshot:
        payload = load_snapshot(
            _required_save_dir(args.save_dir),
            _required_tenant_id(args.tenant_id),
            args.show_snapshot,
        )
    else:
        payload = run_and_maybe_save(
            seeds_path=args.seeds,
            mode=args.mode,
            fixture_path=args.fixture,
            fofa_email=args.fofa_email,
            fofa_key=args.fofa_key,
            allow_live_fofa=args.allow_live_fofa,
            save_dir=args.save_dir,
        )
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _required_save_dir(save_dir):
    if not save_dir:
        raise SystemExit("--save-dir is required")
    return save_dir


def _required_tenant_id(tenant_id):
    if not tenant_id:
        raise SystemExit("--tenant-id is required")
    return tenant_id


def _display_path(path: Path) -> str:
    return path.as_posix()


if __name__ == "__main__":
    main()
