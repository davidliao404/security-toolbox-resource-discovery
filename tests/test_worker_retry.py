from pathlib import Path

from resource_discovery.gateway_api import DiscoveryGatewayApi
from resource_discovery.scope_guard import TenantScopeProfile
from resource_discovery.source_client import FixtureSourceClient, SourceClient
from resource_discovery.sqlite_store import SQLiteResultRepository, SQLiteTaskRepository, initialize_sqlite
from resource_discovery.task_queue import TaskWorkItem
from resource_discovery.queue_backends import TaskQueueStatus
from resource_discovery.worker import TaskWorker, _first_error_message


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

    def mark_retry(self, item, reason, delay_seconds=0):
        self.retries.append((item, reason))
        self.attempts += 1

    def mark_failed(self, item, reason):
        self.failures.append((item, reason))


class LegacyStatusQueue:
    def __init__(self, item, *, attempts=0, missing_status=False):
        self.item = item
        self.retries = []
        self.failures = []
        self._attempts = attempts
        self.missing_status = missing_status

    def dequeue(self):
        item = self.item
        self.item = None
        return item

    def status(self, tenant_id, task_id):
        if self.missing_status:
            raise FileNotFoundError(task_id)
        return TaskQueueStatus(state="running", attempts=self._attempts, last_error="")

    def mark_retry(self, item, reason):
        self.retries.append((item, reason))

    def mark_failed(self, item, reason):
        self.failures.append((item, reason))


class FailingSourceClient(SourceClient):
    def fetch(self, plan):
        raise RuntimeError("provider_timeout")


class ExplodingWorker(TaskWorker):
    def _execute(self, task_payload):
        raise RuntimeError("unexpected_provider_crash")


class RecoverableResultWorker(TaskWorker):
    def _execute(self, task_payload):
        return {
            **task_payload,
            "task": {
                **task_payload["task"],
                "status": "failed",
                "errors": [{"message": "provider_timeout", "recoverable": True}],
            },
        }


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


def test_worker_keeps_task_retrying_until_retry_budget_is_exhausted(tmp_path):
    task_repo, result_repo, item = _create_task(tmp_path, FailingSourceClient())
    queue = QueueSpy(item)

    result = TaskWorker(task_repo, result_repo, queue, FailingSourceClient(), max_attempts=2).run_once()
    saved = task_repo.load(item.tenant_id, item.task_id)

    assert result["status"] == "retrying"
    assert saved["task"]["status"] == "retrying"
    assert saved["task"]["errors"][0]["message"] == "provider_timeout"


def test_worker_marks_failed_when_retry_budget_is_exhausted(tmp_path):
    task_repo, result_repo, item = _create_task(tmp_path, FailingSourceClient())
    queue = QueueSpy(item)
    queue.attempts = 1

    result = TaskWorker(task_repo, result_repo, queue, FailingSourceClient(), max_attempts=2).run_once()

    assert result["status"] == "failed"
    assert queue.failures == [(item, "provider_timeout")]


def test_worker_retries_unexpected_exception_before_terminal_failure(tmp_path):
    task_repo, result_repo, item = _create_task(tmp_path, FixtureSourceClient(Path("tests/fixtures/fofa_results.json")))
    queue = QueueSpy(item)

    result = ExplodingWorker(task_repo, result_repo, queue, FailingSourceClient(), max_attempts=2).run_once()
    saved = task_repo.load(item.tenant_id, item.task_id)

    assert result["status"] == "retrying"
    assert saved["task"]["status"] == "retrying"
    assert queue.retries == [(item, "unexpected_provider_crash")]


def test_worker_marks_unexpected_exception_failed_when_retry_budget_exhausted(tmp_path):
    task_repo, result_repo, item = _create_task(tmp_path, FixtureSourceClient(Path("tests/fixtures/fofa_results.json")))
    queue = QueueSpy(item)
    queue.attempts = 1

    result = ExplodingWorker(task_repo, result_repo, queue, FailingSourceClient(), max_attempts=2).run_once()
    saved = task_repo.load(item.tenant_id, item.task_id)

    assert result["status"] == "failed"
    assert saved["task"]["status"] == "failed"
    assert queue.failures == [(item, "unexpected_provider_crash")]


def test_worker_exception_retry_supports_legacy_queue_without_delay_argument(tmp_path):
    task_repo, result_repo, item = _create_task(tmp_path, FixtureSourceClient(Path("tests/fixtures/fofa_results.json")))
    queue = LegacyStatusQueue(item, missing_status=True)

    result = ExplodingWorker(task_repo, result_repo, queue, FailingSourceClient(), max_attempts=2).run_once()

    assert result["status"] == "retrying"
    assert queue.retries == [(item, "unexpected_provider_crash")]


def test_worker_recoverable_result_supports_status_queue_and_legacy_retry(tmp_path):
    task_repo, result_repo, item = _create_task(tmp_path, FixtureSourceClient(Path("tests/fixtures/fofa_results.json")))
    queue = LegacyStatusQueue(item, attempts=0)

    result = RecoverableResultWorker(task_repo, result_repo, queue, FailingSourceClient(), max_attempts=2).run_once()

    assert result["status"] == "retrying"
    assert queue.retries == [(item, "provider_timeout")]


def test_worker_recoverable_result_marks_failed_after_status_queue_budget_exhausted(tmp_path):
    task_repo, result_repo, item = _create_task(tmp_path, FixtureSourceClient(Path("tests/fixtures/fofa_results.json")))
    queue = LegacyStatusQueue(item, attempts=1)

    result = RecoverableResultWorker(task_repo, result_repo, queue, FailingSourceClient(), max_attempts=2).run_once()

    assert result["status"] == "failed"
    assert queue.failures == [(item, "provider_timeout")]


def test_first_error_message_defaults_when_error_list_is_empty():
    assert _first_error_message({"task": {"errors": []}}) == "recoverable task failure"
