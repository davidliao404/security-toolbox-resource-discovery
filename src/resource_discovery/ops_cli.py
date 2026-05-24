from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config

from .config import GatewaySettings, load_settings
from .request_auth import build_signature
from .scope_guard import TenantScopeProfile
from .sqlite_store import SQLiteScopeProfileRepository, _connect, initialize_sqlite


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Resource discovery gateway operations CLI.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    _settings_args(subparsers.add_parser("verify-config"))

    migrate = subparsers.add_parser("migrate")
    migrate.add_argument("--database-url")
    migrate.add_argument("--alembic-ini", default="alembic.ini")

    seed = subparsers.add_parser("seed-scope-profile")
    _settings_args(seed)
    seed.add_argument("--profile-json", required=True)

    smoke = subparsers.add_parser("smoke-test")
    smoke.add_argument("--base-url", required=True)
    smoke.add_argument("--client-id", required=True)
    smoke.add_argument("--tenant-id", default="tenant_poc")
    smoke.add_argument("--secret", required=True)
    smoke.add_argument("--timeout-seconds", type=float, default=60)

    cleanup = subparsers.add_parser("cleanup-retention")
    _settings_args(cleanup)
    cleanup.add_argument("--older-than-days", type=int, default=90)

    args = parser.parse_args(argv)
    if args.command == "verify-config":
        return _verify_config(args)
    if args.command == "migrate":
        return _migrate(args)
    if args.command == "seed-scope-profile":
        return _seed_scope_profile(args)
    if args.command == "smoke-test":
        return _smoke_test(args)
    if args.command == "cleanup-retention":
        return _cleanup_retention(args)
    raise AssertionError(args.command)


def _settings_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--sqlite-path")
    parser.add_argument("--storage-backend")
    parser.add_argument("--database-url")
    parser.add_argument("--queue-backend")
    parser.add_argument("--redis-url")
    parser.add_argument("--client-secrets-file")


def _settings_from_args(args: argparse.Namespace) -> GatewaySettings:
    base = load_settings()
    return GatewaySettings(
        env=base.env,
        api_prefix=base.api_prefix,
        storage_backend=args.storage_backend or base.storage_backend,
        database_url=args.database_url if args.database_url is not None else base.database_url,
        sqlite_path=args.sqlite_path or base.sqlite_path,
        queue_backend=args.queue_backend or base.queue_backend,
        redis_url=args.redis_url or base.redis_url,
        client_secrets_file=args.client_secrets_file or base.client_secrets_file,
        scope_profile_seed=base.scope_profile_seed,
        fixture_path=base.fixture_path,
        result_limit_default=base.result_limit_default,
        result_limit_max=base.result_limit_max,
        nonce_window_seconds=base.nonce_window_seconds,
        log_level=base.log_level,
        worker_max_attempts=base.worker_max_attempts,
        worker_retry_delay_seconds=base.worker_retry_delay_seconds,
        dead_letter_enabled=base.dead_letter_enabled,
        metrics_enabled=base.metrics_enabled,
        log_format=base.log_format,
    )


def _verify_config(args: argparse.Namespace) -> int:
    settings = _settings_from_args(args)
    checks: dict[str, Any] = {
        "storage_backend": settings.storage_backend,
        "queue_backend": settings.queue_backend,
        "client_secrets_file": settings.client_secrets_file,
    }
    if settings.storage_backend == "postgres" and not settings.database_url:
        raise ValueError("RESOURCE_DISCOVERY_DATABASE_URL is required for postgres storage")
    if settings.queue_backend == "redis" and not settings.redis_url:
        raise ValueError("RESOURCE_DISCOVERY_REDIS_URL is required for redis queue")
    secrets_path = Path(settings.client_secrets_file)
    if not secrets_path.exists():
        raise FileNotFoundError(settings.client_secrets_file)
    json.loads(secrets_path.read_text(encoding="utf-8"))
    print(json.dumps({"status": "ok", "checks": checks}, ensure_ascii=False))
    return 0


def _migrate(args: argparse.Namespace) -> int:
    if args.database_url:
        os.environ["RESOURCE_DISCOVERY_DATABASE_URL"] = args.database_url
    alembic_cfg = Config(args.alembic_ini)
    command.upgrade(alembic_cfg, "head")
    print(json.dumps({"status": "ok", "migration": "head"}, ensure_ascii=False))
    return 0


def _seed_scope_profile(args: argparse.Namespace) -> int:
    settings = _settings_from_args(args)
    profile = TenantScopeProfile(**json.loads(Path(args.profile_json).read_text(encoding="utf-8")))
    if settings.storage_backend != "sqlite":
        raise ValueError("seed-scope-profile currently requires sqlite settings in this local CLI path")
    initialize_sqlite(settings.sqlite_path)
    SQLiteScopeProfileRepository(settings.sqlite_path).save(profile)
    print(json.dumps({"status": "ok", "tenant_id": profile.tenant_id, "profile_id": profile.profile_id}, ensure_ascii=False))
    return 0


def _cleanup_retention(args: argparse.Namespace) -> int:
    settings = _settings_from_args(args)
    if settings.storage_backend != "sqlite":
        raise ValueError("cleanup-retention currently requires sqlite settings in this local CLI path")
    initialize_sqlite(settings.sqlite_path)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=args.older_than_days)).isoformat()
    deleted: dict[str, int] = {}
    with _connect(settings.sqlite_path) as conn:
        expired_tasks = conn.execute("select tenant_id, task_id from tasks where updated_at < ?", (cutoff,)).fetchall()
        deleted_results = 0
        for row in expired_tasks:
            cursor = conn.execute(
                "delete from results where tenant_id=? and task_id=?",
                (row["tenant_id"], row["task_id"]),
            )
            deleted_results += cursor.rowcount
        deleted["results"] = deleted_results
        cursor = conn.execute("delete from tasks where updated_at < ?", (cutoff,))
        deleted["tasks"] = cursor.rowcount
        for table in ("nonces", "audit_events"):
            column = "expires_at" if table == "nonces" else "created_at"
            cursor = conn.execute(f"delete from {table} where {column} < ?", (cutoff,))
            deleted[table] = cursor.rowcount
    print(json.dumps({"status": "ok", "deleted": deleted}, ensure_ascii=False))
    return 0


def _smoke_test(args: argparse.Namespace) -> int:
    import httpx

    client = httpx.Client(base_url=args.base_url, timeout=10)
    path = "/api/v1/discovery/scope-profile"
    headers = _signed_headers(args.secret, args.tenant_id, args.client_id, "GET", path, b"")
    profile = client.get(path, headers=headers)
    profile.raise_for_status()

    task_path = "/api/v1/discovery/tasks"
    body = json.dumps(
        {
            "profile_id": profile.json()["profile_id"],
            "requested_scope": profile.json().get("default_scope", {}),
            "engines": ["fofa"],
            "discovery_strategy": "baseline",
            "result_limit": 20,
            "purpose": "prodlike_smoke_test",
        },
        separators=(",", ":"),
    ).encode("utf-8")
    created = client.post(task_path, content=body, headers=_signed_headers(args.secret, args.tenant_id, args.client_id, "POST", task_path, body))
    created.raise_for_status()
    task_id = created.json()["task_id"]

    deadline = time.time() + args.timeout_seconds
    status_payload = {}
    while time.time() < deadline:
        status_path = f"/api/v1/discovery/tasks/{task_id}"
        status_response = client.get(status_path, headers=_signed_headers(args.secret, args.tenant_id, args.client_id, "GET", status_path, b""))
        status_response.raise_for_status()
        status_payload = status_response.json()
        if status_payload["status"] in {"success", "partial_success", "failed"}:
            break
        time.sleep(1)

    result_path = f"/api/v1/discovery/tasks/{task_id}/results?result_type=assets&limit=20"
    result_response = client.get(
        result_path,
        headers=_signed_headers(args.secret, args.tenant_id, args.client_id, "GET", result_path, b""),
    )
    result_response.raise_for_status()
    result_payload = result_response.json()
    print(
        json.dumps(
            {"status": status_payload.get("status"), "task_id": task_id, "asset_count": len(result_payload.get("assets", []))},
            ensure_ascii=False,
        )
    )
    return 0


def _signed_headers(secret: str, tenant_id: str, client_id: str, method: str, path: str, body: bytes) -> dict[str, str]:
    timestamp = datetime.now(timezone.utc).isoformat()
    nonce = f"ops-{time.time_ns()}"
    signature = build_signature(secret=secret, method=method, path=path, timestamp=timestamp, nonce=nonce, body=body)
    return {
        "X-Tenant-Id": tenant_id,
        "X-Client-Id": client_id,
        "X-Timestamp": timestamp,
        "X-Nonce": nonce,
        "X-Signature": signature,
        "Content-Type": "application/json",
    }


if __name__ == "__main__":
    raise SystemExit(main())
