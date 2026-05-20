from __future__ import annotations

from typing import Any

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
    ) -> None:
        self.task_repository = task_repository
        self.result_repository = result_repository
        self.queue = queue
        self.source_client = source_client

    def run_once(self) -> dict[str, Any]:
        item = self.queue.dequeue()
        if item is None:
            return {"processed": False}
        task_payload = self.task_repository.load(item.tenant_id, item.task_id)
        self._mark_status(task_payload, "running")
        self.task_repository.update(task_payload)
        try:
            result_payload = self._execute(task_payload)
        except Exception as exc:
            task_payload["task"]["status"] = "failed"
            task_payload["task"]["errors"] = [
                {
                    "source": "fofa",
                    "query_type": "unknown",
                    "source_query": "",
                    "message": str(exc),
                    "recoverable": True,
                }
            ]
            self.task_repository.update(task_payload)
            return {"processed": True, "task_id": item.task_id, "status": "failed"}
        self.task_repository.update(result_payload)
        self.result_repository.save_results(item.tenant_id, item.task_id, result_payload)
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
        )

    def _mark_status(self, task_payload: dict[str, Any], status: str) -> None:
        task_payload["task"]["status"] = status
