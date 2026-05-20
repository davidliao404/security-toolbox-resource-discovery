from resource_discovery.repositories import FileResultRepository, FileTaskRepository
from resource_discovery.source_client import FixtureSourceClient
from resource_discovery.task_queue import InMemoryTaskQueue, TaskWorkItem
from resource_discovery.worker import TaskWorker


def _queued_payload():
    return {
        "task": {
            "tenant_id": "tenant_poc",
            "task_id": "dt_worker_001",
            "status": "queued",
            "mode": "fixture",
            "quota_usage": {},
            "errors": [],
        },
        "request": {
            "accepted_scope": {"root_domains": ["example.org"]},
            "engines": ["fofa"],
            "result_limit": 50,
        },
        "snapshot": {"summary": {}, "analysis": {"analysis_mode": "rules_only"}},
    }


def test_task_worker_run_once_executes_queued_task(tmp_path):
    task_repo = FileTaskRepository(tmp_path / "tasks")
    result_repo = FileResultRepository(tmp_path / "results")
    task_repo.create(_queued_payload())
    queue = InMemoryTaskQueue()
    queue.enqueue(TaskWorkItem(tenant_id="tenant_poc", task_id="dt_worker_001"))
    worker = TaskWorker(
        task_repository=task_repo,
        result_repository=result_repo,
        queue=queue,
        source_client=FixtureSourceClient("tests/fixtures/fofa_results.json"),
    )

    result = worker.run_once()

    loaded = task_repo.load("tenant_poc", "dt_worker_001")
    results = result_repo.load_results("tenant_poc", "dt_worker_001", cursor=None, limit=10)
    assert result == {"processed": True, "task_id": "dt_worker_001", "status": "success"}
    assert loaded["task"]["status"] == "success"
    assert results["assets"]


def test_task_worker_run_once_marks_task_failed_on_exception(tmp_path):
    class FailingClient:
        def fetch(self, plan):
            raise RuntimeError("provider unavailable")

    task_repo = FileTaskRepository(tmp_path / "tasks")
    result_repo = FileResultRepository(tmp_path / "results")
    task_repo.create(_queued_payload())
    queue = InMemoryTaskQueue()
    queue.enqueue(TaskWorkItem(tenant_id="tenant_poc", task_id="dt_worker_001"))
    worker = TaskWorker(
        task_repository=task_repo,
        result_repository=result_repo,
        queue=queue,
        source_client=FailingClient(),
    )

    result = worker.run_once()

    loaded = task_repo.load("tenant_poc", "dt_worker_001")
    assert result == {"processed": True, "task_id": "dt_worker_001", "status": "failed"}
    assert loaded["task"]["status"] == "failed"
    assert "provider unavailable" in loaded["task"]["errors"][0]["message"]


def test_task_worker_run_once_returns_idle_when_queue_empty(tmp_path):
    worker = TaskWorker(
        task_repository=FileTaskRepository(tmp_path / "tasks"),
        result_repository=FileResultRepository(tmp_path / "results"),
        queue=InMemoryTaskQueue(),
        source_client=FixtureSourceClient("tests/fixtures/fofa_results.json"),
    )

    assert worker.run_once() == {"processed": False}
