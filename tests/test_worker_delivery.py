from pathlib import Path

from resource_discovery.gateway_api import DiscoveryGatewayApi
from resource_discovery.queue_backends import SQLiteTaskQueue
from resource_discovery.scope_guard import TenantScopeProfile
from resource_discovery.source_client import FixtureSourceClient
from resource_discovery.sqlite_store import SQLiteResultRepository, SQLiteTaskRepository, initialize_sqlite
from resource_discovery.worker import TaskWorker
from resource_discovery.worker_cli import run_worker


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


def test_worker_persists_successful_results_with_sqlite_queue(tmp_path):
    db_path = tmp_path / "gateway.sqlite3"
    initialize_sqlite(db_path)
    task_repo = SQLiteTaskRepository(db_path)
    result_repo = SQLiteResultRepository(db_path)
    queue = SQLiteTaskQueue(db_path)
    source_client = FixtureSourceClient(Path("tests/fixtures/fofa_results.json"))
    api = DiscoveryGatewayApi(
        profile=_profile(),
        source_client=source_client,
        task_repository=task_repo,
        result_repository=result_repo,
        queue=queue,
    )
    created = api.create_task(
        {
            "profile_id": "scope_profile_001",
            "requested_scope": {"root_domains": ["example.org"]},
            "engines": ["fofa"],
            "result_limit": 20,
        }
    )
    worker = TaskWorker(task_repo, result_repo, queue, source_client)

    result = worker.run_once()

    assert result["status"] in {"success", "partial_success"}
    loaded = result_repo.load_results("tenant_poc", created["task_id"], None, 10, "assets")
    assert loaded["assets"]


def test_run_worker_supports_bounded_loop(tmp_path):
    db_path = tmp_path / "gateway.sqlite3"
    initialize_sqlite(db_path)
    task_repo = SQLiteTaskRepository(db_path)
    result_repo = SQLiteResultRepository(db_path)
    queue = SQLiteTaskQueue(db_path)
    source_client = FixtureSourceClient(Path("tests/fixtures/fofa_results.json"))
    api = DiscoveryGatewayApi(
        profile=_profile(),
        source_client=source_client,
        task_repository=task_repo,
        result_repository=result_repo,
        queue=queue,
    )
    api.create_task(
        {
            "profile_id": "scope_profile_001",
            "requested_scope": {"root_domains": ["example.org"]},
            "engines": ["fofa"],
            "result_limit": 20,
        }
    )
    worker = TaskWorker(task_repo, result_repo, queue, source_client)

    results = run_worker(worker, loop=True, interval_seconds=0, max_iterations=2)

    assert results[0]["processed"] is True
    assert results[1]["processed"] is False