from datetime import datetime, timezone

import pytest

from resource_discovery.quota import QuotaDecision, QuotaExceeded, TenantQuotaPolicy, check_task_quota


def test_task_quota_allows_under_daily_limit():
    decision = check_task_quota(
        tenant_id="tenant_a",
        policy=TenantQuotaPolicy(max_tasks_per_day=10, max_provider_queries_per_day=100, max_concurrent_tasks=2),
        current_daily_tasks=3,
        current_daily_provider_queries=12,
        current_running_tasks=1,
        planned_provider_queries=5,
        now=datetime.now(timezone.utc),
    )

    assert decision == QuotaDecision(allowed=True, code="")


def test_task_quota_rejects_daily_task_limit():
    with pytest.raises(QuotaExceeded) as exc:
        check_task_quota(
            tenant_id="tenant_a",
            policy=TenantQuotaPolicy(max_tasks_per_day=3, max_provider_queries_per_day=100, max_concurrent_tasks=2),
            current_daily_tasks=3,
            current_daily_provider_queries=12,
            current_running_tasks=1,
            planned_provider_queries=5,
            now=datetime.now(timezone.utc),
        )

    assert exc.value.code == "tenant_daily_task_quota_exceeded"


def test_task_quota_rejects_provider_query_limit():
    with pytest.raises(QuotaExceeded) as exc:
        check_task_quota(
            tenant_id="tenant_a",
            policy=TenantQuotaPolicy(max_tasks_per_day=10, max_provider_queries_per_day=15, max_concurrent_tasks=2),
            current_daily_tasks=3,
            current_daily_provider_queries=12,
            current_running_tasks=1,
            planned_provider_queries=5,
            now=datetime.now(timezone.utc),
        )

    assert exc.value.code == "provider_daily_query_quota_exceeded"


def test_task_quota_rejects_concurrent_task_limit():
    with pytest.raises(QuotaExceeded) as exc:
        check_task_quota(
            tenant_id="tenant_a",
            policy=TenantQuotaPolicy(max_tasks_per_day=10, max_provider_queries_per_day=100, max_concurrent_tasks=2),
            current_daily_tasks=1,
            current_daily_provider_queries=1,
            current_running_tasks=2,
            planned_provider_queries=1,
            now=datetime.now(timezone.utc),
        )

    assert exc.value.code == "tenant_concurrent_task_quota_exceeded"
