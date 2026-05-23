# Toolbox Integration Delivery Design

## Goal

Deliver the resource discovery gateway as a complete integration package for the Security Toolbox team. The package should let the Toolbox team start local or test-environment integration with minimal back-and-forth: a real HTTP service, signed requests, durable task and result storage, a reliable worker path, clear API examples, and explicit handoff material.

This is still an integration delivery build, not the final production deployment. It should be production-shaped enough that later replacement of SQLite and Redis with managed PostgreSQL, Redis, KMS, centralized audit, and deployment automation does not change the Toolbox-facing API contract.

## Non-Goals

- Do not turn the gateway into the customer's long-term asset inventory.
- Do not add cloud-side active scanning, vulnerability validation, weak-password checks, directory brute force, or exploit-chain validation.
- Do not allow the Toolbox to submit raw FOFA, uncover, or vendor-specific query syntax.
- Do not store provider API keys, Toolbox client secrets, or customer credentials in the repository.
- Do not expand to additional mapping vendors in this phase.
- Do not build a management UI. Scope profiles can be seeded through files or database initialization for the integration delivery.

## Delivery Shape

The integration delivery should contain these runnable pieces:

- A FastAPI application exposing the existing discovery API under `/api/v1/discovery`.
- HMAC request authentication wired into HTTP middleware or dependencies.
- SQLite-backed repositories for task metadata, task results, scope profiles, audit events, nonce replay protection, and queue jobs.
- A Redis-backed queue implementation for integration environments, plus an in-process queue for tests and local fallback.
- A worker process that consumes queued tasks, runs the discovery execution path, persists results, records audit events, and updates task status.
- Environment-based configuration through `.env.example` and documented variables.
- Health and readiness endpoints for local deployment checks.
- OpenAPI output and handoff documents with curl examples, status flow, error codes, pagination semantics, and integration checklist.

## Architecture

The gateway keeps its current core domain modules and wraps them with deployment-facing adapters.

```text
Security Toolbox
-> FastAPI HTTP app
-> Request auth middleware
-> DiscoveryGatewayApi
-> ScopeGuard
-> TaskRepository / ResultRepository / ScopeProfileRepository / AuditRepository
-> QueueRepository or RedisTaskQueue
-> TaskWorker
-> execution.run_discovery
-> FOFA / uncover adapters
```

The existing `DiscoveryGatewayApi` remains the canonical application layer. FastAPI should translate HTTP requests and responses, but business behavior should stay in the API handler, repositories, scope guard, worker, and execution modules. This keeps unit tests useful and avoids coupling discovery behavior to a web framework.

## HTTP Service

The FastAPI service should expose:

- `GET /healthz`: liveness check. Returns service name, version, and `ok`.
- `GET /readyz`: readiness check. Verifies configured repositories and queue can be reached.
- `GET /api/v1/discovery/scope-profile`
- `POST /api/v1/discovery/tasks`
- `GET /api/v1/discovery/tasks/{task_id}`
- `GET /api/v1/discovery/tasks/{task_id}/results`
- `GET /api/v1/discovery/openapi.json` or the default FastAPI OpenAPI path, documented for the Toolbox team.

The four discovery endpoints must preserve the existing API contract in `docs/resource-discovery/toolbox-api-contract.md`. Any required contract adjustment should update that document and its handoff companion in the same change.

## Request Authentication

Production-shaped HTTP requests require these headers:

- `X-Tenant-Id`
- `X-Client-Id`
- `X-Timestamp`
- `X-Nonce`
- `X-Signature`

The signature input remains:

```text
METHOD
PATH
X-Timestamp
X-Nonce
SHA256(request_body)
```

The FastAPI layer should use the existing `request_auth.py` primitives and add an HTTP-facing key resolver. For this delivery, the key resolver may read client secrets from environment variables or an ignored local config file. The repository must only include examples using placeholder values.

Nonce replay protection should be backed by a repository so multiple HTTP workers can share replay state. SQLite is sufficient for this integration delivery; production can replace it with Redis or database-backed TTL storage.

Authentication errors should return a stable error response without signature calculation details.

## Storage

The integration delivery should add durable repositories without removing the current file-backed PoC implementations.

SQLite-backed repositories should cover:

- Tasks: `tenant_id`, `task_id`, status, profile ID, accepted scope, query plan summary, quota fields, errors, timestamps.
- Results: task result payloads split or indexed by result type so `assets`, `services`, and `source_evidence` pagination remains stable.
- Scope profiles: active profile JSON per tenant and profile ID.
- Audit events: append-only event records with tenant ID, task ID when present, event type, sanitized details, and timestamp.
- Nonces: tenant ID, client ID, nonce, timestamp, expiry timestamp.
- Queue jobs when Redis is not configured: queued task IDs, state, attempts, next run time, timestamps.

SQLite is chosen for the first complete delivery because it is easy for the Toolbox team to run locally, easy to inspect during integration, and can be replaced behind repository interfaces. The schema should avoid SQLite-only assumptions where practical so PostgreSQL migration is straightforward.

## Queue And Worker

The delivery should support two queue modes:

- `memory`: used by unit tests and simple local demos.
- `redis`: used for integration-like runs when Redis is available.

If Redis is not available, the service should fail readiness when configured for Redis, rather than silently falling back to memory in integration mode.

Worker behavior:

- Read a queued task.
- Mark it `running`.
- Run the discovery execution path.
- Persist assets, services, source evidence, risk hints, analysis, remediation, report snapshot, quota usage, and source errors.
- Mark task `success`, `partial_success`, or `failed`.
- Record audit events for task start, task completion, task failure, provider errors, and result persistence.

Retry behavior:

- Recoverable provider errors such as timeout and rate limit may be retried with capped attempts.
- Non-recoverable errors such as scope rejection, profile mismatch, and invalid configuration should not be retried.
- Failed attempts should preserve readable error objects for the Toolbox team.

This phase should include retry metadata and retry decisions, but it does not need a full dead-letter queue UI.

## Configuration

Add `.env.example` with placeholder values for:

- `RESOURCE_DISCOVERY_ENV`
- `RESOURCE_DISCOVERY_API_PREFIX`
- `RESOURCE_DISCOVERY_SQLITE_PATH`
- `RESOURCE_DISCOVERY_QUEUE_BACKEND`
- `RESOURCE_DISCOVERY_REDIS_URL`
- `RESOURCE_DISCOVERY_CLIENT_SECRETS_FILE`
- `RESOURCE_DISCOVERY_SCOPE_PROFILE_SEED`
- `RESOURCE_DISCOVERY_RESULT_LIMIT_DEFAULT`
- `RESOURCE_DISCOVERY_RESULT_LIMIT_MAX`
- `RESOURCE_DISCOVERY_NONCE_WINDOW_SECONDS`
- `FOFA_BASE_URL`
- `FOFA_API_KEY`
- `FOFA_EMAIL`
- `FOFA_FULL_HISTORY`
- `RESOURCE_DISCOVERY_LOG_LEVEL`

The README should include copy-paste local startup commands for:

- Installing dependencies.
- Initializing the SQLite database.
- Seeding a sample scope profile.
- Starting the FastAPI app.
- Starting the worker.
- Running HTTP integration tests.

## API Contract And Handoff Material

Update handoff documents so the Toolbox team can integrate without reading Python code:

- `docs/resource-discovery/toolbox-api-contract.md`: keep endpoint contract, authentication, status enums, error model, pagination, and freshness semantics current.
- `docs/resource-discovery/toolbox-handoff.md`: add startup flow, integration sequence, polling advice, and troubleshooting.
- `docs/resource-discovery/production-readiness-checklist.md`: mark the integration delivery state honestly, distinguishing complete-for-integration from complete-for-production.
- README: add a short "Toolbox integration delivery" section with commands and links.

Add curl examples for:

- Generating a signed request.
- Fetching scope profile.
- Creating a task.
- Polling task status.
- Pulling paginated assets.
- Handling a rejected out-of-scope request.

The examples should use placeholder domains and secrets, not real provider keys or customer targets.

## Testing

Add tests at three levels.

Unit tests:

- SQLite task repository creates, updates, and loads tasks by `tenant_id + task_id`.
- SQLite result repository paginates each result type stably.
- SQLite scope profile repository rejects inactive or mismatched profiles.
- Nonce repository rejects replay within the configured window.
- Queue implementation preserves job state and attempt metadata.

HTTP integration tests:

- Missing signature is rejected.
- Bad signature is rejected.
- Valid signed `GET /scope-profile` succeeds.
- Valid signed `POST /tasks` creates a queued task.
- Out-of-scope task request returns `rejected` with `scope_out_of_bounds`.
- Status endpoint returns queued, running, and terminal states.
- Result endpoint paginates assets, services, and source evidence.
- Error responses do not expose tracebacks, provider keys, or signature calculation details.

Worker tests:

- Worker consumes a queued task and marks it running.
- Successful fixture execution persists results and marks success.
- Partial provider failure persists partial results and marks partial success.
- Recoverable provider timeout records retry metadata.
- Non-recoverable configuration failure marks failed without retry.
- Audit events are written for start, completion, failure, and result pull.

The standard verification command remains:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

## Acceptance Criteria

The delivery is ready for Toolbox integration when:

- A fresh clone can install dependencies, initialize local SQLite storage, seed a scope profile, start the API service, start the worker, and run the documented curl sequence.
- The Toolbox team can call the four discovery endpoints over HTTP without reading Python internals.
- Signed request verification works at the FastAPI layer.
- Tasks survive API process restart when backed by SQLite and Redis.
- Results can be pulled with stable pagination after task completion.
- Out-of-scope requests are rejected before any provider call.
- Audit events are persisted without provider keys or client secrets.
- OpenAPI and handoff documents match the implemented responses.
- All automated tests pass.

## Implementation Order

1. Freeze the integration-facing contract and update docs where existing PoC wording says HTTP auth is not implemented.
2. Add configuration loading and `.env.example`.
3. Add SQLite schema and repositories while preserving current file-backed repositories.
4. Add nonce repository and HTTP key resolver.
5. Add FastAPI app and request authentication.
6. Add Redis queue implementation and database-backed local queue fallback.
7. Add worker CLI or module entrypoint.
8. Add HTTP and worker integration tests.
9. Update README, handoff docs, OpenAPI export instructions, and curl examples.
10. Run full verification and package the handoff.

## Open Decisions

- Whether the integration environment will provide Redis on day one. If not, the database-backed queue fallback should be the documented default and Redis should be documented as the preferred shared-worker mode.
- Whether SQLite is acceptable for the first Toolbox integration handoff. If the Toolbox team requires PostgreSQL immediately, repository interfaces should stay the same but the first durable implementation should target PostgreSQL instead.
- Whether signed request examples should include a small helper script for the Toolbox team. The recommended answer is yes, because it reduces integration mistakes around body hashing and nonce handling.

## Spec Self-Review

- Coverage: The design covers HTTP service, authentication, durable storage, queue, worker, configuration, handoff docs, tests, and acceptance criteria for a complete Toolbox integration delivery.
- Placeholder scan: No implementation requirement is left as an unfinished-work marker. Open decisions are explicit choices that require project coordination, not missing design details.
- Scope check: The phase is larger than a small PoC change, but it is a coherent single delivery package because every task supports the same outcome: low-friction Toolbox integration.
- Ambiguity check: The design explicitly separates integration-ready behavior from final production readiness, and it keeps the gateway out of long-term asset inventory and vulnerability validation responsibilities.
