# Resource Discovery Gateway Async Roadmap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the current synchronous gateway POC into a clear, asynchronous asset discovery gateway that the Security Toolbox can call reliably.

**Architecture:** Keep the current Python package and file-backed PoC, but introduce repository abstractions, task state transitions, a lightweight in-process queue/worker, and stable API contracts. The gateway remains a short-term task/result service; the Security Toolbox remains the long-term asset and remediation system.

**Tech Stack:** Python 3.11, pytest, current `resource_discovery` package, file-backed repositories for PoC, later replaceable by database/queue implementations.

---

## Phase 0: Orientation And Invariants

Do before any implementation:

- [ ] Run `git status -sb`.
- [ ] Run `.\.venv\Scripts\python.exe -m pytest -q`.
- [ ] Confirm the baseline is clean and tests pass.
- [ ] Read:
  - `docs/resource-discovery/gateway-roadmap.md`
  - `docs/resource-discovery/uncover-gateway-api-poc-plan.md`
  - `src/resource_discovery/gateway_api.py`
  - `src/resource_discovery/scope_guard.py`
  - `src/resource_discovery/uncover_client.py`

Non-negotiable invariants:

- [ ] Toolboxes cannot submit raw FOFA/uncover queries.
- [ ] Customer requested scope must not exceed `TenantScopeProfile`.
- [ ] `stale` freshness never means “asset is offline”.
- [ ] Gateway stores short-term task/result data, not the customer’s long-term asset inventory.
- [ ] No provider API key is committed.
- [ ] Every change is covered by tests before implementation.

## Phase 1: API Contract Document

**Files:**
- Create: `docs/resource-discovery/toolbox-api-contract.md`
- Modify: `README.md`

Tasks:

- [ ] Document `GET /api/v1/discovery/scope-profile`.
- [ ] Document `POST /api/v1/discovery/tasks`.
- [ ] Document `GET /api/v1/discovery/tasks/{task_id}`.
- [ ] Document `GET /api/v1/discovery/tasks/{task_id}/results`.
- [ ] Document response status values:
  - `queued`
  - `running`
  - `success`
  - `partial_success`
  - `failed`
  - `cancelled`
  - `rejected`
- [ ] Document error object shape:
  ```json
  {
    "code": "scope_out_of_bounds",
    "message": "Requested scope is outside the tenant authorized scope.",
    "recoverable": false,
    "details": {}
  }
  ```
- [ ] Document pagination:
  ```json
  {
    "page": {
      "next_cursor": "100",
      "limit": 100
    }
  }
  ```
- [ ] Document freshness semantics.
- [ ] Document which fields the Toolbox should persist long-term.
- [ ] Run `.\.venv\Scripts\python.exe -m pytest -q`.
- [ ] Commit: `docs: add toolbox api contract`.

## Phase 2: Repository Interfaces

**Files:**
- Create: `src/resource_discovery/repositories.py`
- Modify: `src/resource_discovery/task_store.py`
- Test: `tests/test_repositories.py`

Target interfaces:

```python
class TaskRepository(Protocol):
    def create(self, payload: dict) -> None: ...
    def update(self, payload: dict) -> None: ...
    def load(self, tenant_id: str, task_id: str) -> dict: ...
    def list(self, tenant_id: str) -> list[dict]: ...

class ResultRepository(Protocol):
    def save_results(self, tenant_id: str, task_id: str, payload: dict) -> None: ...
    def load_results(self, tenant_id: str, task_id: str, cursor: str | None, limit: int) -> dict: ...

class ScopeProfileRepository(Protocol):
    def load_active(self, tenant_id: str, profile_id: str) -> TenantScopeProfile: ...
```

Tasks:

- [ ] Write failing tests for `FileTaskRepository`.
- [ ] Implement `FileTaskRepository` by wrapping current `FileTaskStore`.
- [ ] Write failing tests for `FileResultRepository` pagination.
- [ ] Implement `FileResultRepository`.
- [ ] Write failing tests for `FileScopeProfileRepository`.
- [ ] Implement `FileScopeProfileRepository` loading JSON profile files.
- [ ] Run repository tests.
- [ ] Run full pytest.
- [ ] Commit: `feat: add gateway repository abstractions`.

## Phase 3: Stable Error Model

**Files:**
- Create: `src/resource_discovery/errors.py`
- Modify: `src/resource_discovery/gateway_api.py`
- Test: `tests/test_gateway_errors.py`

Target model:

```python
@dataclass(frozen=True)
class ApiError:
    code: str
    message: str
    recoverable: bool
    details: dict[str, Any] = field(default_factory=dict)
```

Tasks:

- [ ] Write failing test for scope rejection using `code=scope_out_of_bounds`.
- [ ] Write failing test for provider timeout mapping.
- [ ] Write failing test ensuring no Python traceback is returned.
- [ ] Implement `ApiError.to_dict()`.
- [ ] Update gateway API rejected responses.
- [ ] Run targeted tests.
- [ ] Run full pytest.
- [ ] Commit: `feat: add gateway api error model`.

## Phase 4: Lightweight Async Task Queue

**Files:**
- Create: `src/resource_discovery/task_queue.py`
- Create: `src/resource_discovery/worker.py`
- Modify: `src/resource_discovery/gateway_api.py`
- Test: `tests/test_task_queue.py`
- Test: `tests/test_gateway_async.py`

Target behavior:

```text
create_task()
-> validates scope
-> saves queued task
-> enqueues work item
-> returns status queued

worker.run_once()
-> loads task
-> marks running
-> executes discovery
-> saves results
-> marks success / partial_success / failed
```

Tasks:

- [ ] Write failing test for enqueue/dequeue FIFO.
- [ ] Implement `InMemoryTaskQueue`.
- [ ] Write failing test for `create_task` returning `queued`.
- [ ] Update `DiscoveryGatewayApi.create_task`.
- [ ] Write failing test for `TaskWorker.run_once` moving task to `running`.
- [ ] Implement running state update.
- [ ] Write failing test for successful worker execution.
- [ ] Implement successful worker execution.
- [ ] Write failing test for provider exception resulting in `failed`.
- [ ] Implement failure handling.
- [ ] Run async gateway tests.
- [ ] Run full pytest.
- [ ] Commit: `feat: add lightweight async gateway worker`.

## Phase 5: Result Pagination

**Files:**
- Modify: `src/resource_discovery/gateway_api.py`
- Modify: `src/resource_discovery/repositories.py`
- Test: `tests/test_gateway_results_pagination.py`

Tasks:

- [ ] Write failing test for `limit=1` returning `next_cursor`.
- [ ] Write failing test for second page using cursor.
- [ ] Write failing test for empty page after end.
- [ ] Implement stable cursor based on integer offset.
- [ ] Add max `limit` guard.
- [ ] Run pagination tests.
- [ ] Run full pytest.
- [ ] Commit: `feat: paginate gateway discovery results`.

## Phase 6: Scope Profile Persistence

**Files:**
- Create: `examples/scope_profile.json`
- Modify: `src/resource_discovery/scope_guard.py`
- Modify: `src/resource_discovery/repositories.py`
- Test: `tests/test_scope_profile_repository.py`

Tasks:

- [ ] Add example scope profile JSON.
- [ ] Write failing test that loads example profile.
- [ ] Implement JSON loader.
- [ ] Write failing test for inactive profile rejection.
- [ ] Implement inactive profile rejection.
- [ ] Write failing test for profile ID mismatch.
- [ ] Implement mismatch error.
- [ ] Run tests.
- [ ] Commit: `feat: persist tenant scope profiles`.

## Phase 7: Uncover Sidecar Runtime Hardening

**Files:**
- Modify: `src/resource_discovery/uncover_client.py`
- Test: `tests/test_uncover_client.py`

Tasks:

- [ ] Write failing test for command timeout mapping.
- [ ] Add `timeout_seconds` to `UncoverCommandSourceClient`.
- [ ] Write failing test for non-zero exit code raising provider error.
- [ ] Implement `UncoverExecutionError`.
- [ ] Write failing test for invalid JSONL line isolation.
- [ ] Implement invalid line skip with parse error count.
- [ ] Ensure command arguments never include provider API key.
- [ ] Run uncover tests.
- [ ] Run full pytest.
- [ ] Commit: `feat: harden uncover sidecar execution`.

## Phase 8: FOFA Fallback Runtime Hardening

**Files:**
- Modify: `src/resource_discovery/fofa_client.py`
- Modify: `src/resource_discovery/source_client.py`
- Test: `tests/test_fofa_client.py`

Tasks:

- [ ] Write failing test for provider timeout mapping.
- [ ] Write failing test for rate limit error mapping.
- [ ] Write failing test for malformed provider response.
- [ ] Implement clear `FofaApiError` messages.
- [ ] Document `lastupdatetime` and `full=true/full=false`.
- [ ] Run FOFA tests.
- [ ] Run full pytest.
- [ ] Commit: `feat: harden fofa fallback client`.

## Phase 9: Audit Events For Gateway API

**Files:**
- Modify: `src/resource_discovery/audit.py`
- Modify: `src/resource_discovery/gateway_api.py`
- Test: `tests/test_gateway_audit.py`

Events:

- `scope_profile_viewed`
- `discovery_task_requested`
- `discovery_scope_rejected`
- `discovery_task_queued`
- `discovery_task_started`
- `discovery_task_completed`
- `discovery_task_failed`
- `discovery_results_fetched`

Tasks:

- [ ] Write failing test for task request audit.
- [ ] Write failing test for scope rejected audit.
- [ ] Write failing test for result fetch audit.
- [ ] Implement audit hook injection into gateway API.
- [ ] Run gateway audit tests.
- [ ] Run full pytest.
- [ ] Commit: `feat: audit gateway api activity`.

## Phase 10: TTL And Cleanup Policy

**Files:**
- Create: `src/resource_discovery/retention.py`
- Modify: repository file implementation.
- Test: `tests/test_retention.py`
- Docs: `docs/resource-discovery/security-compliance.md`

Tasks:

- [ ] Write failing test for expired task result detection.
- [ ] Implement `RetentionPolicy`.
- [ ] Write failing test for deleting expired result files.
- [ ] Implement cleanup.
- [ ] Document default retention:
  - metadata 180 days.
  - results 30-90 days.
  - audit 180-365 days.
- [ ] Run tests.
- [ ] Commit: `feat: add gateway retention policy`.

## Phase 11: Live Validation Script

**Files:**
- Create: `scripts/live_fofa_validation.py`
- Docs: `README.md`
- Test: no live test in pytest; unit-test helper functions only.

Tasks:

- [ ] Script reads `FOFA_API_KEY`.
- [ ] Script reads `FOFA_BASE_URL`.
- [ ] Script reads authorized domain from CLI arg.
- [ ] Script writes artifacts under ignored `artifacts/live-validation/`.
- [ ] Script prints summary only:
  - status.
  - asset count.
  - service count.
  - freshness counts.
  - snapshot path.
- [ ] Script never prints API key.
- [ ] Add README command.
- [ ] Run full pytest.
- [ ] Commit: `chore: add live fofa validation script`.

## Phase 12: Toolbox Handoff Package

**Files:**
- Create: `docs/resource-discovery/toolbox-handoff.md`
- Modify: `README.md`

Contents:

- [ ] API overview.
- [ ] Example scope profile response.
- [ ] Example task create request.
- [ ] Polling sequence.
- [ ] Results pagination.
- [ ] Error code table.
- [ ] freshness explanation.
- [ ] Fields the Toolbox should persist.
- [ ] Fields the Toolbox should treat as transient.
- [ ] Security notes.

Commit: `docs: add toolbox integration handoff`.

## Phase 13: Production Readiness Review

**Files:**
- Create: `docs/resource-discovery/production-readiness-checklist.md`

Checklist:

- [ ] Auth/signature strategy.
- [ ] Tenant isolation.
- [ ] ScopeGuard coverage.
- [ ] Provider key management.
- [ ] Queue strategy.
- [ ] Database strategy.
- [ ] Result retention.
- [ ] Audit retention.
- [ ] Rate limit and quota.
- [ ] Error model.
- [ ] Observability.
- [ ] Disaster recovery.
- [ ] Compliance notes for HK and CN regions.

Commit: `docs: add production readiness checklist`.

## Verification Before Any Final Claim

Before claiming a phase is complete:

- [ ] Run targeted tests for changed modules.
- [ ] Run full `.\.venv\Scripts\python.exe -m pytest -q`.
- [ ] Run `git status -sb`.
- [ ] Confirm no `artifacts/` content is staged.
- [ ] Confirm no API key appears in tracked files.
- [ ] Commit.
- [ ] Push.

## Current Next Recommended Task

Start with **Phase 1: API Contract Document**. It gives the Toolbox team a stable target before we reshape the handler into asynchronous execution.
