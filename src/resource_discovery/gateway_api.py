from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from .audit import AuditEvent, AuditLogger
from .discovery_workflow import DiscoveryWorkflowConfig, build_query_plans
from .errors import (
    invalid_discovery_strategy_error,
    profile_id_mismatch_error,
    query_plan_budget_exceeded_error,
    scope_out_of_bounds_error,
)
from .models import DiscoverySeed
from .query_planner import SUPPORTED_STRATEGIES
from .repositories import FileResultRepository, FileTaskRepository, ResultRepository, TaskRepository
from .scope_guard import TenantScopeProfile, validate_requested_scope
from .source_client import SourceClient
from .task_queue import InMemoryTaskQueue, TaskWorkItem


class DiscoveryGatewayApi:
    def __init__(
        self,
        profile: TenantScopeProfile,
        source_client: SourceClient,
        snapshot_dir: str | Path | None = None,
        task_repository: TaskRepository | None = None,
        result_repository: ResultRepository | None = None,
        queue: InMemoryTaskQueue | None = None,
        audit_logger: AuditLogger | None = None,
    ) -> None:
        self.profile = profile
        self.source_client = source_client
        if task_repository is None or result_repository is None:
            if snapshot_dir is None:
                raise ValueError("snapshot_dir is required when repositories are not provided")
            task_repository = task_repository or FileTaskRepository(snapshot_dir)
            result_repository = result_repository or FileResultRepository(Path(snapshot_dir) / "results")
        self.task_repository = task_repository
        self.result_repository = result_repository
        self.queue = queue if queue is not None else InMemoryTaskQueue()
        self.audit_logger = audit_logger

    def get_scope_profile(self) -> dict[str, Any]:
        self._record(
            "scope_profile_viewed",
            "-",
            {
                "profile_id": self.profile.profile_id,
                "allowed_engines": self.profile.allowed_engines,
            },
        )
        return self.profile.to_toolbox_summary()

    def create_task(self, request: dict[str, Any]) -> dict[str, Any]:
        task_id = request.get("task_id") or _generate_task_id()
        engines = request.get("engines") or ["fofa"]
        result_limit = int(request.get("result_limit", self.profile.limits.get("max_results_per_task", 100)))
        discovery_strategy = request.get("discovery_strategy") or "baseline"
        max_query_plans = int(self.profile.limits.get("max_queries_per_task", 30))
        self._record(
            "discovery_task_requested",
            task_id,
            {
                "profile_id": request.get("profile_id"),
                "engines": engines,
                "discovery_strategy": discovery_strategy,
                "requested_scope_keys": sorted((request.get("requested_scope") or {}).keys()),
                "result_limit": result_limit,
            },
        )
        if request.get("profile_id") != self.profile.profile_id:
            error = profile_id_mismatch_error(self.profile.profile_id, request.get("profile_id"))
            self._record(
                "discovery_scope_rejected",
                task_id,
                {
                    "reason": "profile_id_mismatch",
                    "rejected_count": 0,
                },
            )
            return {
                "status": "rejected",
                "accepted_scope": {},
                "rejected_scope": [],
                "errors": [error.to_dict()],
            }
        if discovery_strategy not in SUPPORTED_STRATEGIES:
            error = invalid_discovery_strategy_error(discovery_strategy)
            self._record(
                "discovery_scope_rejected",
                task_id,
                {
                    "reason": "invalid_discovery_strategy",
                    "discovery_strategy": discovery_strategy,
                },
            )
            return {
                "status": "rejected",
                "accepted_scope": {},
                "rejected_scope": [],
                "errors": [error.to_dict()],
            }
        scope_result = validate_requested_scope(
            self.profile,
            request.get("requested_scope") or {},
            engines=engines,
            result_limit=result_limit,
        )
        if scope_result.rejected_scope:
            error = scope_out_of_bounds_error(self.profile.profile_id, scope_result.rejected_scope)
            self._record(
                "discovery_scope_rejected",
                task_id,
                {
                    "reason": "scope_out_of_bounds",
                    "rejected_count": len(scope_result.rejected_scope),
                },
            )
            return {
                "status": "rejected",
                "accepted_scope": scope_result.accepted_scope,
                "rejected_scope": scope_result.rejected_scope,
                "errors": [error.to_dict()],
            }

        seeds = seeds_from_scope(scope_result.accepted_scope, self.profile.authorization_note)
        plans = build_query_plans(
            task_id,
            seeds,
            DiscoveryWorkflowConfig(
                strategy=discovery_strategy,
                max_query_plans=10_000,
                page_limit=1,
                result_limit=result_limit,
            ),
        )
        if len(plans) > max_query_plans:
            error = query_plan_budget_exceeded_error(max_query_plans, len(plans))
            self._record(
                "discovery_scope_rejected",
                task_id,
                {
                    "reason": "query_plan_budget_exceeded",
                    "discovery_strategy": discovery_strategy,
                    "planned_queries": len(plans),
                    "max_query_plans": max_query_plans,
                },
            )
            return {
                "status": "rejected",
                "accepted_scope": scope_result.accepted_scope,
                "rejected_scope": [],
                "errors": [error.to_dict()],
            }
        payload = _queued_task_payload(
            tenant_id=self.profile.tenant_id,
            task_id=task_id,
            accepted_scope=scope_result.accepted_scope,
            engines=engines,
            result_limit=result_limit,
            authorization_note=self.profile.authorization_note,
            discovery_strategy=discovery_strategy,
            max_query_plans=max_query_plans,
        )
        self.task_repository.create(payload)
        self.queue.enqueue(TaskWorkItem(tenant_id=self.profile.tenant_id, task_id=task_id))
        self._record(
            "discovery_task_queued",
            task_id,
            {
                "accepted_scope_keys": sorted(scope_result.accepted_scope.keys()),
                "discovery_strategy": discovery_strategy,
                "planned_queries": len(plans),
            },
        )
        return {
            "task_id": task_id,
            "status": "queued",
            "accepted_scope": scope_result.accepted_scope,
            "rejected_scope": [],
            "query_plan_summary": {
                "engines": engines,
                "strategy": discovery_strategy,
                "planned_queries": len(plans),
            },
            "status_url": f"/api/v1/discovery/tasks/{task_id}",
            "result_url": f"/api/v1/discovery/tasks/{task_id}/results",
        }

    def get_task(self, task_id: str) -> dict[str, Any]:
        payload = self.task_repository.load(self.profile.tenant_id, task_id)
        task = payload["task"]
        return {
            "task_id": task["task_id"],
            "tenant_id": task["tenant_id"],
            "status": _status_value(task["status"]),
            "engine_status": [
                {
                    "engine": "fofa",
                    "status": _status_value(task["status"]),
                    "result_count": task.get("quota_usage", {}).get("result_count", 0),
                }
            ],
            "errors": task.get("errors", []),
        }

    def get_results(
        self,
        task_id: str,
        cursor: str | None = None,
        limit: int = 100,
        result_type: str = "assets",
    ) -> dict[str, Any]:
        payload = self.result_repository.load_results(
            self.profile.tenant_id,
            task_id,
            cursor,
            limit,
            result_type=result_type,
        )
        self._record(
            "discovery_results_fetched",
            task_id,
            {
                "result_type": result_type,
                "cursor": cursor,
                "limit": limit,
            },
        )
        return payload

    def _record(self, event_type: str, task_id: str, details: dict[str, Any]) -> None:
        if self.audit_logger is None:
            return
        self.audit_logger.record(
            AuditEvent(
                event_type=event_type,
                tenant_id=self.profile.tenant_id,
                task_id=task_id,
                details=details,
            )
        )


def seeds_from_scope(scope: dict[str, list[str]], authorization_note: str | None) -> list[DiscoverySeed]:
    seeds: list[DiscoverySeed] = []
    for value in scope.get("root_domains", []):
        seeds.append(_seed(len(seeds) + 1, "root_domain", value, authorization_note))
    for value in scope.get("domains", []):
        seeds.append(_seed(len(seeds) + 1, "root_domain", value, authorization_note))
    for value in scope.get("ip_cidrs", []):
        seeds.append(_seed(len(seeds) + 1, "ip_cidr", value, authorization_note))
    for value in scope.get("org_names", []):
        seeds.append(_seed(len(seeds) + 1, "organization_name", value, authorization_note))
    return seeds


def _seed(index: int, seed_type: str, value: str, authorization_note: str | None) -> DiscoverySeed:
    return DiscoverySeed(
        seed_id=f"seed_{index:03d}",
        type=seed_type,
        value=value,
        authorization_note=authorization_note or "Tenant scope profile authorization.",
    )


def _status_value(status: Any) -> str:
    return getattr(status, "value", status)


def _generate_task_id() -> str:
    return f"dt_{uuid4().hex[:16]}"


def _queued_task_payload(
    tenant_id: str,
    task_id: str,
    accepted_scope: dict[str, list[str]],
    engines: list[str],
    result_limit: int,
    authorization_note: str | None,
    discovery_strategy: str = "baseline",
    max_query_plans: int = 30,
) -> dict[str, Any]:
    return {
        "task": {
            "tenant_id": tenant_id,
            "task_id": task_id,
            "status": "queued",
            "mode": "async_task",
            "quota_usage": {},
            "errors": [],
        },
        "request": {
            "accepted_scope": accepted_scope,
            "engines": engines,
            "result_limit": result_limit,
            "discovery_strategy": discovery_strategy,
            "max_query_plans": max_query_plans,
        },
        "authorization_note": authorization_note,
        "snapshot": {
            "summary": {},
            "analysis": {"analysis_mode": "rules_only", "llm_enabled": False},
        },
    }
