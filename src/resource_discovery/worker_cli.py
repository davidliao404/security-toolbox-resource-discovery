from __future__ import annotations

import argparse
from pathlib import Path

from .queue_backends import SQLiteTaskQueue
from .source_client import FixtureSourceClient
from .sqlite_store import SQLiteResultRepository, SQLiteTaskRepository, initialize_sqlite
from .worker import TaskWorker


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one resource discovery gateway worker iteration.")
    parser.add_argument("--sqlite-path", default="artifacts/integration/resource-discovery.sqlite3")
    parser.add_argument("--fixture", default="tests/fixtures/fofa_results.json")
    args = parser.parse_args()
    initialize_sqlite(args.sqlite_path)
    worker = TaskWorker(
        SQLiteTaskRepository(args.sqlite_path),
        SQLiteResultRepository(args.sqlite_path),
        SQLiteTaskQueue(args.sqlite_path),
        FixtureSourceClient(Path(args.fixture)),
    )
    print(worker.run_once())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
