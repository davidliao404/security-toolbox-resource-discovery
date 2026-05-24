# Production Operations Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the remaining production operations controls for the resource discovery gateway after the 2026-05-24 quality baseline.

**Architecture:** Keep the current FastAPI gateway, repository interfaces, PostgreSQL tables, Redis queue, and ops CLI boundaries. Add small focused modules for secret resolution, quota accounting, task operations, and audit retention so production behavior can be tested without changing the toolbox API contract.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy Core, PostgreSQL, Redis, pytest, coverage, Alembic, Docker Compose.

---

## File Structure

- `src/resource_discovery/auth_http.py`: keep public authentication entrypoint; wire in database-backed secret resolver.
- `src/resource_discovery/client_secrets.py`: create database-backed client secret resolver and rotation service.
- `src/resource_discovery/postgres_store.py`: add repositories for client secrets, rate-limit buckets, task operations, and retention policies.
- `src/resource_discovery/quota.py`: create tenant quota and provider rate-limit decision logic.
- `src/resource_discovery/task_operations.py`: create cancellation and dead-letter operation helpers.
- `src/resource_discovery/ops_cli.py`: expose admin commands for secret rotation, scope approval, quota inspection, task cancellation, dead-letter listing, audit search, and retention cleanup.
- `src/resource_discovery/http_app.py`: enforce quota before task creation and report structured quota errors.
- `src/resource_discovery/worker.py`: honor cancelled tasks before execution and emit quota, retry, and dead-letter audit events.
- `tests/test_client_secrets.py`: unit and integration coverage for resolver and rotation.
- `tests/test_quota.py`: quota and provider rate-limit accounting tests.
- `tests/test_task_operations.py`: cancellation and dead-letter behavior tests.
- `tests/test_ops_cli_production_ops.py`: ops CLI command tests.
- `tests/test_production_audit_retention.py`: audit search and tenant retention policy tests.
- `docs/resource-discovery/production-readiness-checklist.md`: mark completed controls only after tests pass.

## Task 1: Database-Backed Client Secret Resolution and Rotation

**Files:**
- Create: `src/resource_discovery/client_secrets.py`
- Modify: `src/resource_discovery/auth_http.py`
- Modify: `src/resource_discovery/postgres_store.py`
- Modify: `src/resource_discovery/ops_cli.py`
- Test: `tests/test_client_secrets.py`
- Test: `tests/test_ops_cli_production_ops.py`

- [ ] **Step 1: Write resolver tests**

Add this test file:

```python
from datetime import datetime, timezone

import pytest

from resource_discovery.client_secrets import ClientSecretRecord, ClientSecretRotationService, StaticSecretMaterialResolver
from resource_discovery.request_auth import AuthError


class MemoryClientSecretRepository:
    def __init__(self):
        self.records = {}
        self.audit = []

    def upsert(self, record):
        self.records[(record.tenant_id, record.client_id)] = record

    def load_active(self, tenant_id, client_id):
        record = self.records.get((tenant_id, client_id))
        if record is None or not record.active:
            raise AuthError("Unknown client credentials", code="unknown_client")
        return record

    def deactivate(self, tenant_id, client_id):
        record = self.records[(tenant_id, client_id)]
        self.records[(tenant_id, client_id)] = ClientSecretRecord(
            tenant_id=record.tenant_id,
            client_id=record.client_id,
            secret_ref=record.secret_ref,
            active=False,
            created_at=record.created_at,
            updated_at=datetime.now(timezone.utc),
        )


def test_rotation_service_resolves_active_secret_ref():
    repo = MemoryClientSecretRepository()
    material = StaticSecretMaterialResolver({"vault://tenant_a/toolbox/current": "secret-v2"})
    service = ClientSecretRotationService(repo, material)

    service.activate("tenant_a", "toolbox", "vault://tenant_a/toolbox/current")

    assert service.resolve("tenant_a", "toolbox") == "secret-v2"


def test_rotation_service_rejects_inactive_secret():
    repo = MemoryClientSecretRepository()
    material = StaticSecretMaterialResolver({"vault://tenant_a/toolbox/current": "secret-v2"})
    service = ClientSecretRotationService(repo, material)

    service.activate("tenant_a", "toolbox", "vault://tenant_a/toolbox/current")
    repo.deactivate("tenant_a", "toolbox")

    with pytest.raises(AuthError) as exc:
        service.resolve("tenant_a", "toolbox")
    assert exc.value.code == "unknown_client"
```

- [ ] **Step 2: Run resolver tests and verify failure**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_client_secrets.py -q`

Expected: fails because `resource_discovery.client_secrets` does not exist.

- [ ] **Step 3: Implement client secret module**

Create `src/resource_discovery/client_secrets.py` with:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from .request_auth import AuthError


@dataclass(frozen=True)
class ClientSecretRecord:
    tenant_id: str
    client_id: str
    secret_ref: str
    active: bool
    created_at: datetime
    updated_at: datetime


class ClientSecretRepository(Protocol):
    def upsert(self, record: ClientSecretRecord) -> None:
        """Create or replace the active secret reference."""

    def load_active(self, tenant_id: str, client_id: str) -> ClientSecretRecord:
        """Load the active secret reference for a tenant/client pair."""


class SecretMaterialResolver(Protocol):
    def resolve_material(self, secret_ref: str) -> str:
        """Resolve the secret material behind a reference."""


class StaticSecretMaterialResolver:
    def __init__(self, material_by_ref: dict[str, str]) -> None:
        self.material_by_ref = material_by_ref

    def resolve_material(self, secret_ref: str) -> str:
        try:
            return self.material_by_ref[secret_ref]
        except KeyError:
            raise AuthError("Unknown client credentials", code="unknown_client") from None


class ClientSecretRotationService:
    def __init__(self, repository: ClientSecretRepository, material_resolver: SecretMaterialResolver) -> None:
        self.repository = repository
        self.material_resolver = material_resolver

    def activate(self, tenant_id: str, client_id: str, secret_ref: str) -> None:
        now = datetime.now(timezone.utc)
        self.repository.upsert(
            ClientSecretRecord(
                tenant_id=tenant_id,
                client_id=client_id,
                secret_ref=secret_ref,
                active=True,
                created_at=now,
                updated_at=now,
            )
        )

    def resolve(self, tenant_id: str, client_id: str) -> str:
        record = self.repository.load_active(tenant_id, client_id)
        if not record.active:
            raise AuthError("Unknown client credentials", code="unknown_client")
        return self.material_resolver.resolve_material(record.secret_ref)
```

- [ ] **Step 4: Add PostgreSQL repository**

In `src/resource_discovery/postgres_store.py`, import `client_secrets` from `db.py` and `ClientSecretRecord`. Add `PostgresClientSecretRepository` with `upsert()` using `pg_insert(...).on_conflict_do_update(...)` on `(tenant_id, client_id)` and `load_active()` filtering `active == True`. Raise `AuthError(..., code="unknown_client")` when no row exists.

- [ ] **Step 5: Wire admin CLI**

In `src/resource_discovery/ops_cli.py`, add `rotate-client-secret` accepting `--tenant-id`, `--client-id`, and `--secret-ref`. The command stores only `secret_ref`; it must not print or accept raw secret material.

- [ ] **Step 6: Run focused tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_client_secrets.py tests/test_ops_cli_production_ops.py -q`

Expected: all focused tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/resource_discovery/client_secrets.py src/resource_discovery/auth_http.py src/resource_discovery/postgres_store.py src/resource_discovery/ops_cli.py tests/test_client_secrets.py tests/test_ops_cli_production_ops.py
git commit -m "feat: add production client secret rotation"
```

## Task 2: Scope Profile Administration and Approval Records

**Files:**
- Modify: `src/resource_discovery/postgres_store.py`
- Modify: `src/resource_discovery/ops_cli.py`
- Test: `tests/test_scope_profile_repository.py`
- Test: `tests/test_ops_cli_production_ops.py`

- [ ] **Step 1: Add approval tests**

Add tests that seed a scope profile payload with:

```python
payload["approval"] = {
    "approved_by": "security-admin",
    "approved_at": "2026-05-24T10:00:00+08:00",
    "ticket_id": "SEC-2026-0524",
}
```

Assert `load_active("tenant_poc", "scope_profile_001")` preserves the `approval` field in the profile payload returned to repositories and that inactive profiles are still rejected.

- [ ] **Step 2: Run approval tests and verify failure**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_scope_profile_repository.py tests/test_ops_cli_production_ops.py -q`

Expected: fails until the repository and CLI preserve and require approval metadata.

- [ ] **Step 3: Add CLI command**

In `src/resource_discovery/ops_cli.py`, add `approve-scope-profile` accepting `--tenant-id`, `--profile-id`, `--profile-file`, `--approved-by`, and `--ticket-id`. The command loads JSON, sets `status` to `active`, writes the approval object, and calls the existing scope profile repository.

- [ ] **Step 4: Add audit event**

When approving a profile, write audit event `scope_profile_approved` with `tenant_id`, `profile_id`, `approved_by`, and `ticket_id`. Do not include the full allowed scope payload in the audit details.

- [ ] **Step 5: Run focused tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_scope_profile_repository.py tests/test_ops_cli_production_ops.py -q`

Expected: all focused tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/resource_discovery/postgres_store.py src/resource_discovery/ops_cli.py tests/test_scope_profile_repository.py tests/test_ops_cli_production_ops.py
git commit -m "feat: require approval metadata for scope profiles"
```

## Task 3: Tenant Quota and Provider Rate Limits

**Files:**
- Create: `src/resource_discovery/quota.py`
- Modify: `src/resource_discovery/postgres_store.py`
- Modify: `src/resource_discovery/http_app.py`
- Modify: `src/resource_discovery/errors.py`
- Test: `tests/test_quota.py`
- Test: `tests/test_http_app.py`

- [ ] **Step 1: Write quota tests**

Create `tests/test_quota.py` with tests for three cases:

```python
from datetime import datetime, timezone

import pytest

from resource_discovery.quota import QuotaDecision, QuotaExceeded, TenantQuotaPolicy, check_task_quota


def test_task_quota_allows_under_daily_limit():
    decision = check_task_quota(
        tenant_id="tenant_a",
        policy=TenantQuotaPolicy(max_tasks_per_day=10, max_provider_queries_per_day=100, max_concurrent_tasks=2),
        current_daily_tasks=3,
        current_daily_provider_queries=12,
        current_running_tasks=1,
        planned_provider_queries=5,
        now=datetime.now(timezone.utc),
    )
    assert decision == QuotaDecision(allowed=True, code="")


def test_task_quota_rejects_daily_task_limit():
    with pytest.raises(QuotaExceeded) as exc:
        check_task_quota(
            tenant_id="tenant_a",
            policy=TenantQuotaPolicy(max_tasks_per_day=3, max_provider_queries_per_day=100, max_concurrent_tasks=2),
            current_daily_tasks=3,
            current_daily_provider_queries=12,
            current_running_tasks=1,
            planned_provider_queries=5,
            now=datetime.now(timezone.utc),
        )
    assert exc.value.code == "tenant_daily_task_quota_exceeded"


def test_task_quota_rejects_provider_query_limit():
    with pytest.raises(QuotaExceeded) as exc:
        check_task_quota(
            tenant_id="tenant_a",
            policy=TenantQuotaPolicy(max_tasks_per_day=10, max_provider_queries_per_day=15, max_concurrent_tasks=2),
            current_daily_tasks=3,
            current_daily_provider_queries=12,
            current_running_tasks=1,
            planned_provider_queries=5,
            now=datetime.now(timezone.utc),
        )
    assert exc.value.code == "provider_daily_query_quota_exceeded"
```

- [ ] **Step 2: Run quota tests and verify failure**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_quota.py -q`

Expected: fails because `resource_discovery.quota` does not exist.

- [ ] **Step 3: Implement quota module**

Create `src/resource_discovery/quota.py` with dataclasses `TenantQuotaPolicy`, `QuotaDecision`, exception `QuotaExceeded`, and function `check_task_quota(...)`. Return allowed decisions for under-limit requests and raise `QuotaExceeded` with exact codes from the tests.

- [ ] **Step 4: Enforce quota in HTTP task creation**

In `src/resource_discovery/http_app.py`, call the quota repository before `gateway_api.create_task(...)`. On `QuotaExceeded`, return the existing structured error model with HTTP 429 and code from the exception.

- [ ] **Step 5: Add bucket repository**

In `src/resource_discovery/postgres_store.py`, add repository methods backed by `rate_limit_buckets` for reading and incrementing `tenant:{tenant_id}:tasks:day` and `provider:fofa:queries:day` buckets. Use the table unique constraint to make increments atomic.

- [ ] **Step 6: Run focused tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_quota.py tests/test_http_app.py tests/test_postgres_store.py -q`

Expected: all focused tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/resource_discovery/quota.py src/resource_discovery/postgres_store.py src/resource_discovery/http_app.py src/resource_discovery/errors.py tests/test_quota.py tests/test_http_app.py tests/test_postgres_store.py
git commit -m "feat: enforce tenant quota and provider limits"
```

## Task 4: Task Cancellation and Dead-Letter Operations

**Files:**
- Create: `src/resource_discovery/task_operations.py`
- Modify: `src/resource_discovery/worker.py`
- Modify: `src/resource_discovery/redis_queue.py`
- Modify: `src/resource_discovery/ops_cli.py`
- Test: `tests/test_task_operations.py`
- Test: `tests/test_worker_retry.py`
- Test: `tests/test_redis_queue.py`

- [ ] **Step 1: Write operation tests**

Create `tests/test_task_operations.py` to assert:

- cancelling a `queued`, `retrying`, or `running` task moves status to `cancelled`;
- cancelling `success`, `partial_success`, `failed`, or `cancelled` returns a structured non-retryable error;
- listing dead letters returns `tenant_id`, `task_id`, `attempts`, `last_error`, and `updated_at`.

- [ ] **Step 2: Run operation tests and verify failure**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_task_operations.py -q`

Expected: fails because `resource_discovery.task_operations` does not exist.

- [ ] **Step 3: Implement cancellation helper**

Create `src/resource_discovery/task_operations.py` with `cancel_task(task_repository, tenant_id, task_id, actor)` and `list_dead_letters(queue)`. The cancel function must load the task, check terminal states, update `task["status"] = "cancelled"`, set `task["cancelled_by"]`, set `task["cancelled_at"]`, and persist the task.

- [ ] **Step 4: Make worker honor cancelled tasks**

In `src/resource_discovery/worker.py`, reload the task before provider execution. If status is `cancelled`, skip provider calls, acknowledge queue work, and audit `task_cancelled_before_execution`.

- [ ] **Step 5: Add ops commands**

In `src/resource_discovery/ops_cli.py`, add `cancel-task --tenant-id --task-id --actor` and `list-dead-letters`. The dead-letter command prints JSON lines with one dead-letter object per line.

- [ ] **Step 6: Run focused tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_task_operations.py tests/test_worker_retry.py tests/test_redis_queue.py tests/test_ops_cli_production_ops.py -q`

Expected: all focused tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/resource_discovery/task_operations.py src/resource_discovery/worker.py src/resource_discovery/redis_queue.py src/resource_discovery/ops_cli.py tests/test_task_operations.py tests/test_worker_retry.py tests/test_redis_queue.py tests/test_ops_cli_production_ops.py
git commit -m "feat: add task cancellation and dead letter operations"
```

## Task 5: Audit Search, Metrics, and Retention Operations

**Files:**
- Modify: `src/resource_discovery/postgres_store.py`
- Modify: `src/resource_discovery/metrics.py`
- Modify: `src/resource_discovery/ops_cli.py`
- Test: `tests/test_production_audit_retention.py`
- Test: `tests/test_observability.py`

- [ ] **Step 1: Write audit and retention tests**

Create tests that insert audit events for two tenants, query only one tenant with an event type filter, and assert the result excludes other tenants. Add retention tests that delete expired task results and nonces while preserving audit events newer than the tenant policy.

- [ ] **Step 2: Run tests and verify failure**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_production_audit_retention.py -q`

Expected: fails until repository search and retention methods exist.

- [ ] **Step 3: Add repository methods**

In `src/resource_discovery/postgres_store.py`, add:

- `search_audit_events(tenant_id, event_type=None, task_id=None, limit=100)`
- `load_retention_policy(tenant_id)`
- `cleanup_expired_rows(tenant_id, now)`

All methods must scope by `tenant_id`.

- [ ] **Step 4: Add ops commands**

In `src/resource_discovery/ops_cli.py`, add `search-audit` and `cleanup-retention --tenant-id`. The audit command prints compact JSON lines and never prints authentication headers, signatures, or secret refs.

- [ ] **Step 5: Extend metrics**

In `src/resource_discovery/metrics.py`, add counters for `tasks_created_total`, `tasks_completed_total`, `provider_errors_total`, `dead_letters_total`, and `quota_rejections_total`. Update existing instrumentation in `http_app.py` and `worker.py` to increment them with bounded label values.

- [ ] **Step 6: Run focused tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_production_audit_retention.py tests/test_observability.py tests/test_ops_cli_production_ops.py -q`

Expected: all focused tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/resource_discovery/postgres_store.py src/resource_discovery/metrics.py src/resource_discovery/ops_cli.py src/resource_discovery/http_app.py src/resource_discovery/worker.py tests/test_production_audit_retention.py tests/test_observability.py tests/test_ops_cli_production_ops.py
git commit -m "feat: add production audit retention operations"
```

## Task 6: Controlled Live FOFA Regression

**Files:**
- Modify: `src/resource_discovery/live_validation.py`
- Modify: `src/resource_discovery/ops_cli.py`
- Create: `tests/test_live_fofa_regression.py`
- Modify: `docs/resource-discovery/production-readiness-checklist.md`

- [ ] **Step 1: Write env-gated tests**

Create tests that assert live regression refuses to run unless all of these are present:

- `RESOURCE_DISCOVERY_LIVE_FOFA=1`
- `FOFA_EMAIL`
- `FOFA_KEY`
- `RESOURCE_DISCOVERY_LIVE_AUTHORIZED_DOMAIN`

Also assert logs and returned summaries do not include `FOFA_KEY`.

- [ ] **Step 2: Run tests and verify failure**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_live_fofa_regression.py -q`

Expected: fails until the guard is implemented.

- [ ] **Step 3: Implement guarded runner**

In `src/resource_discovery/live_validation.py`, add `run_live_fofa_regression(authorized_domain, result_limit=10)`. It must build a single passive FOFA query for the authorized domain, use existing FOFA client error mapping, redact credentials from all returned structures, and return only counts plus normalized sample IDs.

- [ ] **Step 4: Add ops command**

In `src/resource_discovery/ops_cli.py`, add `live-fofa-regression`. The command exits nonzero with a clear message if the env gate is missing. It must not accept FOFA credentials as CLI arguments.

- [ ] **Step 5: Run guarded local tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_live_fofa_regression.py tests/test_live_validation.py -q`

Expected: all focused tests pass without real FOFA credentials.

- [ ] **Step 6: Run optional live regression only in an authorized environment**

Run from WSL or Windows with explicit authorization:

```bash
RESOURCE_DISCOVERY_LIVE_FOFA=1 FOFA_EMAIL="$FOFA_EMAIL" FOFA_KEY="$FOFA_KEY" RESOURCE_DISCOVERY_LIVE_AUTHORIZED_DOMAIN="example.com" python -m resource_discovery.ops_cli live-fofa-regression
```

Expected: returns a redacted JSON summary. If credentials or authorization are unavailable, record `not run` in the checklist instead of fabricating a result.

- [ ] **Step 7: Commit**

```bash
git add src/resource_discovery/live_validation.py src/resource_discovery/ops_cli.py tests/test_live_fofa_regression.py docs/resource-discovery/production-readiness-checklist.md
git commit -m "test: add guarded live fofa regression"
```

## Final Verification

- [ ] Run full Windows suite: `.\.venv\Scripts\python.exe -m pytest -q`
- [ ] Run coverage gate: `.\.venv\Scripts\python.exe -m coverage run -m pytest -q && .\.venv\Scripts\python.exe -m coverage report`
- [ ] Run WSL PostgreSQL/Redis suite: `RESOURCE_DISCOVERY_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/resource_discovery RESOURCE_DISCOVERY_TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/resource_discovery RESOURCE_DISCOVERY_TEST_REDIS_URL=redis://localhost:6379/0 python -m pytest -q`
- [ ] Run whitespace check: `git diff --check`
- [ ] Confirm GitHub Actions `CI` and `production-like-gateway` are green after push.
