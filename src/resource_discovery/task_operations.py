from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


TERMINAL_STATUSES = {"success", "partial_success", "failed", "cancelled"}


class TaskOperationError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def cancel_task(task_repository: Any, tenant_id: str, task_id: str, actor: str) -> dict[str, Any]:
    payload = task_repository.load(tenant_id, task_id)
    status = str(payload["task"].get("status", ""))
    if status in TERMINAL_STATUSES:
        raise TaskOperationError("task_not_cancellable", f"Task {task_id} is already terminal: {status}")
    payload["task"]["status"] = "cancelled"
    payload["task"]["cancelled_by"] = actor
    payload["task"]["cancelled_at"] = datetime.now(timezone.utc).isoformat()
    task_repository.update(payload)
    return {"tenant_id": tenant_id, "task_id": task_id, "status": "cancelled"}


def list_dead_letters(queue: Any) -> list[dict[str, Any]]:
    items = queue.dead_letter_items() if hasattr(queue, "dead_letter_items") else []
    normalized: list[dict[str, Any]] = []
    for item in items:
        normalized.append(
            {
                "tenant_id": item.get("tenant_id", ""),
                "task_id": item.get("task_id", ""),
                "attempts": int(item.get("attempts") or 0),
                "last_error": item.get("last_error", ""),
                "updated_at": item.get("updated_at", ""),
            }
        )
    return normalized
