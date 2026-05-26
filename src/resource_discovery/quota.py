from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class TenantQuotaPolicy:
    max_tasks_per_day: int
    max_provider_queries_per_day: int
    max_concurrent_tasks: int


@dataclass(frozen=True)
class QuotaDecision:
    allowed: bool
    code: str


class QuotaExceeded(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def check_task_quota(
    *,
    tenant_id: str,
    policy: TenantQuotaPolicy,
    current_daily_tasks: int,
    current_daily_provider_queries: int,
    current_running_tasks: int,
    planned_provider_queries: int,
    now: datetime,
) -> QuotaDecision:
    if current_daily_tasks >= policy.max_tasks_per_day:
        raise QuotaExceeded(
            "tenant_daily_task_quota_exceeded",
            f"Tenant {tenant_id} has reached the daily task quota.",
        )
    if current_running_tasks >= policy.max_concurrent_tasks:
        raise QuotaExceeded(
            "tenant_concurrent_task_quota_exceeded",
            f"Tenant {tenant_id} has reached the concurrent task quota.",
        )
    if current_daily_provider_queries + planned_provider_queries > policy.max_provider_queries_per_day:
        raise QuotaExceeded(
            "provider_daily_query_quota_exceeded",
            f"Tenant {tenant_id} has reached the daily provider query quota.",
        )
    return QuotaDecision(allowed=True, code="")
