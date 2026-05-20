from __future__ import annotations

import json
from pathlib import Path

from .analysis import LlmRiskEnricher, apply_analysis
from .analysis_config import TenantAnalysisConfig
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
    fofa_base_url: str = "https://fofa.info/api/v1/search/all",
    allow_live_fofa: bool = False,
    source_client: SourceClient | None = None,
    page_limit: int = 10,
    result_limit: int = 1000,
    analysis_mode: str = "rules_only",
    llm_enricher: LlmRiskEnricher | None = None,
    web_search_enabled: bool = False,
    data_sharing_level: str = "none",
    llm_provider: str | None = None,
    llm_model: str | None = None,
    llm_authorization_id: str | None = None,
    tenant_analysis_config: TenantAnalysisConfig | None = None,
) -> dict:
    payload = json.loads(Path(seeds_path).read_text(encoding="utf-8"))
    task_id = payload.get("task_id", "dt_poc_001")
    tenant_id = payload.get("tenant_id", "tenant_poc")
    seeds = [DiscoverySeed(**seed) for seed in payload["seeds"]]
    return run_discovery_from_seeds(
        task_id=task_id,
        tenant_id=tenant_id,
        seeds=seeds,
        mode=mode,
        fixture_path=fixture_path,
        fofa_email=fofa_email,
        fofa_key=fofa_key,
        fofa_base_url=fofa_base_url,
        allow_live_fofa=allow_live_fofa,
        source_client=source_client,
        page_limit=page_limit,
        result_limit=result_limit,
        analysis_mode=analysis_mode,
        llm_enricher=llm_enricher,
        web_search_enabled=web_search_enabled,
        data_sharing_level=data_sharing_level,
        llm_provider=llm_provider,
        llm_model=llm_model,
        llm_authorization_id=llm_authorization_id,
        tenant_analysis_config=tenant_analysis_config,
    )


def run_discovery_from_seeds(
    task_id: str,
    tenant_id: str,
    seeds: list[DiscoverySeed],
    mode: str = "fixture",
    fixture_path: str | Path | None = None,
    fofa_email: str | None = None,
    fofa_key: str | None = None,
    fofa_base_url: str = "https://fofa.info/api/v1/search/all",
    allow_live_fofa: bool = False,
    source_client: SourceClient | None = None,
    page_limit: int = 10,
    result_limit: int = 1000,
    analysis_mode: str = "rules_only",
    llm_enricher: LlmRiskEnricher | None = None,
    web_search_enabled: bool = False,
    data_sharing_level: str = "none",
    llm_provider: str | None = None,
    llm_model: str | None = None,
    llm_authorization_id: str | None = None,
    tenant_analysis_config: TenantAnalysisConfig | None = None,
) -> dict:
    analysis_options = _resolve_analysis_options(
        tenant_id=tenant_id,
        analysis_mode=analysis_mode,
        web_search_enabled=web_search_enabled,
        data_sharing_level=data_sharing_level,
        llm_provider=llm_provider,
        llm_model=llm_model,
        llm_authorization_id=llm_authorization_id,
        tenant_analysis_config=tenant_analysis_config,
    )
    validate_seeds(seeds)
    plans = plan_fofa_queries(task_id, seeds, page_limit=page_limit, result_limit=result_limit)
    enforce_plan_quota(plans)

    if mode == "dry-run":
        return _dry_run_payload(plans)
    if mode == "fixture":
        if fixture_path is None and source_client is None:
            raise ValueError("fixture_path is required in fixture mode")
        return _execute_with_client(
            mode=mode,
            task_id=task_id,
            tenant_id=tenant_id,
            plans=plans,
            client=source_client or FixtureSourceClient(fixture_path),
            analysis_mode=analysis_options["analysis_mode"],
            llm_enricher=llm_enricher,
            web_search_enabled=analysis_options["web_search_enabled"],
            data_sharing_level=analysis_options["data_sharing_level"],
            llm_provider=analysis_options["llm_provider"],
            llm_model=analysis_options["llm_model"],
            llm_authorization_id=analysis_options["llm_authorization_id"],
        )
    if mode == "live":
        if not allow_live_fofa:
            raise LiveExecutionDisabled("Live FOFA execution must be explicitly enabled")
        if not fofa_email or not fofa_key:
            if not fofa_key:
                raise LiveExecutionDisabled("Live FOFA execution requires FOFA credentials")
        if source_client is not None:
            return _execute_with_client(
                mode=mode,
                task_id=task_id,
                tenant_id=tenant_id,
                plans=plans,
                client=source_client,
                analysis_mode=analysis_options["analysis_mode"],
                llm_enricher=llm_enricher,
                web_search_enabled=analysis_options["web_search_enabled"],
                data_sharing_level=analysis_options["data_sharing_level"],
                llm_provider=analysis_options["llm_provider"],
                llm_model=analysis_options["llm_model"],
                llm_authorization_id=analysis_options["llm_authorization_id"],
            )
        api_client = FofaApiClient(email=fofa_email, key=fofa_key or "", base_url=fofa_base_url)
        return _execute_with_client(
            mode=mode,
            task_id=task_id,
            tenant_id=tenant_id,
            plans=plans,
            client=FofaSourceClient(api_client),
            analysis_mode=analysis_options["analysis_mode"],
            llm_enricher=llm_enricher,
            web_search_enabled=analysis_options["web_search_enabled"],
            data_sharing_level=analysis_options["data_sharing_level"],
            llm_provider=analysis_options["llm_provider"],
            llm_model=analysis_options["llm_model"],
            llm_authorization_id=analysis_options["llm_authorization_id"],
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
    analysis_mode: str = "rules_only",
    llm_enricher: LlmRiskEnricher | None = None,
    web_search_enabled: bool = False,
    data_sharing_level: str = "none",
    llm_provider: str | None = None,
    llm_model: str | None = None,
    llm_authorization_id: str | None = None,
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
                    recoverable=getattr(exc, "recoverable", True),
                    code=getattr(exc, "code", None),
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
    risk_hint_dicts, analysis = apply_analysis(
        risk_hint_dicts,
        analysis_mode=analysis_mode,
        llm_enricher=llm_enricher,
        web_search_enabled=web_search_enabled,
        data_sharing_level=data_sharing_level,
        llm_provider=llm_provider,
        llm_model=llm_model,
        llm_authorization_id=llm_authorization_id,
    )
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
        "analysis": analysis,
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


def _resolve_analysis_options(
    tenant_id: str,
    analysis_mode: str,
    web_search_enabled: bool,
    data_sharing_level: str,
    llm_provider: str | None,
    llm_model: str | None,
    llm_authorization_id: str | None,
    tenant_analysis_config: TenantAnalysisConfig | None,
) -> dict:
    if tenant_analysis_config is not None:
        return tenant_analysis_config.resolve_options(tenant_id)
    return {
        "analysis_mode": analysis_mode,
        "web_search_enabled": web_search_enabled,
        "data_sharing_level": data_sharing_level,
        "llm_provider": llm_provider,
        "llm_model": llm_model,
        "llm_authorization_id": llm_authorization_id,
    }
