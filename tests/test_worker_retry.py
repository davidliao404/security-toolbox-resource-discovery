from pathlib import Path

from resource_discovery.gateway_api import DiscoveryGatewayApi
from resource_discovery.scope_guard import TenantScopeProfile
from resource_discovery.source_client import FixtureSourceClient, SourceClient
from resource_discovery.sqlite_store import SQLiteResultRepository, SQLiteTaskRepository, initialize_sqlite
from resource_discovery.task_queue import TaskWorkItem
from resource_discovery.worker import TaskWorker


class QueueSpy:
    def __init__(self, item):
        self.item = item
        self.done = []
        self.retries = []
        self.failures = []
        self.attempts = 0

    def enqueue(self, item):
        self.item = item

    def dequeue(self):
        item = self.item
        self.item = None
        return item

    def mark_done(self, item):
        self.done.append(item)

    def mark_retry(self, item, reason):
        self.retries.append((item, reason))
        self.attempts += 1

    def mark_failed(self, item, reason):
        self.failures.append((item, reason))


class FailingSourceClient(SourceClient):
    def fetch(self, plan):
        raise RuntimeError("provider_timeout")


def _profile():
    return TenantScopeProfile(
        tenant_id="tenant_poc",
        profile_id="scope_profile_001",
        status="active",
        allowed_root_domains=["example.org"],
        allowed_domains=[],
        allowed_ip_cidrs=[],
        allowed_org_names=[],
        allowed_engines=["fofa"],
        default_scope={"root_domains": ["example.org"]},
        limits={"max_results_per_task": 100, "max_queries_per_task": 10},
        authorization_note="Customer approval for example.org.",
    )


def _create_task(tmp_path, source_client):
    db_path = tmp_path / "gateway.sqlite3"
    initialize_sqlite(db_path)
    task_repo = SQLiteTaskRepository(db_path)
    result_repo = SQLiteResultRepository(db_path)
    api = DiscoveryGatewayApi(
        profile=_profile(),
        source_client=source_client,
        task_repository=task_repo,
        result_repository=result_repo,
        queue=QueueSpy(None),
    )
    created = api.create_task(
        {
            "profile_id": "scope_profile_001",
            "requested_scope": {"root_domains": ["example.org"]},
            "engines": ["fofa"],
            "result_limit": 20,
        }
    )
    return task_repo, result_repo, TaskWorkItem("tenant_poc", created["task_id"])


def test_worker_marks_queue_done_after_success(tmp_path):
    source_client = FixtureSourceClient(Path("tests/fixtures/fofa_results.json"))
    task_repo, result_repo, item = _create_task(tmp_path, source_client)
    queue = QueueSpy(item)

    result = TaskWorker(task_repo, result_repo, queue, source_client).run_once()

    assert result["status"] in {"success", "partial_success"}
    assert queue.done == [item]


def test_worker_retries_recoverable_failure_before_terminal_failure(tmp_path):
    task_repo, result_repo, item = _create_task(tmp_path, FailingSourceClient())
    queue = QueueSpy(item)

    result = TaskWorker(task_repo, result_repo, queue, FailingSourceClient(), max_attempts=2).run_once()

    assert result["status"] == "retrying"
    assert queue.retries == [(item, "provider_timeout")]


def test_worker_marks_failed_when_retry_budget_is_exhausted(tmp_path):
    task_repo, result_repo, item = _create_task(tmp_path, FailingSourceClient())
    queue = QueueSpy(item)
    queue.attempts = 1

    result = TaskWorker(task_repo, result_repo, queue, FailingSourceClient(), max_attempts=2).run_once()

    assert result["status"] == "failed"
    assert queue.failures == [(item, "provider_timeout")]
