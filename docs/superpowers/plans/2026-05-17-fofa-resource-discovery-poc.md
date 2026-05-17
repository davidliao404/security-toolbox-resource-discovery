# FOFA Resource Discovery PoC Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a minimal offline-first FOFA resource discovery PoC that turns authorized seeds into normalized assets, exposed services, risk hints, and a manager-readable report draft.

**Architecture:** Implement a small Python package with focused modules for domain models, query planning, source client abstraction, normalization, deduplication, risk hinting, report building, and CLI orchestration. The PoC defaults to fixture data so tests and demos do not require SaaS credentials, while preserving an adapter boundary for a real FOFA client.

**Tech Stack:** Python 3.11+, pytest, standard library dataclasses/argparse/json.

---

## Task 1: Project Skeleton And Domain Models

**Files:**
- Create: `pyproject.toml`
- Create: `src/resource_discovery/__init__.py`
- Create: `src/resource_discovery/models.py`
- Create: `tests/test_models.py`

- [ ] Create package metadata with pytest configuration in `pyproject.toml`.
- [ ] Define enums and dataclasses for `DiscoverySeed`, `SourceQueryPlan`, `DiscoveredAsset`, `ExposedService`, `RiskHint`, `SourceEvidence`, and `ExposureReport`.
- [ ] Add serialization helpers returning plain dictionaries.
- [ ] Add tests proving model serialization preserves `source_query`, `raw_reference`, `confidence`, `first_seen`, `last_seen`, `evidence`, and `normalized_fields`.
- [ ] Run `python -m pytest tests/test_models.py -q`.
- [ ] Commit with `feat: add resource discovery domain models`.

## Task 2: Query Planner

**Files:**
- Create: `src/resource_discovery/query_planner.py`
- Create: `tests/test_query_planner.py`

- [ ] Implement FOFA query planning for `root_domain`, `organization_name`, and `ip_cidr` seeds.
- [ ] Reject unsupported seed types with a clear `ValueError`.
- [ ] Keep queries template-controlled; do not allow arbitrary SaaS query syntax from users.
- [ ] Add tests for the three supported seed types and unsupported input.
- [ ] Run `python -m pytest tests/test_query_planner.py -q`.
- [ ] Commit with `feat: add fofa query planner`.

## Task 3: Fixture Source Client And Normalizer

**Files:**
- Create: `src/resource_discovery/source_client.py`
- Create: `src/resource_discovery/normalizer.py`
- Create: `tests/fixtures/fofa_results.json`
- Create: `tests/test_normalizer.py`

- [ ] Implement `FixtureSourceClient` that loads FOFA-like results from JSON.
- [ ] Implement normalizer mapping fixture rows to assets, services, and source evidence.
- [ ] Preserve all required source tracing fields.
- [ ] Add tests proving fixture rows normalize into consistent asset/service/evidence models.
- [ ] Run `python -m pytest tests/test_normalizer.py -q`.
- [ ] Commit with `feat: normalize fofa fixture results`.

## Task 4: Deduplication And Risk Hints

**Files:**
- Create: `src/resource_discovery/deduplicator.py`
- Create: `src/resource_discovery/risk_hints.py`
- Create: `tests/test_deduplicator.py`
- Create: `tests/test_risk_hints.py`

- [ ] Implement deduplication by `domain_or_ip + port + protocol + service`.
- [ ] Merge source evidence instead of overwriting it.
- [ ] Implement risk hints for remote access, admin portal, test environment, database exposure, and middleware exposure.
- [ ] Keep risk hints as passive findings with `verification_required = true`.
- [ ] Add tests for duplicate service merging and each risk category.
- [ ] Run `python -m pytest tests/test_deduplicator.py tests/test_risk_hints.py -q`.
- [ ] Commit with `feat: add deduplication and passive risk hints`.

## Task 5: Report Builder And CLI Demo

**Files:**
- Create: `src/resource_discovery/report_builder.py`
- Create: `src/resource_discovery/cli.py`
- Create: `tests/test_report_builder.py`
- Create: `tests/test_cli.py`
- Create: `examples/seeds.json`

- [ ] Build `ExposureReport` with manager summary, key risks, recommendations, and technical appendix references.
- [ ] Add CLI command `python -m resource_discovery.cli --seeds examples/seeds.json --fixture tests/fixtures/fofa_results.json`.
- [ ] CLI prints JSON report to stdout and never requires FOFA credentials in fixture mode.
- [ ] Add tests for report content and CLI output.
- [ ] Run `python -m pytest tests/test_report_builder.py tests/test_cli.py -q`.
- [ ] Commit with `feat: add manager report demo cli`.

## Task 6: Full Verification And Documentation Update

**Files:**
- Create: `README.md`
- Modify: `docs/resource-discovery/poc-plan.md`

- [ ] Document how to run the offline PoC.
- [ ] Add a short note to `poc-plan.md` that the first executable PoC uses fixture mode before live FOFA credentials.
- [ ] Run `python -m pytest -q`.
- [ ] Run CLI demo and save no generated output by default.
- [ ] Commit with `docs: document fofa poc execution`.
