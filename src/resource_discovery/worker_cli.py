from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

from .backend_factory import build_queue, build_repositories
from .config import load_settings
from .queue_backends import SQLiteTaskQueue
from .source_client import FixtureSourceClient
from .sqlite_store import SQLiteResultRepository, SQLiteTaskRepository, initialize_sqlite
from .worker import TaskWorker


def run_worker(
    worker: TaskWorker,
    *,
    loop: bool = False,
    interval_seconds: float = 5.0,
    max_iterations: int | None = None,
) -> list[dict]:
    results: list[dict] = []
    iterations = 0
    while True:
        result = worker.run_once()
        results.append(result)
        iterations += 1
        if not loop:
            break
        if max_iterations is not None and iterations >= max_iterations:
            break
        if not result.get("processed"):
            time.sleep(interval_seconds)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Run resource discovery gateway worker iterations.")
    parser.add_argument("--sqlite-path", default="artifacts/integration/resource-discovery.sqlite3")
    parser.add_argument("--fixture", default="tests/fixtures/fofa_results.json")
    parser.add_argument("--settings-env", help="Load RESOURCE_DISCOVERY_* settings after setting RESOURCE_DISCOVERY_ENV.")
    parser.add_argument("--loop", action="store_true", help="Continuously poll for queued work.")
    parser.add_argument("--interval-seconds", type=float, default=5.0)
    parser.add_argument("--max-iterations", type=int)
    args = parser.parse_args()
    if args.settings_env:
        os.environ["RESOURCE_DISCOVERY_ENV"] = args.settings_env
        settings = load_settings()
        repositories = build_repositories(settings)
        queue = build_queue(settings)
        worker = TaskWorker(
            repositories.task_repository,
            repositories.result_repository,
            queue,
            FixtureSourceClient(Path(settings.fixture_path)),
            max_attempts=settings.worker_max_attempts,
            retry_delay_seconds=settings.worker_retry_delay_seconds,
        )
        for result in run_worker(
            worker,
            loop=args.loop,
            interval_seconds=args.interval_seconds,
            max_iterations=args.max_iterations,
        ):
            print(result)
        return 0
    initialize_sqlite(args.sqlite_path)
    worker = TaskWorker(
        SQLiteTaskRepository(args.sqlite_path),
        SQLiteResultRepository(args.sqlite_path),
        SQLiteTaskQueue(args.sqlite_path),
        FixtureSourceClient(Path(args.fixture)),
    )
    for result in run_worker(
        worker,
        loop=args.loop,
        interval_seconds=args.interval_seconds,
        max_iterations=args.max_iterations,
    ):
        print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
