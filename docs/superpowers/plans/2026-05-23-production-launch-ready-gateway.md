# Production Launch Ready Gateway Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the current resource discovery gateway from "Toolbox integration delivery" to a production-launch-ready gateway while freezing the current API contract and requiring the external Toolbox team to adapt to it.

**Architecture:** Keep the existing FastAPI API contract, HMAC request signing, scope guard, async task model, and result pagination semantics. Replace integration-only infrastructure with production-grade adapters: PostgreSQL for durable task/result/scope/audit/nonce state, Redis for queue/retry/dead-letter coordination, Docker Compose for local production-like validation inside WSL, and explicit operations commands for migrations, seeding, config checks, smoke tests, and retention cleanup.

**Tech Stack:** Windows host + WSL Ubuntu 24.04, Docker Engine + Docker Compose plugin inside WSL, Python 3.12, FastAPI, uvicorn, pytest, PostgreSQL 16, Redis 7, SQLAlchemy Core, Alembic, psycopg, prometheus-client, structlog.

## Goal Command For Next Agent

```text
Execute docs/superpowers/plans/2026-05-23-production-launch-ready-gateway.md task by task. API contract is frozen; external Toolbox team must adapt to docs/resource-discovery/toolbox-api-contract.md. Build and verify all missing infrastructure locally inside WSL, including Docker Engine, Docker Compose, PostgreSQL, Redis, migrations, API, worker, and smoke tests. Do not stop because Docker/PostgreSQL/Redis are missing on Windows; install and validate them in WSL.
```

## Contract Policy

- Gateway team owns the API contract and freezes the current endpoint, auth, pagination, task-state, error-code, and payload semantics.
- External Toolbox team adapts to `docs/resource-discovery/toolbox-api-contract.md`, `docs/resource-discovery/toolbox-handoff.md`, and the examples shipped in this repository.
- Joint integration validates implementation compatibility against the frozen contract. It is not a contract redesign session.
- Feedback from the external team may produce documentation clarifications, sample fixes, or gateway bug fixes. Contract changes require explicit gateway-owner approval and a versioned migration note.
- Production launch readiness is judged by this repository's automated tests, WSL production-like compose smoke test, migration verification, and handoff checklist.

## File Structure

Create or update these files:

```text
docs/resource-discovery/toolbox-integration-rules.md
docs/resource-discovery/toolbox-api-contract.md
docs/resource-discovery/toolbox-handoff.md
docs/resource-discovery/production-readiness-checklist.md
README.md
pyproject.toml
alembic.ini
migrations/env.py
migrations/versions/0001_gateway_schema.py
src/resource_discovery/config.py
src/resource_discovery/db.py
src/resource_discovery/postgres_store.py
src/resource_discovery/redis_queue.py
src/resource_discovery/backend_factory.py
src/resource_discovery/http_app.py
src/resource_discovery/worker.py
src/resource_discovery/worker_cli.py
src/resource_discovery/ops_cli.py
src/resource_discovery/logging_config.py
src/resource_discovery/metrics.py
docker-compose.prodlike.yml
Dockerfile
scripts/wsl_bootstrap.ps1
scripts/wsl_bootstrap.sh
scripts/prodlike_smoke_test.py
tests/test_config.py
tests/test_postgres_store.py
tests/test_redis_queue.py
tests/test_ops_cli.py
tests/test_prodlike_contract.py
tests/test_backend_factory.py
tests/test_observability.py
tests/test_worker_retry.py
tests/test_tenant_isolation.py
.github/workflows/prodlike.yml
```

## Tasks

### Task 0: Establish Baseline

- [ ] Run `git status --short --branch` and confirm the starting branch and local changes.
- [ ] Run the current Windows test suite with `pytest` and record the exact result in `docs/resource-discovery/production-readiness-checklist.md`.
- [ ] Add a readiness section named `Production Launch Upgrade Baseline` with the current commit SHA, date `2026-05-23`, and current verification output.
- [ ] Commit with message `docs: record production launch baseline`.

### Task 1: Build Local WSL Production-Like Environment

- [ ] Add `scripts/wsl_bootstrap.ps1` for Windows host orchestration. It checks for WSL, installs or selects Ubuntu 24.04, copies the repository path into WSL-compatible form, and invokes `scripts/wsl_bootstrap.sh`.
- [ ] Add `scripts/wsl_bootstrap.sh` for Ubuntu setup. It installs Docker Engine, Docker Compose plugin, Python 3.12 tooling, PostgreSQL client, Redis tools, and project test dependencies.
- [ ] The shell script verifies `docker --version`, `docker compose version`, `python3.12 --version`, and `pytest`.
- [ ] Document WSL usage in `README.md`, including the command `powershell -ExecutionPolicy Bypass -File scripts/wsl_bootstrap.ps1`.
- [ ] Run the bootstrap from Windows and capture successful command output in the readiness checklist.
- [ ] Commit with message `ops: add WSL production validation bootstrap`.

### Task 2: Freeze External Toolbox Integration Rules

- [ ] Add `docs/resource-discovery/toolbox-integration-rules.md` describing interface ownership, frozen API surface, external-team responsibilities, allowed feedback categories, and launch acceptance gates.
- [ ] Update `docs/resource-discovery/toolbox-handoff.md` to link the rules and clearly state that the Toolbox implementation must adapt to the gateway API.
- [ ] Update `README.md` with a short `External Toolbox Contract` section pointing to the contract, handoff, and rules docs.
- [ ] Commit with message `docs: freeze toolbox integration rules`.

### Task 3: Add Production Configuration and Dependencies

- [ ] Add tests in `tests/test_config.py` for `storage_backend`, `database_url`, `redis_url`, `worker_max_attempts`, `worker_retry_delay_seconds`, `dead_letter_enabled`, `metrics_enabled`, and `log_format`.
- [ ] Update `pyproject.toml` dependencies for `SQLAlchemy`, `alembic`, `psycopg[binary]`, `redis`, `prometheus-client`, and `structlog`.
- [ ] Extend `GatewaySettings` in `src/resource_discovery/config.py` with typed production settings and environment-variable parsing.
- [ ] Keep SQLite settings valid for local unit tests and mark PostgreSQL/Redis as selectable production backends.
- [ ] Run `pytest tests/test_config.py`.
- [ ] Commit with message `feat: add production gateway settings`.

### Task 4: Add PostgreSQL Schema and Repository Adapter

- [ ] Add `src/resource_discovery/db.py` with SQLAlchemy metadata for `tasks`, `task_results`, `scope_profiles`, `request_nonces`, `audit_events`, `queue_jobs`, `client_secrets`, `retention_policies`, and `rate_limit_buckets`.
- [ ] Add `alembic.ini`, `migrations/env.py`, and `migrations/versions/0001_gateway_schema.py` using the metadata from `db.py`.
- [ ] Add indexes for client ID, tenant ID, task state, creation time, nonce expiry, and result pagination.
- [ ] Add `src/resource_discovery/postgres_store.py` implementing durable task, result, scope, nonce, audit, and client-secret repository operations.
- [ ] Add `tests/test_postgres_store.py`. The tests run when `RESOURCE_DISCOVERY_TEST_DATABASE_URL` is set and skip with a clear reason when it is absent.
- [ ] In WSL, start PostgreSQL with `docker run --rm -d --name rd-postgres -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=resource_discovery -p 5432:5432 postgres:16`.
- [ ] Run `alembic upgrade head` against the test database.
- [ ] Run `pytest tests/test_postgres_store.py` with `RESOURCE_DISCOVERY_TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/resource_discovery`.
- [ ] Commit with message `feat: add postgres storage backend`.

### Task 5: Add Redis Queue, Retry, and Dead-Letter Handling

- [ ] Add `src/resource_discovery/redis_queue.py` with enqueue, dequeue, acknowledge, retry, fail, dead-letter listing, and queue-depth operations.
- [ ] Update worker processing so every job records attempt count, last error, next visible time, and terminal failure state.
- [ ] Add `tests/test_redis_queue.py` for FIFO behavior, visibility timeout, retry scheduling, dead-letter routing, and idempotent acknowledgement.
- [ ] Add `tests/test_worker_retry.py` for worker retry decisions and terminal failure behavior.
- [ ] In WSL, start Redis with `docker run --rm -d --name rd-redis -p 6379:6379 redis:7`.
- [ ] Run `pytest tests/test_redis_queue.py tests/test_worker_retry.py` with `RESOURCE_DISCOVERY_TEST_REDIS_URL=redis://localhost:6379/0`.
- [ ] Commit with message `feat: add redis queue backend`.

### Task 6: Wire Backend Factories into API and Worker

- [ ] Add `src/resource_discovery/backend_factory.py` with a `RepositoryBundle` and `build_repositories(settings)` / `build_queue(settings)` functions.
- [ ] Update `src/resource_discovery/http_app.py` so application startup selects SQLite or PostgreSQL repositories based on settings.
- [ ] Update `src/resource_discovery/worker_cli.py` so worker startup selects SQLite, PostgreSQL, or Redis queue settings consistently.
- [ ] Add `tests/test_backend_factory.py` for backend selection, missing URL failures, and SQLite compatibility.
- [ ] Run `pytest tests/test_backend_factory.py tests/test_prodlike_contract.py`.
- [ ] Commit with message `feat: wire production backend factories`.

### Task 7: Add Operations CLI

- [ ] Add `src/resource_discovery/ops_cli.py` with commands `verify-config`, `migrate`, `seed-scope-profile`, `smoke-test`, and `cleanup-retention`.
- [ ] `verify-config` checks required backend URLs, secrets file readability, HMAC settings, and worker retry settings.
- [ ] `migrate` runs Alembic migrations for PostgreSQL.
- [ ] `seed-scope-profile` creates or updates a tenant/client scope profile from JSON input.
- [ ] `smoke-test` sends signed API requests and confirms task submission, task completion polling, and result pagination.
- [ ] `cleanup-retention` removes expired nonces, stale audit records, and expired task/result rows based on configured retention policy.
- [ ] Add `tests/test_ops_cli.py` covering command parsing and repository effects.
- [ ] Document CLI examples in `README.md`.
- [ ] Run `pytest tests/test_ops_cli.py`.
- [ ] Commit with message `feat: add gateway operations CLI`.

### Task 8: Add Observability and Request Tracing

- [ ] Add `src/resource_discovery/logging_config.py` for structured JSON logs in production mode and readable logs in local mode.
- [ ] Add `src/resource_discovery/metrics.py` with counters and histograms for requests, auth failures, task submissions, worker completions, worker failures, queue depth, and storage errors.
- [ ] Add `/metrics` when `metrics_enabled=true`.
- [ ] Ensure every API response includes `X-Request-Id`, preserving an inbound request ID when supplied.
- [ ] Update worker logs to include task ID, tenant ID, client ID, queue attempt, and final state.
- [ ] Add `tests/test_observability.py` for request ID, metrics route, and structured log field presence.
- [ ] Run `pytest tests/test_observability.py`.
- [ ] Commit with message `feat: add gateway observability`.

### Task 9: Add Production-Like Docker Compose Stack

- [ ] Add `docker-compose.prodlike.yml` with services `postgres`, `redis`, `migrate`, `api`, and `worker`.
- [ ] Use PostgreSQL 16 and Redis 7 official images with health checks.
- [ ] Configure API and worker with PostgreSQL storage, Redis queue, config-file client secrets, metrics enabled, and JSON logs.
- [ ] Ensure the `migrate` service runs before API and worker become healthy.
- [ ] Add `scripts/prodlike_smoke_test.py` that creates signed requests for a representative discovery query, polls task completion, retrieves paginated results, and prints a JSON summary.
- [ ] In WSL, run `docker compose -f docker-compose.prodlike.yml config`.
- [ ] In WSL, run `docker compose -f docker-compose.prodlike.yml up -d --build`.
- [ ] In WSL, run `python scripts/prodlike_smoke_test.py --base-url http://localhost:8000 --client-id toolbox-dev --secret <configured-secret>`.
- [ ] Confirm the smoke output contains a completed task and `asset_count > 0`.
- [ ] In WSL, run `docker compose -f docker-compose.prodlike.yml logs --tail=100 api worker migrate` and confirm no stack traces.
- [ ] In WSL, run `docker compose -f docker-compose.prodlike.yml down -v`.
- [ ] Record commands and outputs in the readiness checklist.
- [ ] Commit with message `ops: add production-like compose validation`.

### Task 10: Add CI Production-Like Verification

- [ ] Add `.github/workflows/prodlike.yml` with PostgreSQL and Redis service containers.
- [ ] The workflow installs project dependencies, runs Alembic migrations, runs unit tests, and runs PostgreSQL/Redis integration tests with service URLs.
- [ ] Include a separate job or step for `docker compose -f docker-compose.prodlike.yml config`.
- [ ] Document the CI workflow in the readiness checklist.
- [ ] Commit with message `ci: add production-like gateway verification`.

### Task 11: Add Tenant Isolation and Retention Controls

- [ ] Add `tests/test_tenant_isolation.py` proving one tenant/client cannot read another tenant's tasks or results.
- [ ] Ensure PostgreSQL queries include tenant/client predicates for task reads, result pagination, and audit reads.
- [ ] Add retention-policy defaults for nonces, task records, task results, and audit events.
- [ ] Add tests proving `cleanup-retention` removes expired rows and keeps active rows.
- [ ] Run `pytest tests/test_tenant_isolation.py tests/test_ops_cli.py`.
- [ ] Commit with message `feat: enforce tenant isolation and retention`.

### Task 12: Final Launch Verification

- [ ] Run Windows `pytest` and record the exact result.
- [ ] Run WSL `pytest` and record the exact result.
- [ ] Run WSL PostgreSQL integration tests with `RESOURCE_DISCOVERY_TEST_DATABASE_URL` and record the exact result.
- [ ] Run WSL Redis integration tests with `RESOURCE_DISCOVERY_TEST_REDIS_URL` and record the exact result.
- [ ] Run WSL production-like Docker Compose smoke test and record the exact JSON summary.
- [ ] Run `git diff --check`.
- [ ] Run the repository unfinished-work marker scan described in the self-review checklist across `docs`, `src`, `tests`, `scripts`, `.github`, `README.md`, and `pyproject.toml`; resolve every match that indicates incomplete delivery.
- [ ] Update `docs/resource-discovery/production-readiness-checklist.md` with a final section named `Production Launch Verification - 2026-05-23`.
- [ ] Commit with message `docs: record production launch verification`.
- [ ] Push the branch and provide the final branch name, commit SHA, and verification summary.

## Acceptance Criteria

- [ ] Current Toolbox API contract remains compatible with the documented endpoints, auth, request bodies, response bodies, task states, pagination, and error envelopes.
- [ ] External Toolbox integration rules state that the external team adapts to the gateway contract.
- [ ] WSL bootstrap provisions Docker Engine, Docker Compose plugin, Python 3.12, PostgreSQL client tools, Redis tools, and project dependencies.
- [ ] PostgreSQL migrations create all production tables and indexes from a clean database.
- [ ] PostgreSQL repository tests pass against a real PostgreSQL 16 container in WSL.
- [ ] Redis queue tests pass against a real Redis 7 container in WSL.
- [ ] Worker retry and dead-letter behavior are covered by automated tests.
- [ ] API and worker run together against PostgreSQL and Redis through `docker-compose.prodlike.yml`.
- [ ] Signed smoke test completes a discovery task and returns at least one result.
- [ ] Operations CLI covers config verification, migrations, scope seeding, smoke testing, and retention cleanup.
- [ ] Observability includes request IDs, structured logs, and Prometheus metrics.
- [ ] CI verifies PostgreSQL, Redis, migrations, tests, and compose configuration.
- [ ] Production readiness checklist includes exact command outputs for Windows, WSL, integration tests, and compose smoke test.

## Self-Review Checklist

- [ ] Coverage: every new production behavior has an automated test or a recorded smoke command.
- [ ] Completeness scan: no unfinished-work markers remain in delivery files.
- [ ] Type consistency: configuration values have explicit types and stable environment-variable names.
- [ ] Scope check: implementation keeps the current API contract stable and limits changes to production readiness, operations, and verification.
- [ ] Security check: secrets are read from config files or environment variables, never committed as real values.
- [ ] Operations check: a new engineer can run WSL bootstrap, migrations, compose stack, and smoke test from documented commands.

