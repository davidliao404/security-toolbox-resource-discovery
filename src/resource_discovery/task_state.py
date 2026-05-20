from __future__ import annotations

from .models import QuotaUsage, SourceQueryPlan, TaskEnvelope, TaskError, TaskStatus


def build_task_envelope(
    task_id: str,
    tenant_id: str,
    mode: str,
    plans: list[SourceQueryPlan],
    completed_queries: int,
    failed_errors: list[TaskError],
    result_count: int,
) -> TaskEnvelope:
    status = _status_for(completed_queries, failed_errors)
    return TaskEnvelope(
        task_id=task_id,
        tenant_id=tenant_id,
        mode=mode,
        status=status,
        quota_usage=QuotaUsage(
            planned_queries=len(plans),
            completed_queries=completed_queries,
            failed_queries=len(failed_errors),
            planned_pages=sum(plan.page_limit for plan in plans),
            consumed_pages=completed_queries,
            result_count=result_count,
        ),
        errors=failed_errors,
    )


def build_report_snapshot(payload: dict) -> dict:
    return {
        "task": payload["task"],
        "summary": {
            "asset_count": len(payload.get("assets", [])),
            "service_count": len(payload.get("services", [])),
            "risk_hint_count": len(payload.get("risk_hints", [])),
            "source_evidence_count": len(payload.get("source_evidence", [])),
        },
        "analysis": payload.get("analysis"),
        "report": payload.get("report"),
    }


def _status_for(completed_queries: int, errors: list[TaskError]) -> TaskStatus:
    if errors and completed_queries > 0:
        return TaskStatus.PARTIAL_SUCCESS
    if errors:
        return TaskStatus.FAILED
    return TaskStatus.SUCCESS
