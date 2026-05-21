from __future__ import annotations

import argparse
import sys

from resource_discovery.request_auth import build_signature


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a resource discovery gateway request signature.")
    parser.add_argument("--secret", required=True)
    parser.add_argument("--method", required=True)
    parser.add_argument("--path", required=True)
    parser.add_argument("--timestamp", required=True)
    parser.add_argument("--nonce", required=True)
    parser.add_argument("--body-file")
    args = parser.parse_args()
    body = b""
    if args.body_file:
        with open(args.body_file, "rb") as handle:
            body = handle.read()
    signature = build_signature(
        secret=args.secret,
        method=args.method,
        path=args.path,
        timestamp=args.timestamp,
        nonce=args.nonce,
        body=body,
    )
    sys.stdout.write(signature)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
