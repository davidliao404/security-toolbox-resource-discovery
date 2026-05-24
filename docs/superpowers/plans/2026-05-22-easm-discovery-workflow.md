# EASM Discovery Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deepen the gateway's passive internet asset discovery workflow while keeping the gateway boundary unchanged: no active scanning, no vulnerability verification, no long-term asset inventory.

**Architecture:** Add a strategy layer above the current FOFA query planner. The default `baseline` strategy preserves today's query volume and behavior; an opt-in `easm` strategy generates richer authorized passive queries, records query intent, estimates ownership confidence, and produces Toolbox-ready discovery evidence for local verification.

**Tech Stack:** Python 3.11, pytest, existing `resource_discovery` package, FOFA-compatible passive source clients, current gateway task/result models.

---

## Boundary Decision

The gateway boundary stays:

```text
Gateway:
  authorized passive discovery
  query planning and provider aggregation
  evidence normalization
  ownership confidence
  passive risk hints
  short-term task result storage

Toolbox:
  long-term asset inventory
  active validation
  vulnerability confirmation
  remediation workflow
  reporting archive
```

Do not implement cloud-side active probing, proof-of-concept validation, weak-password checks, directory brute force, or customer-facing long-term inventory in this plan.

## File Structure

- Modify: `src/resource_discovery/models.py`
  - Add optional query metadata to `SourceQueryPlan`.
  - Add optional discovery metadata to `DiscoveredAsset` and `ExposedService` only when needed by later tasks.
- Modify: `src/resource_discovery/query_planner.py`
  - Preserve current baseline planning.
  - Add opt-in `easm` strategy with controlled FOFA query templates.
- Create: `src/resource_discovery/discovery_workflow.py`
  - Own strategy selection, pivot policy, and query budget decisions.
- Create: `src/resource_discovery/ownership.py`
  - Score whether a passive result belongs to the tenant's authorized scope.
- Modify: `src/resource_discovery/normalizer.py`
  - Preserve extended FOFA fields such as `domain`, `asn`, `org`, `server`, `header_hash`, `banner_hash`, `product`, `version`, `cert`, `cname`, and `lastupdatetime`.
- Modify: `src/resource_discovery/source_client.py`
  - Request richer FOFA fields by default without changing safety boundaries.
- Create: `src/resource_discovery/change_detection.py`
  - Compare two task snapshots and emit additions, removals, and service changes.
- Modify: `src/resource_discovery/execution.py`
  - Accept discovery strategy and wire the workflow into dry-run, fixture, and live paths.
- Modify: `src/resource_discovery/gateway_api.py`
  - Allow approved strategy values from the gateway request when tenant limits permit.
- Modify: `docs/resource-discovery/toolbox-api-contract.md`
  - Document discovery strategy, ownership confidence, passive evidence fields, and change summaries.
- Modify: `docs/resource-discovery/toolbox-handoff.md`
  - Explain the professional multi-step passive discovery workflow.
- Test: `tests/test_query_planner.py`
- Test: `tests/test_discovery_workflow.py`
- Test: `tests/test_ownership.py`
- Test: `tests/test_normalizer.py`
- Test: `tests/test_change_detection.py`
- Test: `tests/test_execution_modes.py`
- Test: `tests/test_gateway_api.py`

## Task 1: Query Plan Metadata And Baseline Compatibility

**Files:**
- Modify: `src/resource_discovery/models.py`
- Modify: `src/resource_discovery/query_planner.py`
- Test: `tests/test_query_planner.py`

- [x] **Step 1: Write failing test for query metadata**

Add to `tests/test_query_planner.py`:

```python
def test_baseline_query_plans_include_stage_and_intent_metadata():
    seeds = [DiscoverySeed(seed_id="s1", type="root_domain", value="example.org")]

    plans = plan_fofa_queries("dt_001", seeds)

    assert len(plans) == 1
    assert plans[0].stage == "seed"
    assert plans[0].query_intent == "root_domain_match"
    assert plans[0].derived_from == ["s1"]
```

- [x] **Step 2: Run test and verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_query_planner.py::test_baseline_query_plans_include_stage_and_intent_metadata -q
```

Expected: FAIL because `SourceQueryPlan` has no `stage`, `query_intent`, or `derived_from`.

- [x] **Step 3: Add optional metadata fields**

In `src/resource_discovery/models.py`, extend `SourceQueryPlan`:

```python
@dataclass(frozen=True)
class SourceQueryPlan(Serializable):
    plan_id: str
    task_id: str
    source: str
    seed_id: str
    source_query: str
    query_type: str
    page_limit: int = 10
    result_limit: int = 1000
    stage: str = "seed"
    query_intent: str | None = None
    derived_from: list[str] = field(default_factory=list)
```

In `src/resource_discovery/query_planner.py`, set the metadata when creating each plan:

```python
source_query, query_type, query_intent = _query_for_seed(seed)
...
stage="seed",
query_intent=query_intent,
derived_from=[seed.seed_id],
```

Update `_query_for_seed()` to return `(source_query, query_type, query_intent)`.

- [x] **Step 4: Run query planner tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_query_planner.py -q
```

Expected: PASS.

- [x] **Step 5: Run full tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Expected: PASS.

## Task 2: Opt-In EASM FOFA Query Strategy

**Files:**
- Modify: `src/resource_discovery/query_planner.py`
- Test: `tests/test_query_planner.py`

- [x] **Step 1: Write failing test for default baseline compatibility**

Add:

```python
def test_default_strategy_preserves_existing_query_count_and_queries():
    seeds = [
        DiscoverySeed(seed_id="s1", type="root_domain", value="example.org"),
        DiscoverySeed(seed_id="s2", type="organization_name", value="Example Org"),
        DiscoverySeed(seed_id="s3", type="ip_cidr", value="203.0.113.0/24"),
    ]

    plans = plan_fofa_queries("dt_001", seeds)

    assert [plan.source_query for plan in plans] == [
        'domain="example.org"',
        'cert.subject.org="Example Org" || title="Example Org"',
        'ip="203.0.113.0/24"',
    ]
```

- [x] **Step 2: Write failing test for opt-in EASM strategy**

Add:

```python
def test_easm_strategy_generates_controlled_passive_query_templates():
    seeds = [
        DiscoverySeed(seed_id="s1", type="root_domain", value="example.org"),
        DiscoverySeed(seed_id="s2", type="organization_name", value="Example Org"),
        DiscoverySeed(seed_id="s3", type="ip_cidr", value="203.0.113.0/24"),
    ]

    plans = plan_fofa_queries("dt_001", seeds, strategy="easm")

    assert [plan.query_intent for plan in plans] == [
        "root_domain_match",
        "host_suffix_match",
        "certificate_domain_match",
        "organization_certificate_match",
        "organization_title_match",
        "asn_organization_match",
        "ip_range_match",
    ]
    assert [plan.source_query for plan in plans] == [
        'domain="example.org"',
        'host=".example.org"',
        'cert.domain="example.org"',
        'cert.subject.org="Example Org"',
        'title="Example Org"',
        'org="Example Org"',
        'ip="203.0.113.0/24"',
    ]
```

- [x] **Step 3: Run EASM planner test and verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_query_planner.py::test_easm_strategy_generates_controlled_passive_query_templates -q
```

Expected: FAIL because `strategy` is not supported.

- [x] **Step 4: Implement strategy selection**

In `src/resource_discovery/query_planner.py`:

```python
SUPPORTED_STRATEGIES = {"baseline", "easm"}

def plan_fofa_queries(
    task_id: str,
    seeds: list[DiscoverySeed],
    page_limit: int = 10,
    result_limit: int = 1000,
    strategy: str = "baseline",
) -> list[SourceQueryPlan]:
    if strategy not in SUPPORTED_STRATEGIES:
        raise ValueError(f"Unsupported discovery strategy: {strategy}")
    templates = _baseline_templates if strategy == "baseline" else _easm_templates
    plans: list[SourceQueryPlan] = []
    for seed in seeds:
        for source_query, query_type, query_intent in templates(seed):
            plans.append(...)
    return plans
```

Use `_escape_fofa()` for every seed value. Do not add freeform user queries.

- [x] **Step 5: Run query planner tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_query_planner.py -q
```

Expected: PASS.

## Task 3: Discovery Workflow Policy

**Files:**
- Create: `src/resource_discovery/discovery_workflow.py`
- Modify: `src/resource_discovery/execution.py`
- Test: `tests/test_discovery_workflow.py`
- Test: `tests/test_execution_modes.py`

- [x] **Step 1: Write failing workflow policy tests**

Create `tests/test_discovery_workflow.py`:

```python
import pytest

from resource_discovery.discovery_workflow import DiscoveryWorkflowConfig, build_query_plans
from resource_discovery.models import DiscoverySeed


def test_workflow_uses_baseline_strategy_by_default():
    config = DiscoveryWorkflowConfig()
    seeds = [DiscoverySeed(seed_id="s1", type="root_domain", value="example.org")]

    plans = build_query_plans("dt_001", seeds, config)

    assert len(plans) == 1
    assert plans[0].query_intent == "root_domain_match"


def test_workflow_enforces_max_plans_before_provider_calls():
    config = DiscoveryWorkflowConfig(strategy="easm", max_query_plans=2)
    seeds = [
        DiscoverySeed(seed_id="s1", type="root_domain", value="example.org"),
        DiscoverySeed(seed_id="s2", type="organization_name", value="Example Org"),
    ]

    with pytest.raises(ValueError, match="query plan budget"):
        build_query_plans("dt_001", seeds, config)
```

- [x] **Step 2: Run workflow tests and verify they fail**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_discovery_workflow.py -q
```

Expected: FAIL because `discovery_workflow.py` does not exist.

- [x] **Step 3: Implement workflow policy**

Create `src/resource_discovery/discovery_workflow.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

from .models import DiscoverySeed, SourceQueryPlan
from .query_planner import plan_fofa_queries


@dataclass(frozen=True)
class DiscoveryWorkflowConfig:
    strategy: str = "baseline"
    max_query_plans: int = 30
    page_limit: int = 10
    result_limit: int = 1000


def build_query_plans(
    task_id: str,
    seeds: list[DiscoverySeed],
    config: DiscoveryWorkflowConfig,
) -> list[SourceQueryPlan]:
    plans = plan_fofa_queries(
        task_id,
        seeds,
        page_limit=config.page_limit,
        result_limit=config.result_limit,
        strategy=config.strategy,
    )
    if len(plans) > config.max_query_plans:
        raise ValueError(
            f"Generated {len(plans)} query plans, exceeding query plan budget {config.max_query_plans}"
        )
    return plans
```

- [x] **Step 4: Wire execution to workflow config**

In `src/resource_discovery/execution.py`, add parameters:

```python
discovery_strategy: str = "baseline",
max_query_plans: int = 30,
```

Replace direct `plan_fofa_queries(...)` with:

```python
workflow_config = DiscoveryWorkflowConfig(
    strategy=discovery_strategy,
    max_query_plans=max_query_plans,
    page_limit=page_limit,
    result_limit=result_limit,
)
plans = build_query_plans(task_id, seeds, workflow_config)
```

- [x] **Step 5: Add dry-run test for EASM strategy**

In `tests/test_execution_modes.py`:

```python
def test_dry_run_supports_opt_in_easm_strategy():
    payload = run_discovery(
        seeds_path="examples/seeds.json",
        mode="dry-run",
        discovery_strategy="easm",
        max_query_plans=10,
    )

    assert "certificate_domain_match" in [
        plan["query_intent"] for plan in payload["query_plans"]
    ]
```

- [x] **Step 6: Run targeted tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_discovery_workflow.py tests\test_execution_modes.py -q
```

Expected: PASS.

## Task 4: FOFA Extended Field Collection

**Files:**
- Modify: `src/resource_discovery/source_client.py`
- Modify: `src/resource_discovery/normalizer.py`
- Test: `tests/test_normalizer.py`

- [x] **Step 1: Write failing test for extended fields**

Add to `tests/test_normalizer.py`:

```python
from resource_discovery.models import SourceQueryPlan
from resource_discovery.normalizer import normalize_fofa_results


def test_normalizer_preserves_extended_fofa_evidence_fields():
    plan = SourceQueryPlan(
        plan_id="plan_001",
        task_id="dt_001",
        source="fofa",
        seed_id="s1",
        source_query='domain="example.org"',
        query_type="domain",
    )
    rows = [
        {
            "ip": "203.0.113.10",
            "host": "vpn.example.org",
            "domain": "example.org",
            "port": "443",
            "protocol": "https",
            "title": "VPN Portal",
            "product": "ExampleVPN",
            "version": "1.2.3",
            "server": "nginx",
            "asn": "64500",
            "org": "Example Limited",
            "country": "HK",
            "header_hash": "hh",
            "banner_hash": "bb",
            "cname": "edge.example-cdn.net",
            "lastupdatetime": "2026-05-20T00:00:00Z",
        }
    ]

    batch = normalize_fofa_results("dt_001", plan, rows)

    evidence = batch.evidences[0].evidence
    assert evidence["server"] == "nginx"
    assert evidence["asn"] == "64500"
    assert evidence["org"] == "Example Limited"
    assert evidence["header_hash"] == "hh"
    assert evidence["banner_hash"] == "bb"
    assert evidence["cname"] == "edge.example-cdn.net"
    assert batch.assets[0].asn == "64500"
    assert batch.assets[0].country_or_region == "HK"
    assert batch.services[0].version == "1.2.3"
```

- [x] **Step 2: Run normalizer test and verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_normalizer.py::test_normalizer_preserves_extended_fofa_evidence_fields -q
```

Expected: FAIL because extended evidence fields are not preserved consistently.

- [x] **Step 3: Extend FOFA default fields**

In `src/resource_discovery/source_client.py`, update `FofaSourceClient.DEFAULT_FIELDS`:

```python
DEFAULT_FIELDS = [
    "host",
    "ip",
    "port",
    "protocol",
    "domain",
    "title",
    "product",
    "version",
    "server",
    "link",
    "asn",
    "org",
    "country",
    "country_name",
    "header_hash",
    "banner_hash",
    "cname",
    "lastupdatetime",
]
```

- [x] **Step 4: Preserve fields in normalizer evidence**

In `src/resource_discovery/normalizer.py`, include the new fields in `normalized_fields` and `evidence`.

- [x] **Step 5: Run normalizer tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_normalizer.py -q
```

Expected: PASS.

## Task 5: Ownership Confidence Scoring

**Files:**
- Create: `src/resource_discovery/ownership.py`
- Modify: `src/resource_discovery/normalizer.py`
- Test: `tests/test_ownership.py`

- [x] **Step 1: Write failing ownership tests**

Create `tests/test_ownership.py`:

```python
from resource_discovery.ownership import score_ownership


def test_scores_direct_domain_match_high():
    score = score_ownership(
        row={"host": "vpn.example.org", "domain": "example.org"},
        authorized_scope={"root_domains": ["example.org"]},
    )

    assert score == 0.95


def test_scores_organization_only_match_as_candidate():
    score = score_ownership(
        row={"org": "Example Limited"},
        authorized_scope={"org_names": ["Example Limited"]},
    )

    assert score == 0.7


def test_scores_unrelated_cloud_result_low():
    score = score_ownership(
        row={"host": "random.cloudfront.net", "org": "Amazon.com, Inc."},
        authorized_scope={"root_domains": ["example.org"], "org_names": ["Example Limited"]},
    )

    assert score == 0.3
```

- [x] **Step 2: Run ownership tests and verify they fail**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_ownership.py -q
```

Expected: FAIL because `ownership.py` does not exist.

- [x] **Step 3: Implement deterministic scoring**

Create `src/resource_discovery/ownership.py`:

```python
from __future__ import annotations


def score_ownership(row: dict, authorized_scope: dict[str, list[str]] | None = None) -> float:
    scope = authorized_scope or {}
    host = _lower(row.get("host") or row.get("domain") or "")
    domain = _lower(row.get("domain") or "")
    org = _lower(row.get("org") or "")
    root_domains = [_lower(item) for item in scope.get("root_domains", [])]
    org_names = [_lower(item) for item in scope.get("org_names", [])]

    if any(domain == root or host == root or host.endswith(f".{root}") for root in root_domains):
        return 0.95
    if org and org in org_names:
        return 0.7
    return 0.3


def _lower(value: object) -> str:
    return str(value or "").strip().lower().rstrip(".")
```

- [x] **Step 4: Add optional normalizer parameter**

Update `normalize_fofa_results()`:

```python
def normalize_fofa_results(
    task_id: str,
    plan: SourceQueryPlan,
    rows: list[dict],
    authorized_scope: dict[str, list[str]] | None = None,
) -> NormalizedBatch:
```

Set `ownership_confidence=score_ownership(row, authorized_scope)` when `authorized_scope` is provided; keep current row confidence fallback when not provided to avoid changing existing behavior.

- [x] **Step 5: Run ownership and normalizer tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_ownership.py tests\test_normalizer.py -q
```

Expected: PASS.

## Task 6: Change Detection For Toolbox Pull

**Files:**
- Create: `src/resource_discovery/change_detection.py`
- Test: `tests/test_change_detection.py`

- [x] **Step 1: Write failing change detection tests**

Create `tests/test_change_detection.py`:

```python
from resource_discovery.change_detection import compare_snapshots


def test_detects_new_asset_and_service_between_snapshots():
    before = {"assets": [], "services": []}
    after = {
        "assets": [{"asset_id": "asset_1", "domain": "vpn.example.org"}],
        "services": [{"service_id": "svc_1", "domain": "vpn.example.org", "port": 443}],
    }

    summary = compare_snapshots(before, after)

    assert summary["new_assets"] == [{"asset_id": "asset_1", "domain": "vpn.example.org"}]
    assert summary["new_services"] == [
        {"service_id": "svc_1", "domain": "vpn.example.org", "port": 443}
    ]


def test_detects_removed_service():
    before = {
        "assets": [{"asset_id": "asset_1", "domain": "vpn.example.org"}],
        "services": [{"service_id": "svc_1", "domain": "vpn.example.org", "port": 443}],
    }
    after = {"assets": [{"asset_id": "asset_1", "domain": "vpn.example.org"}], "services": []}

    summary = compare_snapshots(before, after)

    assert summary["removed_services"] == [
        {"service_id": "svc_1", "domain": "vpn.example.org", "port": 443}
    ]
```

- [x] **Step 2: Run change detection tests and verify they fail**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_change_detection.py -q
```

Expected: FAIL because `change_detection.py` does not exist.

- [x] **Step 3: Implement stable ID-based comparison**

Create `src/resource_discovery/change_detection.py`:

```python
from __future__ import annotations


def compare_snapshots(before: dict, after: dict) -> dict:
    before_assets = _by_id(before.get("assets", []), "asset_id")
    after_assets = _by_id(after.get("assets", []), "asset_id")
    before_services = _by_id(before.get("services", []), "service_id")
    after_services = _by_id(after.get("services", []), "service_id")
    return {
        "new_assets": _sorted_values(after_assets, set(after_assets) - set(before_assets)),
        "removed_assets": _sorted_values(before_assets, set(before_assets) - set(after_assets)),
        "new_services": _sorted_values(after_services, set(after_services) - set(before_services)),
        "removed_services": _sorted_values(before_services, set(before_services) - set(after_services)),
    }


def _by_id(items: list[dict], key: str) -> dict[str, dict]:
    return {str(item[key]): item for item in items if item.get(key)}


def _sorted_values(items: dict[str, dict], ids: set[str]) -> list[dict]:
    return [items[item_id] for item_id in sorted(ids)]
```

- [x] **Step 4: Run change detection tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_change_detection.py -q
```

Expected: PASS.

## Task 7: Gateway Contract For Discovery Strategy

**Files:**
- Modify: `src/resource_discovery/gateway_api.py`
- Modify: `docs/resource-discovery/toolbox-api-contract.md`
- Modify: `docs/resource-discovery/toolbox-handoff.md`
- Test: `tests/test_gateway_api.py`

- [x] **Step 1: Write failing gateway test**

Add a test showing that a task request may specify:

```json
{
  "discovery_strategy": "easm"
}
```

and that the response `query_plan_summary` includes:

```json
{
  "strategy": "easm",
  "planned_queries": 7
}
```

- [x] **Step 2: Run gateway test and verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_gateway_api.py -q
```

Expected: FAIL because strategy is not accepted or summarized.

- [x] **Step 3: Implement gateway strategy parsing**

Accept only `baseline` and `easm`. Reject unknown strategies with `invalid_discovery_strategy`. Use tenant `max_queries_per_task` to prevent expensive strategy expansion.

- [x] **Step 4: Update contract docs**

Document:

```json
{
  "discovery_strategy": "baseline"
}
```

and:

```json
{
  "discovery_strategy": "easm"
}
```

Explain that `easm` remains passive and may consume more provider quota.

- [x] **Step 5: Run gateway and docs-safe tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_gateway_api.py tests\test_query_planner.py tests\test_discovery_workflow.py -q
```

Expected: PASS.

## Task 8: Final Verification

**Files:**
- All modified files.

- [ ] **Step 1: Run whitespace check**

Run:

```powershell
git diff --check
```

Expected: no output.

- [ ] **Step 2: Run full test suite**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Expected: all tests pass.

- [ ] **Step 3: Review git diff**

Run:

```powershell
git diff --stat
git diff
```

Expected: changes match this plan and do not add active scanning, vulnerability verification, provider secrets, or long-term inventory behavior.

- [ ] **Step 4: Commit**

Run:

```powershell
git add docs src tests
git commit -m "feat: add passive easm discovery workflow"
```

Expected: commit succeeds.
