from __future__ import annotations

from typing import Any

from .audit import AuditEvent, AuditLogger
from .execution import run_discovery_from_seeds
from .gateway_api import seeds_from_scope
from .repositories import ResultRepository, TaskRepository
from .source_client import SourceClient
from .task_queue import InMemoryTaskQueue


class TaskWorker:
    def __init__(
        self,
        task_repository: TaskRepository,
        result_repository: ResultRepository,
        queue: InMemoryTaskQueue,
        source_client: SourceClient,
        audit_logger: AuditLogger | None = None,
        max_attempts: int = 3,
        retry_delay_seconds: float = 30.0,
    ) -> None:
        self.task_repository = task_repository
        self.result_repository = result_repository
        self.queue = queue
        self.source_client = source_client
        self.audit_logger = audit_logger
        self.max_attempts = max_attempts
        self.retry_delay_seconds = retry_delay_seconds

    def run_once(self) -> dict[str, Any]:
        item = self.queue.dequeue()
        if item is None:
            return {"processed": False}
        task_payload = self.task_repository.load(item.tenant_id, item.task_id)
        self._mark_status(task_payload, "running")
        self.task_repository.update(task_payload)
        self._record("discovery_task_started", item.tenant_id, item.task_id, {})
        try:
            result_payload = self._execute(task_payload)
        except Exception as exc:
            reason = str(exc)
            task_payload["task"]["status"] = "failed"
            task_payload["task"]["errors"] = [
                {
                    "source": "fofa",
                    "query_type": "unknown",
                    "source_query": "",
                    "message": reason,
                    "recoverable": True,
                }
            ]
            self.task_repository.update(task_payload)
            attempts = getattr(self.queue, "attempts", None)
            if attempts is None and hasattr(self.queue, "status"):
                try:
                    attempts = self.queue.status(item.tenant_id, item.task_id).attempts
                except FileNotFoundError:
                    attempts = 0
            attempts = int(attempts or 0)
            if attempts + 1 < self.max_attempts and hasattr(self.queue, "mark_retry"):
                try:
                    self.queue.mark_retry(item, reason, delay_seconds=self.retry_delay_seconds)
                except TypeError:
                    self.queue.mark_retry(item, reason)
                self._record(
                    "discovery_task_retry_scheduled",
                    item.tenant_id,
                    item.task_id,
                    {"message": reason, "attempt": attempts + 1, "max_attempts": self.max_attempts},
                )
                return {"processed": True, "task_id": item.task_id, "status": "retrying"}
            if hasattr(self.queue, "mark_failed"):
                self.queue.mark_failed(item, reason)
            self._record(
                "discovery_task_failed",
                item.tenant_id,
                item.task_id,
                {"message": reason, "recoverable": True},
            )
            return {"processed": True, "task_id": item.task_id, "status": "failed"}
        if _status_value(result_payload["task"]["status"]) == "failed" and _has_recoverable_error(result_payload):
            reason = _first_error_message(result_payload)
            self.task_repository.update(result_payload)
            if self._retry_or_fail(item, reason):
                self._record(
                    "discovery_task_retry_scheduled",
                    item.tenant_id,
                    item.task_id,
                    {"message": reason, "max_attempts": self.max_attempts},
                )
                return {"processed": True, "task_id": item.task_id, "status": "retrying"}
            self._record(
                "discovery_task_failed",
                item.tenant_id,
                item.task_id,
                {"message": reason, "recoverable": True},
            )
            return {"processed": True, "task_id": item.task_id, "status": "failed"}
        self.task_repository.update(result_payload)
        self.result_repository.save_results(item.tenant_id, item.task_id, result_payload)
        if hasattr(self.queue, "mark_done"):
            self.queue.mark_done(item)
        self._record(
            "discovery_task_completed",
            item.tenant_id,
            item.task_id,
            {
                "status": result_payload["task"]["status"],
                "result_count": result_payload["task"].get("quota_usage", {}).get("result_count", 0),
            },
        )
        return {
            "processed": True,
            "task_id": item.task_id,
            "status": result_payload["task"]["status"],
        }

    def _execute(self, task_payload: dict[str, Any]) -> dict[str, Any]:
        task = task_payload["task"]
        request = task_payload.get("request", {})
        seeds = seeds_from_scope(
            request.get("accepted_scope", {}),
            task_payload.get("authorization_note") or "Tenant scope profile authorization.",
        )
        return run_discovery_from_seeds(
            task_id=task["task_id"],
            tenant_id=task["tenant_id"],
            seeds=seeds,
            mode="fixture",
            source_client=self.source_client,
            page_limit=1,
            result_limit=int(request.get("result_limit", 100)),
            discovery_strategy=request.get("discovery_strategy", "baseline"),
            max_query_plans=int(request.get("max_query_plans", 30)),
            authorized_scope=request.get("accepted_scope", {}),
        )

    def _mark_status(self, task_payload: dict[str, Any], status: str) -> None:
        task_payload["task"]["status"] = status

    def _record(self, event_type: str, tenant_id: str, task_id: str, details: dict[str, Any]) -> None:
        if self.audit_logger is None:
            return
        self.audit_logger.record(
            AuditEvent(
                event_type=event_type,
                tenant_id=tenant_id,
                task_id=task_id,
                details=details,
            )
        )

    def _retry_or_fail(self, item: Any, reason: str) -> bool:
        attempts = getattr(self.queue, "attempts", None)
        if attempts is None and hasattr(self.queue, "status"):
            try:
                attempts = self.queue.status(item.tenant_id, item.task_id).attempts
            except FileNotFoundError:
                attempts = 0
        attempts = int(attempts or 0)
        if attempts + 1 < self.max_attempts and hasattr(self.queue, "mark_retry"):
            try:
                self.queue.mark_retry(item, reason, delay_seconds=self.retry_delay_seconds)
            except TypeError:
                self.queue.mark_retry(item, reason)
            return True
        if hasattr(self.queue, "mark_failed"):
            self.queue.mark_failed(item, reason)
        return False


def _status_value(status: Any) -> str:
    return getattr(status, "value", status)


def _has_recoverable_error(payload: dict[str, Any]) -> bool:
    return any(error.get("recoverable") for error in payload["task"].get("errors", []))


def _first_error_message(payload: dict[str, Any]) -> str:
    errors = payload["task"].get("errors", [])
    if not errors:
        return "recoverable task failure"
    return str(errors[0].get("message") or errors[0].get("code") or "recoverable task failure")
