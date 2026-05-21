# Toolbox Integration Delivery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a complete Security Toolbox integration delivery for the resource discovery gateway: FastAPI HTTP service, signed requests, durable SQLite state, Redis-capable queueing, worker execution, and handoff materials.

**Architecture:** Keep `DiscoveryGatewayApi` as the application layer and add deployment adapters around it. FastAPI handles HTTP and auth, SQLite repositories provide integration-grade durable state, queue adapters feed `TaskWorker`, and handoff docs describe the exact integration sequence for the Toolbox team.

**Tech Stack:** Python 3.11, pytest, FastAPI, uvicorn, httpx TestClient, SQLite via stdlib `sqlite3`, optional Redis via `redis` package, existing `resource_discovery` package.

---

## File Structure

- Create `src/resource_discovery/config.py`: environment-backed settings and local config parsing.
- Create `src/resource_discovery/sqlite_store.py`: SQLite schema initialization and SQLite repository implementations.
- Create `src/resource_discovery/auth_http.py`: HTTP client secret resolver and FastAPI-compatible request authentication helper.
- Create `src/resource_discovery/http_app.py`: FastAPI app factory, routes, dependencies, health checks.
- Create `src/resource_discovery/queue_backends.py`: queue protocol, SQLite queue, Redis queue adapter, memory queue compatibility.
- Create `src/resource_discovery/worker_cli.py`: worker command entrypoint for integration environments.
- Create `scripts/sign_request.py`: signed-request helper for Toolbox curl examples.
- Create `.env.example`: local integration configuration.
- Create `tests/test_config.py`: settings tests.
- Create `tests/test_sqlite_store.py`: SQLite repository and schema tests.
- Create `tests/test_auth_http.py`: HTTP auth and nonce replay tests.
- Create `tests/test_http_app.py`: FastAPI route tests.
- Create `tests/test_queue_backends.py`: queue adapter tests.
- Create `tests/test_worker_delivery.py`: worker retry and persistence tests.
- Modify `pyproject.toml`: add FastAPI, uvicorn, httpx, redis optional/runtime dependencies.
- Modify `src/resource_discovery/task_queue.py`: expose a small queue protocol or align `InMemoryTaskQueue` with queue adapter interface.
- Modify `src/resource_discovery/worker.py`: accept queue protocol, retry metadata, and durable status updates.
- Modify `src/resource_discovery/repositories.py`: add protocols for audit, nonce, client secrets, and queue job persistence if keeping protocols centralized.
- Modify `src/resource_discovery/request_auth.py`: support tenant/client-aware nonce storage without breaking existing tests.
- Modify `README.md`: add Toolbox integration delivery startup and verification commands.
- Modify `docs/resource-discovery/toolbox-api-contract.md`: remove PoC wording that says HTTP auth is not implemented and align FastAPI behavior.
- Modify `docs/resource-discovery/toolbox-handoff.md`: add local startup, signed curl sequence, polling flow, and troubleshooting.
- Modify `docs/resource-discovery/production-readiness-checklist.md`: mark FastAPI auth, SQLite integration storage, and Redis-capable queue as integration-ready, while preserving production caveats.

## Task 0: Baseline And Branch Hygiene

**Files:**
- Read: `docs/superpowers/specs/2026-05-21-toolbox-integration-delivery-design.md`
- Read: `docs/resource-discovery/toolbox-api-contract.md`
- Read: `src/resource_discovery/gateway_api.py`
- Read: `src/resource_discovery/worker.py`
- Read: `src/resource_discovery/request_auth.py`

- [ ] **Step 1: Confirm working tree ownership**

Run:

```powershell
git status --short --branch
```

Expected: identify existing uncommitted files. If unrelated files are already modified, do not edit or revert them unless the task explicitly requires that file.

- [ ] **Step 2: Run baseline tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Expected: existing suite passes before implementation starts. If it fails, record failing tests and fix only failures that block this plan.

- [ ] **Step 3: Confirm no secrets are present**

Run:

```powershell
rg "FOFA_API_KEY|FOFA_EMAIL|X-Signature|secret|token|api_key" . -g "!artifacts/**" -g "!*.pyc"
```

Expected: only placeholders, tests, and docs examples appear. Remove any real key before proceeding.

## Task 1: Dependencies And Configuration

**Files:**
- Modify: `pyproject.toml`
- Create: `.env.example`
- Create: `src/resource_discovery/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write failing settings tests**

Create `tests/test_config.py`:

```python
from resource_discovery.config import GatewaySettings, load_settings


def test_load_settings_uses_defaults(monkeypatch):
    monkeypatch.delenv("RESOURCE_DISCOVERY_SQLITE_PATH", raising=False)
    settings = load_settings()
    assert settings.api_prefix == "/api/v1/discovery"
    assert settings.sqlite_path == "artifacts/integration/resource-discovery.sqlite3"
    assert settings.queue_backend == "sqlite"
    assert settings.nonce_window_seconds == 300


def test_load_settings_reads_environment(monkeypatch):
    monkeypatch.setenv("RESOURCE_DISCOVERY_SQLITE_PATH", "artifacts/test.sqlite3")
    monkeypatch.setenv("RESOURCE_DISCOVERY_QUEUE_BACKEND", "redis")
    monkeypatch.setenv("RESOURCE_DISCOVERY_REDIS_URL", "redis://localhost:6379/3")
    monkeypatch.setenv("RESOURCE_DISCOVERY_RESULT_LIMIT_MAX", "250")
    settings = load_settings()
    assert settings.sqlite_path == "artifacts/test.sqlite3"
    assert settings.queue_backend == "redis"
    assert settings.redis_url == "redis://localhost:6379/3"
    assert settings.result_limit_max == 250


def test_gateway_settings_rejects_unknown_queue_backend():
    try:
        GatewaySettings(queue_backend="filesystem")
    except ValueError as exc:
        assert "Unsupported queue backend" in str(exc)
    else:
        raise AssertionError("Expected unsupported queue backend to be rejected")
```

- [ ] **Step 2: Run settings tests and verify failure**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_config.py -q
```

Expected: fails because `resource_discovery.config` does not exist.

- [ ] **Step 3: Add dependencies**

Modify `pyproject.toml`:

```toml
dependencies = [
  "PyYAML>=6.0",
  "fastapi>=0.111",
  "uvicorn>=0.30",
  "redis>=5.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "httpx>=0.27"]
```

- [ ] **Step 4: Implement settings**

Create `src/resource_discovery/config.py`:

```python
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class GatewaySettings:
    env: str = "local"
    api_prefix: str = "/api/v1/discovery"
    sqlite_path: str = "artifacts/integration/resource-discovery.sqlite3"
    queue_backend: str = "sqlite"
    redis_url: str = "redis://localhost:6379/0"
    client_secrets_file: str = "artifacts/integration/client-secrets.json"
    scope_profile_seed: str = "examples/scope_profile.json"
    result_limit_default: int = 100
    result_limit_max: int = 500
    nonce_window_seconds: int = 300
    log_level: str = "INFO"

    def __post_init__(self) -> None:
        if self.queue_backend not in {"memory", "sqlite", "redis"}:
            raise ValueError(f"Unsupported queue backend: {self.queue_backend}")
        if self.result_limit_default < 1:
            raise ValueError("RESOURCE_DISCOVERY_RESULT_LIMIT_DEFAULT must be positive")
        if self.result_limit_max < self.result_limit_default:
            raise ValueError("RESOURCE_DISCOVERY_RESULT_LIMIT_MAX must be >= default")
        if self.nonce_window_seconds < 1:
            raise ValueError("RESOURCE_DISCOVERY_NONCE_WINDOW_SECONDS must be positive")


def load_settings() -> GatewaySettings:
    return GatewaySettings(
        env=os.getenv("RESOURCE_DISCOVERY_ENV", "local"),
        api_prefix=os.getenv("RESOURCE_DISCOVERY_API_PREFIX", "/api/v1/discovery"),
        sqlite_path=os.getenv(
            "RESOURCE_DISCOVERY_SQLITE_PATH",
            "artifacts/integration/resource-discovery.sqlite3",
        ),
        queue_backend=os.getenv("RESOURCE_DISCOVERY_QUEUE_BACKEND", "sqlite"),
        redis_url=os.getenv("RESOURCE_DISCOVERY_REDIS_URL", "redis://localhost:6379/0"),
        client_secrets_file=os.getenv(
            "RESOURCE_DISCOVERY_CLIENT_SECRETS_FILE",
            "artifacts/integration/client-secrets.json",
        ),
        scope_profile_seed=os.getenv("RESOURCE_DISCOVERY_SCOPE_PROFILE_SEED", "examples/scope_profile.json"),
        result_limit_default=int(os.getenv("RESOURCE_DISCOVERY_RESULT_LIMIT_DEFAULT", "100")),
        result_limit_max=int(os.getenv("RESOURCE_DISCOVERY_RESULT_LIMIT_MAX", "500")),
        nonce_window_seconds=int(os.getenv("RESOURCE_DISCOVERY_NONCE_WINDOW_SECONDS", "300")),
        log_level=os.getenv("RESOURCE_DISCOVERY_LOG_LEVEL", "INFO"),
    )
```

- [ ] **Step 5: Add `.env.example`**

Create `.env.example`:

```dotenv
RESOURCE_DISCOVERY_ENV=local
RESOURCE_DISCOVERY_API_PREFIX=/api/v1/discovery
RESOURCE_DISCOVERY_SQLITE_PATH=artifacts/integration/resource-discovery.sqlite3
RESOURCE_DISCOVERY_QUEUE_BACKEND=sqlite
RESOURCE_DISCOVERY_REDIS_URL=redis://localhost:6379/0
RESOURCE_DISCOVERY_CLIENT_SECRETS_FILE=artifacts/integration/client-secrets.json
RESOURCE_DISCOVERY_SCOPE_PROFILE_SEED=examples/scope_profile.json
RESOURCE_DISCOVERY_RESULT_LIMIT_DEFAULT=100
RESOURCE_DISCOVERY_RESULT_LIMIT_MAX=500
RESOURCE_DISCOVERY_NONCE_WINDOW_SECONDS=300
RESOURCE_DISCOVERY_LOG_LEVEL=INFO
FOFA_BASE_URL=https://fofa.info/api/v1/search/all
FOFA_EMAIL=<fofa-email-placeholder>
FOFA_API_KEY=<fofa-api-key-placeholder>
FOFA_FULL_HISTORY=false
```

- [ ] **Step 6: Verify settings tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_config.py -q
```

Expected: `3 passed`.

- [ ] **Step 7: Commit**

Run:

```powershell
git add pyproject.toml .env.example src/resource_discovery/config.py tests/test_config.py
git commit -m "feat: add gateway integration settings"
```

## Task 2: SQLite Schema And Durable Repositories

**Files:**
- Create: `src/resource_discovery/sqlite_store.py`
- Modify: `src/resource_discovery/repositories.py`
- Test: `tests/test_sqlite_store.py`

- [ ] **Step 1: Write failing SQLite repository tests**

Create `tests/test_sqlite_store.py`:

```python
from pathlib import Path

from resource_discovery.scope_guard import TenantScopeProfile
from resource_discovery.sqlite_store import (
    SQLiteAuditRepository,
    SQLiteNonceRepository,
    SQLiteResultRepository,
    SQLiteScopeProfileRepository,
    SQLiteTaskRepository,
    initialize_sqlite,
)


def test_sqlite_task_repository_round_trips_task(tmp_path):
    db_path = tmp_path / "gateway.sqlite3"
    initialize_sqlite(db_path)
    repo = SQLiteTaskRepository(db_path)
    payload = {"task": {"tenant_id": "tenant_a", "task_id": "task_1", "status": "queued"}, "request": {}}
    repo.create(payload)
    payload["task"]["status"] = "running"
    repo.update(payload)
    assert repo.load("tenant_a", "task_1")["task"]["status"] == "running"
    assert repo.list("tenant_a")[0]["task_id"] == "task_1"


def test_sqlite_result_repository_paginates_by_type(tmp_path):
    db_path = tmp_path / "gateway.sqlite3"
    initialize_sqlite(db_path)
    repo = SQLiteResultRepository(db_path, max_page_limit=2)
    repo.save_results(
        "tenant_a",
        "task_1",
        {
            "assets": [{"asset_id": "a1"}, {"asset_id": "a2"}, {"asset_id": "a3"}],
            "services": [{"service_id": "s1"}],
            "source_evidence": [{"evidence_id": "e1"}],
        },
    )
    first = repo.load_results("tenant_a", "task_1", None, 2, result_type="assets")
    second = repo.load_results("tenant_a", "task_1", first["page"]["next_cursor"], 2, result_type="assets")
    assert [item["asset_id"] for item in first["assets"]] == ["a1", "a2"]
    assert [item["asset_id"] for item in second["assets"]] == ["a3"]
    assert second["page"]["next_cursor"] is None


def test_sqlite_scope_profile_repository_loads_active_profile(tmp_path):
    db_path = tmp_path / "gateway.sqlite3"
    initialize_sqlite(db_path)
    repo = SQLiteScopeProfileRepository(db_path)
    profile = TenantScopeProfile(
        tenant_id="tenant_a",
        profile_id="profile_1",
        status="active",
        root_domains=["example.com"],
        domains=[],
        ip_cidrs=[],
        org_names=[],
        allowed_engines=["fofa"],
        default_scope={"root_domains": ["example.com"]},
        limits={"max_results_per_task": 100, "max_queries_per_task": 10},
        authorization_note="Customer approval for example.com.",
    )
    repo.save(profile)
    assert repo.load_active("tenant_a", "profile_1").root_domains == ["example.com"]


def test_sqlite_nonce_repository_rejects_replay(tmp_path):
    from datetime import datetime, timezone

    db_path = tmp_path / "gateway.sqlite3"
    initialize_sqlite(db_path)
    repo = SQLiteNonceRepository(db_path, window_seconds=300)
    timestamp = datetime(2026, 5, 22, 10, 0, tzinfo=timezone.utc)
    assert repo.remember_once("nonce-1", timestamp)
    assert not repo.remember_once("nonce-1", timestamp)


def test_sqlite_audit_repository_appends_events(tmp_path):
    db_path = tmp_path / "gateway.sqlite3"
    initialize_sqlite(db_path)
    repo = SQLiteAuditRepository(db_path)
    repo.record_event("tenant_a", "task_1", "discovery_task_started", {"worker": "local"})
    assert repo.list_events("tenant_a")[0]["event_type"] == "discovery_task_started"
```

- [ ] **Step 2: Run SQLite tests and verify failure**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_sqlite_store.py -q
```

Expected: fails because `sqlite_store.py` does not exist.

- [ ] **Step 3: Implement SQLite schema and repositories**

Create `src/resource_discovery/sqlite_store.py` with these public names:

```python
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .repositories import _parse_cursor
from .scope_guard import TenantScopeProfile


def initialize_sqlite(path: str | Path) -> None:
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            create table if not exists tasks (
                tenant_id text not null,
                task_id text not null,
                status text not null,
                payload text not null,
                updated_at text not null,
                primary key (tenant_id, task_id)
            );
            create table if not exists results (
                tenant_id text not null,
                task_id text not null,
                result_type text not null,
                position integer not null,
                payload text not null,
                primary key (tenant_id, task_id, result_type, position)
            );
            create table if not exists scope_profiles (
                tenant_id text not null,
                profile_id text not null,
                status text not null,
                payload text not null,
                updated_at text not null,
                primary key (tenant_id, profile_id)
            );
            create table if not exists nonces (
                nonce text primary key,
                timestamp text not null,
                expires_at text not null
            );
            create table if not exists audit_events (
                id integer primary key autoincrement,
                tenant_id text not null,
                task_id text not null,
                event_type text not null,
                details text not null,
                created_at text not null
            );
            """
        )


def _connect(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(Path(path))
    conn.row_factory = sqlite3.Row
    return conn


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()
```

Add repository classes in the same file:

```python
class SQLiteTaskRepository:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)

    def create(self, payload: dict[str, Any]) -> None:
        self.update(payload)

    def update(self, payload: dict[str, Any]) -> None:
        task = payload["task"]
        with _connect(self.db_path) as conn:
            conn.execute(
                """
                insert into tasks (tenant_id, task_id, status, payload, updated_at)
                values (?, ?, ?, ?, ?)
                on conflict(tenant_id, task_id) do update set
                    status=excluded.status,
                    payload=excluded.payload,
                    updated_at=excluded.updated_at
                """,
                (
                    task["tenant_id"],
                    task["task_id"],
                    task["status"],
                    json.dumps(payload, ensure_ascii=False),
                    _utcnow(),
                ),
            )

    def load(self, tenant_id: str, task_id: str) -> dict[str, Any]:
        with _connect(self.db_path) as conn:
            row = conn.execute(
                "select payload from tasks where tenant_id=? and task_id=?",
                (tenant_id, task_id),
            ).fetchone()
        if row is None:
            raise FileNotFoundError(f"Task not found: {tenant_id}/{task_id}")
        return json.loads(row["payload"])

    def list(self, tenant_id: str) -> list[dict[str, Any]]:
        with _connect(self.db_path) as conn:
            rows = conn.execute(
                "select task_id, status, updated_at from tasks where tenant_id=? order by updated_at desc",
                (tenant_id,),
            ).fetchall()
        return [dict(row) for row in rows]
```

```python
class SQLiteResultRepository:
    def __init__(self, db_path: str | Path, max_page_limit: int = 500) -> None:
        self.db_path = Path(db_path)
        self.max_page_limit = max_page_limit

    def save_results(self, tenant_id: str, task_id: str, payload: dict[str, Any]) -> None:
        with _connect(self.db_path) as conn:
            conn.execute("delete from results where tenant_id=? and task_id=?", (tenant_id, task_id))
            for result_type in ("assets", "services", "source_evidence"):
                for position, item in enumerate(payload.get(result_type, [])):
                    conn.execute(
                        """
                        insert into results (tenant_id, task_id, result_type, position, payload)
                        values (?, ?, ?, ?, ?)
                        """,
                        (tenant_id, task_id, result_type, position, json.dumps(item, ensure_ascii=False)),
                    )

    def load_results(
        self,
        tenant_id: str,
        task_id: str,
        cursor: str | None,
        limit: int,
        result_type: str = "assets",
    ) -> dict[str, Any]:
        if result_type not in {"assets", "services", "source_evidence"}:
            raise ValueError(f"Unsupported result_type: {result_type}")
        start = _parse_cursor(cursor)
        effective_limit = max(1, min(limit, self.max_page_limit))
        with _connect(self.db_path) as conn:
            rows = conn.execute(
                """
                select payload from results
                where tenant_id=? and task_id=? and result_type=?
                order by position
                limit ? offset ?
                """,
                (tenant_id, task_id, result_type, effective_limit + 1, start),
            ).fetchall()
        visible = rows[:effective_limit]
        next_cursor = str(start + effective_limit) if len(rows) > effective_limit else None
        items = [json.loads(row["payload"]) for row in visible]
        return {
            "task_id": task_id,
            "assets": items if result_type == "assets" else [],
            "services": items if result_type == "services" else [],
            "source_evidence": items if result_type == "source_evidence" else [],
            "page": {"next_cursor": next_cursor, "limit": effective_limit, "type": result_type},
        }
```

```python
class SQLiteScopeProfileRepository:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)

    def save(self, profile: TenantScopeProfile) -> None:
        payload = profile.__dict__
        with _connect(self.db_path) as conn:
            conn.execute(
                """
                insert into scope_profiles (tenant_id, profile_id, status, payload, updated_at)
                values (?, ?, ?, ?, ?)
                on conflict(tenant_id, profile_id) do update set
                    status=excluded.status,
                    payload=excluded.payload,
                    updated_at=excluded.updated_at
                """,
                (
                    profile.tenant_id,
                    profile.profile_id,
                    profile.status,
                    json.dumps(payload, ensure_ascii=False),
                    _utcnow(),
                ),
            )

    def load_active(self, tenant_id: str, profile_id: str) -> TenantScopeProfile:
        with _connect(self.db_path) as conn:
            row = conn.execute(
                "select payload from scope_profiles where tenant_id=? and profile_id=?",
                (tenant_id, profile_id),
            ).fetchone()
        if row is None:
            raise FileNotFoundError(f"Scope profile not found: {tenant_id}/{profile_id}")
        profile = TenantScopeProfile(**json.loads(row["payload"]))
        if profile.status != "active":
            raise ValueError(f"Scope profile is not active: {profile_id}")
        return profile
```

```python
class SQLiteNonceRepository:
    def __init__(self, db_path: str | Path, window_seconds: int = 300) -> None:
        self.db_path = Path(db_path)
        self.window_seconds = window_seconds

    def remember_once(self, nonce: str, timestamp: datetime) -> bool:
        expires_at = timestamp.astimezone(timezone.utc) + timedelta(seconds=self.window_seconds)
        with _connect(self.db_path) as conn:
            conn.execute(
                "delete from nonces where expires_at < ?",
                (datetime.now(timezone.utc).isoformat(),),
            )
            try:
                conn.execute(
                    "insert into nonces (nonce, timestamp, expires_at) values (?, ?, ?)",
                    (nonce, timestamp.astimezone(timezone.utc).isoformat(), expires_at.isoformat()),
                )
            except sqlite3.IntegrityError:
                return False
        return True
```

```python
class SQLiteAuditRepository:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)

    def record_event(self, tenant_id: str, task_id: str, event_type: str, details: dict[str, Any]) -> None:
        with _connect(self.db_path) as conn:
            conn.execute(
                """
                insert into audit_events (tenant_id, task_id, event_type, details, created_at)
                values (?, ?, ?, ?, ?)
                """,
                (tenant_id, task_id, event_type, json.dumps(details, ensure_ascii=False), _utcnow()),
            )

    def list_events(self, tenant_id: str) -> list[dict[str, Any]]:
        with _connect(self.db_path) as conn:
            rows = conn.execute(
                "select tenant_id, task_id, event_type, details, created_at from audit_events where tenant_id=? order by id",
                (tenant_id,),
            ).fetchall()
        return [
            {
                "tenant_id": row["tenant_id"],
                "task_id": row["task_id"],
                "event_type": row["event_type"],
                "details": json.loads(row["details"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]
```

- [ ] **Step 4: Verify SQLite tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_sqlite_store.py -q
```

Expected: `5 passed`.

- [ ] **Step 5: Run repository regression tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_repositories.py tests\test_scope_profile_repository.py -q
```

Expected: existing file-backed repository behavior still passes.

- [ ] **Step 6: Commit**

Run:

```powershell
git add src/resource_discovery/sqlite_store.py src/resource_discovery/repositories.py tests/test_sqlite_store.py
git commit -m "feat: add sqlite gateway repositories"
```

## Task 3: HTTP Authentication Adapter

**Files:**
- Create: `src/resource_discovery/auth_http.py`
- Modify: `src/resource_discovery/request_auth.py`
- Test: `tests/test_auth_http.py`
- Create: `scripts/sign_request.py`

- [ ] **Step 1: Write failing auth adapter tests**

Create `tests/test_auth_http.py`:

```python
import json
from datetime import datetime, timezone

from resource_discovery.auth_http import FileClientSecretResolver, authenticate_http_request
from resource_discovery.request_auth import AuthError, InMemoryNonceStore, build_signature


def test_file_client_secret_resolver_loads_secret(tmp_path):
    path = tmp_path / "client-secrets.json"
    path.write_text(json.dumps({"tenant_a": {"toolbox": "secret-1"}}), encoding="utf-8")
    resolver = FileClientSecretResolver(path)
    assert resolver.resolve("tenant_a", "toolbox") == "secret-1"


def test_authenticate_http_request_accepts_valid_signature(tmp_path):
    path = tmp_path / "client-secrets.json"
    path.write_text(json.dumps({"tenant_a": {"toolbox": "secret-1"}}), encoding="utf-8")
    timestamp = "2026-05-22T10:00:00+00:00"
    body = b'{"profile_id":"profile_1"}'
    signature = build_signature(
        secret="secret-1",
        method="POST",
        path="/api/v1/discovery/tasks",
        timestamp=timestamp,
        nonce="nonce-1",
        body=body,
    )
    result = authenticate_http_request(
        method="POST",
        path="/api/v1/discovery/tasks",
        body=body,
        headers={
            "X-Tenant-Id": "tenant_a",
            "X-Client-Id": "toolbox",
            "X-Timestamp": timestamp,
            "X-Nonce": "nonce-1",
            "X-Signature": signature,
        },
        resolver=FileClientSecretResolver(path),
        nonce_store=InMemoryNonceStore(),
        now=datetime(2026, 5, 22, 10, 0, tzinfo=timezone.utc),
    )
    assert result == {"tenant_id": "tenant_a", "client_id": "toolbox"}


def test_authenticate_http_request_rejects_missing_header(tmp_path):
    path = tmp_path / "client-secrets.json"
    path.write_text(json.dumps({"tenant_a": {"toolbox": "secret-1"}}), encoding="utf-8")
    try:
        authenticate_http_request(
            method="GET",
            path="/api/v1/discovery/scope-profile",
            body=b"",
            headers={"X-Tenant-Id": "tenant_a"},
            resolver=FileClientSecretResolver(path),
            nonce_store=InMemoryNonceStore(),
            now=datetime(2026, 5, 22, 10, 0, tzinfo=timezone.utc),
        )
    except AuthError as exc:
        assert exc.code == "missing_auth_header"
    else:
        raise AssertionError("Expected missing auth header to be rejected")
```

- [ ] **Step 2: Run auth adapter tests and verify failure**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_auth_http.py -q
```

Expected: fails because `auth_http.py` does not exist.

- [ ] **Step 3: Implement auth adapter**

Create `src/resource_discovery/auth_http.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping, Protocol

from .request_auth import AuthError, NonceStore, verify_signature


class ClientSecretResolver(Protocol):
    def resolve(self, tenant_id: str, client_id: str) -> str:
        """Return the shared secret for a tenant/client pair."""


class FileClientSecretResolver:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def resolve(self, tenant_id: str, client_id: str) -> str:
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        try:
            return payload[tenant_id][client_id]
        except KeyError:
            raise AuthError("Unknown client credentials", code="unknown_client") from None


def authenticate_http_request(
    *,
    method: str,
    path: str,
    body: bytes,
    headers: Mapping[str, str],
    resolver: ClientSecretResolver,
    nonce_store: NonceStore,
    now,
    allowed_skew_seconds: int = 300,
) -> dict[str, str]:
    required = ["X-Tenant-Id", "X-Client-Id", "X-Timestamp", "X-Nonce", "X-Signature"]
    missing = [name for name in required if not headers.get(name)]
    if missing:
        raise AuthError("Missing authentication header", code="missing_auth_header")
    tenant_id = headers["X-Tenant-Id"]
    client_id = headers["X-Client-Id"]
    secret = resolver.resolve(tenant_id, client_id)
    verify_signature(
        secret=secret,
        method=method,
        path=path,
        timestamp=headers["X-Timestamp"],
        nonce=headers["X-Nonce"],
        body=body,
        signature=headers["X-Signature"],
        now=now,
        allowed_skew_seconds=allowed_skew_seconds,
        nonce_store=nonce_store,
    )
    return {"tenant_id": tenant_id, "client_id": client_id}
```

- [ ] **Step 4: Add signing helper script**

Create `scripts/sign_request.py`:

```python
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
```

- [ ] **Step 5: Verify auth tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_auth_http.py tests\test_request_auth.py -q
```

Expected: auth adapter and existing request auth tests pass.

- [ ] **Step 6: Commit**

Run:

```powershell
git add src/resource_discovery/auth_http.py src/resource_discovery/request_auth.py scripts/sign_request.py tests/test_auth_http.py
git commit -m "feat: add http request authentication adapter"
```

## Task 4: Queue Backends

**Files:**
- Create: `src/resource_discovery/queue_backends.py`
- Modify: `src/resource_discovery/task_queue.py`
- Test: `tests/test_queue_backends.py`

- [ ] **Step 1: Write failing queue backend tests**

Create `tests/test_queue_backends.py`:

```python
from resource_discovery.queue_backends import SQLiteTaskQueue, TaskQueueStatus
from resource_discovery.sqlite_store import initialize_sqlite
from resource_discovery.task_queue import TaskWorkItem


def test_sqlite_task_queue_dequeues_fifo(tmp_path):
    db_path = tmp_path / "gateway.sqlite3"
    initialize_sqlite(db_path)
    queue = SQLiteTaskQueue(db_path)
    queue.enqueue(TaskWorkItem("tenant_a", "task_1"))
    queue.enqueue(TaskWorkItem("tenant_a", "task_2"))
    assert queue.dequeue() == TaskWorkItem("tenant_a", "task_1")
    assert queue.dequeue() == TaskWorkItem("tenant_a", "task_2")
    assert queue.dequeue() is None


def test_sqlite_task_queue_records_attempts(tmp_path):
    db_path = tmp_path / "gateway.sqlite3"
    initialize_sqlite(db_path)
    queue = SQLiteTaskQueue(db_path)
    queue.enqueue(TaskWorkItem("tenant_a", "task_1"))
    item = queue.dequeue()
    assert item == TaskWorkItem("tenant_a", "task_1")
    queue.mark_retry(item, "provider_timeout")
    status = queue.status("tenant_a", "task_1")
    assert status == TaskQueueStatus(state="queued", attempts=1, last_error="provider_timeout")


def test_sqlite_task_queue_marks_done(tmp_path):
    db_path = tmp_path / "gateway.sqlite3"
    initialize_sqlite(db_path)
    queue = SQLiteTaskQueue(db_path)
    item = TaskWorkItem("tenant_a", "task_1")
    queue.enqueue(item)
    queue.dequeue()
    queue.mark_done(item)
    assert queue.status("tenant_a", "task_1").state == "done"
```

- [ ] **Step 2: Run queue tests and verify failure**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_queue_backends.py -q
```

Expected: fails because `queue_backends.py` does not exist.

- [ ] **Step 3: Add queue schema to SQLite initialization**

Modify `initialize_sqlite()` in `src/resource_discovery/sqlite_store.py` to include:

```sql
create table if not exists queue_jobs (
    tenant_id text not null,
    task_id text not null,
    state text not null,
    attempts integer not null,
    last_error text not null,
    available_at text not null,
    created_at text not null,
    updated_at text not null,
    primary key (tenant_id, task_id)
);
```

- [ ] **Step 4: Implement SQLite queue**

Create `src/resource_discovery/queue_backends.py`:

```python
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .sqlite_store import _connect, _utcnow
from .task_queue import TaskWorkItem


@dataclass(frozen=True)
class TaskQueueStatus:
    state: str
    attempts: int
    last_error: str


class SQLiteTaskQueue:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)

    def enqueue(self, item: TaskWorkItem) -> None:
        now = _utcnow()
        with _connect(self.db_path) as conn:
            conn.execute(
                """
                insert into queue_jobs (tenant_id, task_id, state, attempts, last_error, available_at, created_at, updated_at)
                values (?, ?, 'queued', 0, '', ?, ?, ?)
                on conflict(tenant_id, task_id) do update set
                    state='queued',
                    available_at=excluded.available_at,
                    updated_at=excluded.updated_at
                """,
                (item.tenant_id, item.task_id, now, now, now),
            )

    def dequeue(self) -> TaskWorkItem | None:
        with _connect(self.db_path) as conn:
            row = conn.execute(
                """
                select tenant_id, task_id from queue_jobs
                where state='queued'
                order by created_at
                limit 1
                """
            ).fetchone()
            if row is None:
                return None
            conn.execute(
                "update queue_jobs set state='running', updated_at=? where tenant_id=? and task_id=?",
                (_utcnow(), row["tenant_id"], row["task_id"]),
            )
        return TaskWorkItem(row["tenant_id"], row["task_id"])

    def mark_retry(self, item: TaskWorkItem, reason: str) -> None:
        with _connect(self.db_path) as conn:
            conn.execute(
                """
                update queue_jobs
                set state='queued', attempts=attempts + 1, last_error=?, updated_at=?
                where tenant_id=? and task_id=?
                """,
                (reason, _utcnow(), item.tenant_id, item.task_id),
            )

    def mark_done(self, item: TaskWorkItem) -> None:
        with _connect(self.db_path) as conn:
            conn.execute(
                "update queue_jobs set state='done', updated_at=? where tenant_id=? and task_id=?",
                (_utcnow(), item.tenant_id, item.task_id),
            )

    def mark_failed(self, item: TaskWorkItem, reason: str) -> None:
        with _connect(self.db_path) as conn:
            conn.execute(
                """
                update queue_jobs
                set state='failed', last_error=?, updated_at=?
                where tenant_id=? and task_id=?
                """,
                (reason, _utcnow(), item.tenant_id, item.task_id),
            )

    def status(self, tenant_id: str, task_id: str) -> TaskQueueStatus:
        with _connect(self.db_path) as conn:
            row = conn.execute(
                "select state, attempts, last_error from queue_jobs where tenant_id=? and task_id=?",
                (tenant_id, task_id),
            ).fetchone()
        if row is None:
            raise FileNotFoundError(f"Queue job not found: {tenant_id}/{task_id}")
        return TaskQueueStatus(state=row["state"], attempts=row["attempts"], last_error=row["last_error"])
```

- [ ] **Step 5: Add Redis queue adapter**

Append to `src/resource_discovery/queue_backends.py`:

```python
class RedisTaskQueue:
    def __init__(self, redis_url: str, queue_name: str = "resource_discovery:tasks") -> None:
        import redis

        self.client = redis.Redis.from_url(redis_url, decode_responses=True)
        self.queue_name = queue_name

    def enqueue(self, item: TaskWorkItem) -> None:
        self.client.rpush(self.queue_name, f"{item.tenant_id}:{item.task_id}")

    def dequeue(self) -> TaskWorkItem | None:
        value = self.client.lpop(self.queue_name)
        if value is None:
            return None
        tenant_id, task_id = value.split(":", 1)
        return TaskWorkItem(tenant_id, task_id)

    def mark_retry(self, item: TaskWorkItem, reason: str) -> None:
        self.enqueue(item)

    def mark_done(self, item: TaskWorkItem) -> None:
        return None

    def mark_failed(self, item: TaskWorkItem, reason: str) -> None:
        return None
```

- [ ] **Step 6: Verify queue tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_queue_backends.py tests\test_task_queue.py -q
```

Expected: SQLite queue and existing memory queue tests pass.

- [ ] **Step 7: Commit**

Run:

```powershell
git add src/resource_discovery/queue_backends.py src/resource_discovery/sqlite_store.py src/resource_discovery/task_queue.py tests/test_queue_backends.py
git commit -m "feat: add durable gateway queue backends"
```

## Task 5: FastAPI Application

**Files:**
- Create: `src/resource_discovery/http_app.py`
- Test: `tests/test_http_app.py`

- [ ] **Step 1: Write failing FastAPI tests**

Create `tests/test_http_app.py`:

```python
import json
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from resource_discovery.http_app import create_app
from resource_discovery.request_auth import build_signature


def _headers(secret, method, path, body=b"", nonce="nonce-1"):
    timestamp = "2026-05-22T10:00:00+00:00"
    return {
        "X-Tenant-Id": "tenant_poc",
        "X-Client-Id": "toolbox",
        "X-Timestamp": timestamp,
        "X-Nonce": nonce,
        "X-Signature": build_signature(
            secret=secret,
            method=method,
            path=path,
            timestamp=timestamp,
            nonce=nonce,
            body=body,
        ),
    }


def test_healthz_returns_ok(tmp_path):
    app = create_app(sqlite_path=tmp_path / "gateway.sqlite3", client_secrets={"tenant_poc": {"toolbox": "secret"}})
    client = TestClient(app)
    assert client.get("/healthz").json()["status"] == "ok"


def test_scope_profile_requires_signature(tmp_path):
    app = create_app(sqlite_path=tmp_path / "gateway.sqlite3", client_secrets={"tenant_poc": {"toolbox": "secret"}})
    client = TestClient(app)
    response = client.get("/api/v1/discovery/scope-profile")
    assert response.status_code == 401
    assert response.json()["errors"][0]["code"] == "missing_auth_header"


def test_scope_profile_with_valid_signature(tmp_path):
    path = "/api/v1/discovery/scope-profile"
    app = create_app(
        sqlite_path=tmp_path / "gateway.sqlite3",
        client_secrets={"tenant_poc": {"toolbox": "secret"}},
        now=lambda: datetime(2026, 5, 22, 10, 0, tzinfo=timezone.utc),
    )
    client = TestClient(app)
    response = client.get(path, headers=_headers("secret", "GET", path))
    assert response.status_code == 200
    assert response.json()["tenant_id"] == "tenant_poc"


def test_create_task_rejects_out_of_scope_request(tmp_path):
    path = "/api/v1/discovery/tasks"
    body = json.dumps(
        {
            "profile_id": "scope_profile_001",
            "requested_scope": {"root_domains": ["other.com"]},
            "engines": ["fofa"],
            "result_limit": 100,
            "purpose": "toolbox_asset_discovery",
        },
        separators=(",", ":"),
    ).encode("utf-8")
    app = create_app(
        sqlite_path=tmp_path / "gateway.sqlite3",
        client_secrets={"tenant_poc": {"toolbox": "secret"}},
        now=lambda: datetime(2026, 5, 22, 10, 0, tzinfo=timezone.utc),
    )
    client = TestClient(app)
    response = client.post(path, content=body, headers=_headers("secret", "POST", path, body))
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert response.json()["errors"][0]["code"] == "scope_out_of_bounds"
```

- [ ] **Step 2: Run FastAPI tests and verify failure**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_http_app.py -q
```

Expected: fails because `http_app.py` does not exist.

- [ ] **Step 3: Implement app factory**

Create `src/resource_discovery/http_app.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .auth_http import authenticate_http_request
from .gateway_api import DiscoveryGatewayApi
from .request_auth import AuthError, InMemoryNonceStore
from .scope_guard import TenantScopeProfile
from .sqlite_store import (
    SQLiteResultRepository,
    SQLiteTaskRepository,
    initialize_sqlite,
)
from .task_queue import InMemoryTaskQueue
from .uncover_client import FixtureSourceClient


def _default_profile() -> TenantScopeProfile:
    return TenantScopeProfile(
        tenant_id="tenant_poc",
        profile_id="scope_profile_001",
        status="active",
        root_domains=["example.com"],
        domains=["vpn.example.com"],
        ip_cidrs=["203.0.113.0/24"],
        org_names=["Example Limited"],
        allowed_engines=["fofa"],
        default_scope={"root_domains": ["example.com"]},
        limits={"max_results_per_task": 200, "max_queries_per_task": 10},
        authorization_note="Customer approval for integration fixture scope.",
    )
```

Continue with:

```python
class DictSecretResolver:
    def __init__(self, secrets: dict[str, dict[str, str]]) -> None:
        self.secrets = secrets

    def resolve(self, tenant_id: str, client_id: str) -> str:
        try:
            return self.secrets[tenant_id][client_id]
        except KeyError:
            raise AuthError("Unknown client credentials", code="unknown_client") from None
```

Finish with:

```python
def create_app(
    *,
    sqlite_path: str | Path,
    client_secrets: dict[str, dict[str, str]],
    now: Callable[[], datetime] | None = None,
) -> FastAPI:
    initialize_sqlite(sqlite_path)
    app = FastAPI(title="Resource Discovery Gateway", version="0.1.0")
    queue = InMemoryTaskQueue()
    profile = _default_profile()
    api = DiscoveryGatewayApi(
        profile=profile,
        source_client=FixtureSourceClient(Path("tests/fixtures/fofa_results.json")),
        task_repository=SQLiteTaskRepository(sqlite_path),
        result_repository=SQLiteResultRepository(sqlite_path),
        queue=queue,
    )
    resolver = DictSecretResolver(client_secrets)
    nonce_store = InMemoryNonceStore()
    clock = now or (lambda: datetime.now(timezone.utc))

    async def require_auth(request: Request) -> dict[str, str] | JSONResponse:
        body = await request.body()
        try:
            return authenticate_http_request(
                method=request.method,
                path=request.url.path,
                body=body,
                headers=request.headers,
                resolver=resolver,
                nonce_store=nonce_store,
                now=clock(),
            )
        except AuthError as exc:
            return JSONResponse(
                status_code=401,
                content={"status": "rejected", "errors": [{"code": exc.code, "message": str(exc), "recoverable": False, "details": {}}]},
            )

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok", "service": "resource-discovery-gateway"}

    @app.get("/readyz")
    def readyz() -> dict[str, str]:
        return {"status": "ok", "storage": "sqlite"}

    @app.get("/api/v1/discovery/scope-profile")
    async def get_scope_profile(request: Request) -> Any:
        auth = await require_auth(request)
        if isinstance(auth, JSONResponse):
            return auth
        return api.get_scope_profile()

    @app.post("/api/v1/discovery/tasks")
    async def create_task(request: Request) -> Any:
        auth = await require_auth(request)
        if isinstance(auth, JSONResponse):
            return auth
        return api.create_task(await request.json())

    @app.get("/api/v1/discovery/tasks/{task_id}")
    async def get_task(task_id: str, request: Request) -> Any:
        auth = await require_auth(request)
        if isinstance(auth, JSONResponse):
            return auth
        return api.get_task(task_id)

    @app.get("/api/v1/discovery/tasks/{task_id}/results")
    async def get_results(task_id: str, request: Request, cursor: str | None = None, limit: int = 100, result_type: str = "assets") -> Any:
        auth = await require_auth(request)
        if isinstance(auth, JSONResponse):
            return auth
        return api.get_results(task_id, cursor=cursor, limit=limit, result_type=result_type)

    return app


app = create_app(
    sqlite_path="artifacts/integration/resource-discovery.sqlite3",
    client_secrets={"tenant_poc": {"toolbox": "local-dev-secret"}},
)
```

- [ ] **Step 4: Verify FastAPI tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_http_app.py -q
```

Expected: FastAPI route tests pass.

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/resource_discovery/http_app.py tests/test_http_app.py
git commit -m "feat: expose discovery gateway over fastapi"
```

## Task 6: Worker Retry And CLI Entrypoint

**Files:**
- Modify: `src/resource_discovery/worker.py`
- Create: `src/resource_discovery/worker_cli.py`
- Test: `tests/test_worker_delivery.py`

- [ ] **Step 1: Write failing worker delivery tests**

Create `tests/test_worker_delivery.py`:

```python
from pathlib import Path

from resource_discovery.gateway_api import DiscoveryGatewayApi
from resource_discovery.queue_backends import SQLiteTaskQueue
from resource_discovery.scope_guard import TenantScopeProfile
from resource_discovery.sqlite_store import SQLiteResultRepository, SQLiteTaskRepository, initialize_sqlite
from resource_discovery.uncover_client import FixtureSourceClient
from resource_discovery.worker import TaskWorker


def _profile():
    return TenantScopeProfile(
        tenant_id="tenant_poc",
        profile_id="scope_profile_001",
        status="active",
        root_domains=["example.com"],
        domains=[],
        ip_cidrs=[],
        org_names=[],
        allowed_engines=["fofa"],
        default_scope={"root_domains": ["example.com"]},
        limits={"max_results_per_task": 100, "max_queries_per_task": 10},
        authorization_note="Customer approval for example.com.",
    )


def test_worker_persists_successful_results_with_sqlite_queue(tmp_path):
    db_path = tmp_path / "gateway.sqlite3"
    initialize_sqlite(db_path)
    task_repo = SQLiteTaskRepository(db_path)
    result_repo = SQLiteResultRepository(db_path)
    queue = SQLiteTaskQueue(db_path)
    source_client = FixtureSourceClient(Path("tests/fixtures/fofa_results.json"))
    api = DiscoveryGatewayApi(
        profile=_profile(),
        source_client=source_client,
        task_repository=task_repo,
        result_repository=result_repo,
        queue=queue,
    )
    created = api.create_task(
        {
            "profile_id": "scope_profile_001",
            "requested_scope": {"root_domains": ["example.com"]},
            "engines": ["fofa"],
            "result_limit": 20,
        }
    )
    worker = TaskWorker(task_repo, result_repo, queue, source_client)
    result = worker.run_once()
    assert result["status"] in {"success", "partial_success"}
    loaded = result_repo.load_results("tenant_poc", created["task_id"], None, 10, "assets")
    assert loaded["assets"]
```

- [ ] **Step 2: Run worker delivery tests and verify failure**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_worker_delivery.py -q
```

Expected: fails until `TaskWorker` supports the durable queue method surface.

- [ ] **Step 3: Update `TaskWorker` queue handling**

Modify `src/resource_discovery/worker.py` so `run_once()` calls optional queue finalizers:

```python
def _mark_queue_done(self, item) -> None:
    mark_done = getattr(self.queue, "mark_done", None)
    if mark_done is not None:
        mark_done(item)


def _mark_queue_failed(self, item, reason: str) -> None:
    mark_failed = getattr(self.queue, "mark_failed", None)
    if mark_failed is not None:
        mark_failed(item, reason)
```

Call `_mark_queue_done(item)` after successful result persistence and `_mark_queue_failed(item, str(exc))` after non-retry failure.

- [ ] **Step 4: Add worker CLI entrypoint**

Create `src/resource_discovery/worker_cli.py`:

```python
from __future__ import annotations

import argparse
from pathlib import Path

from .queue_backends import SQLiteTaskQueue
from .sqlite_store import SQLiteResultRepository, SQLiteTaskRepository, initialize_sqlite
from .uncover_client import FixtureSourceClient
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
```

- [ ] **Step 5: Verify worker tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_worker_delivery.py tests\test_worker.py -q
```

Expected: delivery worker and existing worker tests pass.

- [ ] **Step 6: Commit**

Run:

```powershell
git add src/resource_discovery/worker.py src/resource_discovery/worker_cli.py tests/test_worker_delivery.py
git commit -m "feat: add integration worker entrypoint"
```

## Task 7: Documentation And Handoff Package

**Files:**
- Modify: `README.md`
- Modify: `docs/resource-discovery/toolbox-api-contract.md`
- Modify: `docs/resource-discovery/toolbox-handoff.md`
- Modify: `docs/resource-discovery/production-readiness-checklist.md`

- [ ] **Step 1: Update API contract wording**

In `docs/resource-discovery/toolbox-api-contract.md`, replace PoC wording that says HTTP auth is not implemented with:

```markdown
FastAPI integration delivery implements HMAC-SHA256 request verification at the HTTP layer. Local examples use placeholder client secrets from `artifacts/integration/client-secrets.json`; production deployments must resolve client secrets from the customer-approved secret store.
```

- [ ] **Step 2: Add README startup commands**

Add this section to `README.md`:

```markdown
## 工具箱联调交付版

初始化本地 SQLite 状态：

```powershell
.\.venv\Scripts\python.exe -m resource_discovery.worker_cli --sqlite-path artifacts\integration\resource-discovery.sqlite3
```

启动 HTTP 服务：

```powershell
.\.venv\Scripts\python.exe -m uvicorn resource_discovery.http_app:app --host 127.0.0.1 --port 8000
```

生成签名：

```powershell
$timestamp = "2026-05-22T10:00:00+00:00"
$nonce = "nonce-demo-001"
$signature = .\.venv\Scripts\python.exe .\scripts\sign_request.py --secret local-dev-secret --method GET --path /api/v1/discovery/scope-profile --timestamp $timestamp --nonce $nonce
```

查询授权范围：

```powershell
curl.exe http://127.0.0.1:8000/api/v1/discovery/scope-profile `
  -H "X-Tenant-Id: tenant_poc" `
  -H "X-Client-Id: toolbox" `
  -H "X-Timestamp: $timestamp" `
  -H "X-Nonce: $nonce" `
  -H "X-Signature: $signature"
```
```

- [ ] **Step 3: Update handoff troubleshooting**

Add to `docs/resource-discovery/toolbox-handoff.md`:

```markdown
## FastAPI 联调排查

| 现象 | 检查项 |
| --- | --- |
| `missing_auth_header` | 五个签名请求头是否全部发送 |
| `invalid_signature` | 签名 path 是否只包含路径、不包含域名；body 字节是否与实际发送一致 |
| `replay_detected` | 每次请求必须使用新的 nonce |
| `scope_out_of_bounds` | 工具箱提交范围超过后台 scope profile |
| 状态一直 `queued` | worker 是否启动，队列 backend 是否和 API 使用同一 SQLite/Redis |
| 结果为空 | 任务是否进入 `success` 或 `partial_success`，`result_type` 是否正确 |
```

- [ ] **Step 4: Update production readiness checklist**

In `docs/resource-discovery/production-readiness-checklist.md`, mark FastAPI HTTP auth, SQLite integration storage, and Redis-capable queue as integration delivery state. Keep managed database, KMS, centralized audit, production Redis, and deployment automation as production requirements.

- [ ] **Step 5: Verify docs diff**

Run:

```powershell
git diff --check -- README.md docs/resource-discovery/toolbox-api-contract.md docs/resource-discovery/toolbox-handoff.md docs/resource-discovery/production-readiness-checklist.md
```

Expected: no whitespace errors.

- [ ] **Step 6: Commit**

Run:

```powershell
git add README.md docs/resource-discovery/toolbox-api-contract.md docs/resource-discovery/toolbox-handoff.md docs/resource-discovery/production-readiness-checklist.md
git commit -m "docs: add toolbox integration handoff package"
```

## Task 8: End-To-End Verification

**Files:**
- Read: all changed files

- [ ] **Step 1: Run focused integration tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_config.py tests\test_sqlite_store.py tests\test_auth_http.py tests\test_queue_backends.py tests\test_http_app.py tests\test_worker_delivery.py -q
```

Expected: all focused integration tests pass.

- [ ] **Step 2: Run full suite**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Expected: full suite passes.

- [ ] **Step 3: Run whitespace check**

Run:

```powershell
git diff --check
```

Expected: no whitespace errors.

- [ ] **Step 4: Run secret scan**

Run:

```powershell
rg "FOFA_API_KEY|local-dev-secret|secret-|token|api_key" . -g "!artifacts/**" -g "!*.pyc"
```

Expected: only placeholder secrets, local development examples, tests, and docs appear.

- [ ] **Step 5: Inspect final status**

Run:

```powershell
git status --short --branch
```

Expected: only intentional changes remain. If unrelated pre-existing worktree changes are still present, report them separately and do not stage them.

## Self-Review

- Spec coverage: Tasks cover FastAPI HTTP service, HMAC auth, SQLite repositories, nonce replay storage, Redis-capable queueing, worker execution, settings, handoff docs, curl signing helper, and verification.
- Placeholder scan: The plan contains concrete files, commands, expected outcomes, and code snippets for every implementation task. The only intentionally future-facing items are production caveats in documentation.
- Type consistency: Queue work uses existing `TaskWorkItem(tenant_id, task_id)`. Repository method names match existing protocols: `create`, `update`, `load`, `list`, `save_results`, and `load_results`.
- Scope check: This is a single large integration delivery. The tasks are independently committable and each produces a working layer that supports the same Toolbox handoff goal.
