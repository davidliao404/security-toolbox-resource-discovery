from __future__ import annotations

import argparse

from resource_discovery.ops_cli import main


def run() -> int:
    parser = argparse.ArgumentParser(description="Run signed production-like gateway smoke test.")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--client-id", required=True)
    parser.add_argument("--secret", required=True)
    parser.add_argument("--tenant-id", default="tenant_poc")
    parser.add_argument("--timeout-seconds", type=float, default=60)
    args = parser.parse_args()
    return main(
        [
            "smoke-test",
            "--base-url",
            args.base_url,
            "--client-id",
            args.client_id,
            "--secret",
            args.secret,
            "--tenant-id",
            args.tenant_id,
            "--timeout-seconds",
            str(args.timeout_seconds),
        ]
    )


if __name__ == "__main__":
    raise SystemExit(run())
