from pathlib import Path
import sys
from types import SimpleNamespace

from resource_discovery.config import GatewaySettings
from resource_discovery.gateway_api import DiscoveryGatewayApi
from resource_discovery.queue_backends import SQLiteTaskQueue
from resource_discovery.scope_guard import TenantScopeProfile
from resource_discovery.source_client import FixtureSourceClient
from resource_discovery.sqlite_store import SQLiteResultRepository, SQLiteTaskRepository, initialize_sqlite
from resource_discovery.worker import TaskWorker
import resource_discovery.worker_cli as worker_cli
from resource_discovery.worker_cli import main, run_worker


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


def test_run_worker_sleeps_when_looping_without_work(monkeypatch):
    class EmptyWorker:
        def run_once(self):
            return {"processed": False}

    sleeps = []
    monkeypatch.setattr(worker_cli.time, "sleep", lambda seconds: sleeps.append(seconds))

    results = run_worker(EmptyWorker(), loop=True, interval_seconds=0.5, max_iterations=2)

    assert results == [{"processed": False}, {"processed": False}]
    assert sleeps == [0.5]


def test_worker_cli_main_runs_default_sqlite_path(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "worker",
            "--sqlite-path",
            str(tmp_path / "gateway.sqlite3"),
            "--fixture",
            "tests/fixtures/fofa_results.json",
        ],
    )

    assert main() == 0
    assert "'processed': False" in capsys.readouterr().out


def test_worker_cli_main_uses_settings_env(monkeypatch, capsys):
    class EmptyWorker:
        def __init__(self, *args, **kwargs):
            pass

        def run_once(self):
            return {"processed": False}

    monkeypatch.setattr(worker_cli, "load_settings", lambda: GatewaySettings(fixture_path="tests/fixtures/fofa_results.json"))
    monkeypatch.setattr(
        worker_cli,
        "build_repositories",
        lambda settings: SimpleNamespace(task_repository=object(), result_repository=object()),
    )
    monkeypatch.setattr(worker_cli, "build_queue", lambda settings: object())
    monkeypatch.setattr(worker_cli, "TaskWorker", EmptyWorker)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "worker",
            "--settings-env",
            "prodlike",
            "--loop",
            "--interval-seconds",
            "0",
            "--max-iterations",
            "1",
        ],
    )

    assert main() == 0
    assert "'processed': False" in capsys.readouterr().out
