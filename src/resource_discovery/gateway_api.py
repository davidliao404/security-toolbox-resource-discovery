from __future__ import annotations

from pathlib import Path
from typing import Any

from .execution import run_discovery_from_seeds
from .models import DiscoverySeed
from .query_planner import plan_fofa_queries
from .scope_guard import TenantScopeProfile, validate_requested_scope
from .source_client import SourceClient
from .task_store import FileTaskStore


class DiscoveryGatewayApi:
    def __init__(
        self,
        profile: TenantScopeProfile,
        source_client: SourceClient,
        snapshot_dir: str | Path,
    ) -> None:
        self.profile = profile
        self.source_client = source_client
        self.store = FileTaskStore(snapshot_dir)

    def get_scope_profile(self) -> dict[str, Any]:
        return self.profile.to_toolbox_summary()

    def create_task(self, request: dict[str, Any]) -> dict[str, Any]:
        if request.get("profile_id") != self.profile.profile_id:
            return {
                "status": "rejected",
                "reason": "profile_id_mismatch",
                "accepted_scope": {},
                "rejected_scope": [],
            }
        engines = request.get("engines") or ["fofa"]
        result_limit = int(request.get("result_limit", self.profile.limits.get("max_results_per_task", 100)))
        scope_result = validate_requested_scope(
            self.profile,
            request.get("requested_scope") or {},
            engines=engines,
            result_limit=result_limit,
        )
        if scope_result.rejected_scope:
            return {
                "status": "rejected",
                "accepted_scope": scope_result.accepted_scope,
                "rejected_scope": scope_result.rejected_scope,
            }

        task_id = request.get("task_id") or "dt_api_001"
        seeds = _seeds_from_scope(scope_result.accepted_scope, self.profile.authorization_note)
        plans = plan_fofa_queries(task_id, seeds, page_limit=1, result_limit=result_limit)
        payload = run_discovery_from_seeds(
            task_id=task_id,
            tenant_id=self.profile.tenant_id,
            seeds=seeds,
            mode="fixture",
            source_client=self.source_client,
            page_limit=1,
            result_limit=result_limit,
        )
        self.store.save(payload)
        return {
            "task_id": task_id,
            "status": _status_value(payload["task"]["status"]),
            "accepted_scope": scope_result.accepted_scope,
            "rejected_scope": [],
            "query_plan_summary": {
                "engines": engines,
                "planned_queries": len(plans),
            },
            "status_url": f"/api/v1/discovery/tasks/{task_id}",
            "result_url": f"/api/v1/discovery/tasks/{task_id}/results",
        }

    def get_task(self, task_id: str) -> dict[str, Any]:
        payload = self.store.load(self.profile.tenant_id, task_id)
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

    def get_results(self, task_id: str, cursor: str | None = None, limit: int = 100) -> dict[str, Any]:
        payload = self.store.load(self.profile.tenant_id, task_id)
        start = int(cursor or 0)
        end = start + limit
        assets = payload.get("assets", [])[start:end]
        next_cursor = str(end) if end < len(payload.get("assets", [])) else None
        return {
            "task_id": task_id,
            "assets": assets,
            "services": payload.get("services", []),
            "source_evidence": payload.get("source_evidence", []),
            "page": {"next_cursor": next_cursor},
        }


def _seeds_from_scope(scope: dict[str, list[str]], authorization_note: str | None) -> list[DiscoverySeed]:
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
