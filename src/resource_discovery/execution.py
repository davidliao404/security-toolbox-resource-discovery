from __future__ import annotations

import json
from pathlib import Path

from .deduplicator import deduplicate_assets, deduplicate_services
from .fofa_client import FofaApiClient
from .models import DiscoverySeed, SourceQueryPlan
from .normalizer import normalize_fofa_results
from .query_planner import plan_fofa_queries
from .report_builder import build_exposure_report
from .remediation import build_remediation_plan
from .risk_hints import generate_risk_hints
from .safety import enforce_plan_quota, validate_seeds
from .source_client import FixtureSourceClient, FofaSourceClient, SourceClient
from .task_state import build_report_snapshot, build_task_envelope
from .models import TaskError


class LiveExecutionDisabled(RuntimeError):
    """Raised when live SaaS execution is requested without explicit enablement."""


def run_discovery(
    seeds_path: str | Path,
    mode: str = "fixture",
    fixture_path: str | Path | None = None,
    fofa_email: str | None = None,
    fofa_key: str | None = None,
    allow_live_fofa: bool = False,
    source_client: SourceClient | None = None,
) -> dict:
    payload = json.loads(Path(seeds_path).read_text(encoding="utf-8"))
    task_id = payload.get("task_id", "dt_poc_001")
    tenant_id = payload.get("tenant_id", "tenant_poc")
    seeds = [DiscoverySeed(**seed) for seed in payload["seeds"]]
    validate_seeds(seeds)
    plans = plan_fofa_queries(task_id, seeds)
    enforce_plan_quota(plans)

    if mode == "dry-run":
        return _dry_run_payload(plans)
    if mode == "fixture":
        if fixture_path is None:
            raise ValueError("fixture_path is required in fixture mode")
        return _execute_with_client(
            mode=mode,
            task_id=task_id,
            tenant_id=tenant_id,
            plans=plans,
            client=source_client or FixtureSourceClient(fixture_path),
        )
    if mode == "live":
        if not allow_live_fofa:
            raise LiveExecutionDisabled("Live FOFA execution must be explicitly enabled")
        if not fofa_email or not fofa_key:
            raise LiveExecutionDisabled("Live FOFA execution requires FOFA credentials")
        api_client = FofaApiClient(email=fofa_email, key=fofa_key)
        return _execute_with_client(
            mode=mode,
            task_id=task_id,
            tenant_id=tenant_id,
            plans=plans,
            client=FofaSourceClient(api_client),
        )
    raise ValueError(f"Unsupported execution mode: {mode}")


def _dry_run_payload(plans: list[SourceQueryPlan]) -> dict:
    return {
        "mode": "dry-run",
        "live_api_enabled": False,
        "query_plans": [plan.to_dict() for plan in plans],
        "report": None,
        "assets": [],
        "services": [],
        "risk_hints": [],
        "source_evidence": [],
    }


def _execute_with_client(
    mode: str,
    task_id: str,
    tenant_id: str,
    plans: list[SourceQueryPlan],
    client: SourceClient,
) -> dict:
    assets = []
    services = []
    evidences = []
    errors: list[TaskError] = []
    completed_queries = 0
    for plan in plans:
        try:
            rows = client.fetch(plan)
        except Exception as exc:
            errors.append(
                TaskError(
                    source=plan.source,
                    query_type=plan.query_type,
                    source_query=plan.source_query,
                    message=str(exc),
                    recoverable=True,
                )
            )
            continue
        completed_queries += 1
        batch = normalize_fofa_results(task_id, plan, rows)
        assets.extend(batch.assets)
        services.extend(batch.services)
        evidences.extend(batch.evidences)

    deduped_assets = deduplicate_assets(assets)
    deduped_services = deduplicate_services(services)
    risk_hints = generate_risk_hints(task_id, deduped_services)
    report = build_exposure_report(task_id, tenant_id, deduped_assets, deduped_services, risk_hints)
    risk_hint_dicts = [risk.to_dict() for risk in risk_hints]
    remediation = build_remediation_plan(risk_hint_dicts)

    task = build_task_envelope(
        task_id=task_id,
        tenant_id=tenant_id,
        mode=mode,
        plans=plans,
        completed_queries=completed_queries,
        failed_errors=errors,
        result_count=len(evidences),
    )
    payload = {
        "mode": mode,
        "live_api_enabled": mode == "live",
        "task": task.to_dict(),
        "report": report.to_dict(),
        "assets": [asset.to_dict() for asset in deduped_assets],
        "services": [service.to_dict() for service in deduped_services],
        "risk_hints": risk_hint_dicts,
        "remediation": remediation,
        "source_evidence": [evidence.to_dict() for evidence in evidences],
    }
    payload["snapshot"] = build_report_snapshot(payload)
    return payload
