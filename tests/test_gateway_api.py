from resource_discovery.gateway_api import DiscoveryGatewayApi
from resource_discovery.repositories import FileResultRepository, FileTaskRepository
from resource_discovery.scope_guard import TenantScopeProfile
from resource_discovery.source_client import FixtureSourceClient
from resource_discovery.task_queue import InMemoryTaskQueue
from resource_discovery.uncover_client import FixtureUncoverSourceClient
from resource_discovery.worker import TaskWorker


def _profile():
    return TenantScopeProfile(
        tenant_id="tenant_poc",
        profile_id="scope_profile_001",
        allowed_root_domains=["example.org"],
        allowed_domains=["vpn.example.org"],
        allowed_ip_cidrs=["203.0.113.0/24"],
        allowed_org_names=["Example Organization"],
        default_scope={"root_domains": ["example.org"]},
        allowed_engines=["fofa"],
        provider_profile_id="provider_fofa_poc",
        limits={"max_results_per_task": 100, "max_queries_per_task": 10},
        created_by="security_operator_hash",
        authorization_note="Confirmed by customer interview.",
    )


def _api(tmp_path):
    return DiscoveryGatewayApi(
        profile=_profile(),
        source_client=FixtureSourceClient("tests/fixtures/fofa_results.json"),
        snapshot_dir=tmp_path,
    )


def test_get_scope_profile_returns_toolbox_contract(tmp_path):
    response = _api(tmp_path).get_scope_profile()

    assert response["profile_id"] == "scope_profile_001"
    assert response["allowed_engines"] == ["fofa"]
    assert response["default_scope"] == {"root_domains": ["example.org"]}


def test_create_discovery_task_queues_with_accepted_scope(tmp_path):
    queue = InMemoryTaskQueue()
    response = DiscoveryGatewayApi(
        profile=_profile(),
        source_client=FixtureSourceClient("tests/fixtures/fofa_results.json"),
        snapshot_dir=tmp_path,
        queue=queue,
    ).create_task(
        {
            "profile_id": "scope_profile_001",
            "requested_scope": {"domains": ["vpn.example.org"]},
            "engines": ["fofa"],
            "result_limit": 50,
            "purpose": "toolbox_asset_discovery",
        }
    )

    assert response["status"] == "queued"
    assert type(response["status"]) is str
    assert response["accepted_scope"] == {"domains": ["vpn.example.org"]}
    assert response["rejected_scope"] == []
    assert response["query_plan_summary"] == {"engines": ["fofa"], "planned_queries": 1}
    assert response["status_url"].endswith(response["task_id"])
    assert response["result_url"].endswith(f"{response['task_id']}/results")
    assert len(queue) == 1


def test_create_discovery_task_generates_unique_task_ids(tmp_path):
    queue = InMemoryTaskQueue()
    api = DiscoveryGatewayApi(
        profile=_profile(),
        source_client=FixtureSourceClient("tests/fixtures/fofa_results.json"),
        snapshot_dir=tmp_path,
        queue=queue,
    )
    request = {
        "profile_id": "scope_profile_001",
        "requested_scope": {"domains": ["vpn.example.org"]},
        "engines": ["fofa"],
        "result_limit": 50,
        "purpose": "toolbox_asset_discovery",
    }

    first = api.create_task(request)
    second = api.create_task(request)

    assert first["task_id"] != second["task_id"]
    assert first["task_id"].startswith("dt_")
    assert second["task_id"].startswith("dt_")


def test_create_discovery_task_rejects_out_of_scope_values(tmp_path):
    response = _api(tmp_path).create_task(
        {
            "profile_id": "scope_profile_001",
            "requested_scope": {"root_domains": ["other.org"]},
            "engines": ["fofa"],
            "result_limit": 50,
            "purpose": "toolbox_asset_discovery",
        }
    )

    assert response["status"] == "rejected"
    assert response["accepted_scope"] == {}
    assert response["rejected_scope"][0]["reason"] == "outside_tenant_allowed_scope"


def test_get_task_and_results_return_toolbox_payload_after_worker_runs(tmp_path):
    task_repo = FileTaskRepository(tmp_path / "tasks")
    result_repo = FileResultRepository(tmp_path / "results")
    queue = InMemoryTaskQueue()
    api = DiscoveryGatewayApi(
        profile=_profile(),
        source_client=FixtureSourceClient("tests/fixtures/fofa_results.json"),
        task_repository=task_repo,
        result_repository=result_repo,
        queue=queue,
    )
    created = api.create_task(
        {
            "profile_id": "scope_profile_001",
            "requested_scope": {"root_domains": ["example.org"]},
            "engines": ["fofa"],
            "result_limit": 50,
            "purpose": "toolbox_asset_discovery",
        }
    )
    worker = TaskWorker(
        task_repository=task_repo,
        result_repository=result_repo,
        queue=queue,
        source_client=FixtureSourceClient("tests/fixtures/fofa_results.json"),
    )
    worker.run_once()

    task = api.get_task(created["task_id"])
    results = api.get_results(created["task_id"], limit=2)

    assert task["task_id"] == created["task_id"]
    assert task["status"] == "success"
    assert task["engine_status"] == [{"engine": "fofa", "status": "success", "result_count": 3}]
    assert results["task_id"] == created["task_id"]
    assert len(results["assets"]) == 2
    assert "report" not in results
    assert results["page"]["next_cursor"] == "2"


def test_gateway_api_can_use_uncover_fixture_client(tmp_path):
    task_repo = FileTaskRepository(tmp_path / "tasks")
    result_repo = FileResultRepository(tmp_path / "results")
    queue = InMemoryTaskQueue()
    api = DiscoveryGatewayApi(
        profile=_profile(),
        source_client=FixtureUncoverSourceClient("tests/fixtures/uncover_fofa_results.jsonl"),
        task_repository=task_repo,
        result_repository=result_repo,
        queue=queue,
    )

    created = api.create_task(
        {
            "profile_id": "scope_profile_001",
            "requested_scope": {"root_domains": ["example.org"]},
            "engines": ["fofa"],
            "result_limit": 50,
            "purpose": "toolbox_asset_discovery",
        }
    )
    TaskWorker(
        task_repository=task_repo,
        result_repository=result_repo,
        queue=queue,
        source_client=FixtureUncoverSourceClient("tests/fixtures/uncover_fofa_results.jsonl"),
    ).run_once()
    results = api.get_results(created["task_id"], result_type="services")

    assert created["status"] == "queued"
    assert results["services"][0]["freshness"]["status"] == "fresh"
    assert results["services"][1]["freshness"]["status"] == "stale"


def test_gateway_api_can_use_repository_abstractions(tmp_path):
    task_repo = FileTaskRepository(tmp_path / "tasks")
    result_repo = FileResultRepository(tmp_path / "results")
    queue = InMemoryTaskQueue()
    api = DiscoveryGatewayApi(
        profile=_profile(),
        source_client=FixtureSourceClient("tests/fixtures/fofa_results.json"),
        task_repository=task_repo,
        result_repository=result_repo,
        queue=queue,
    )

    created = api.create_task(
        {
            "profile_id": "scope_profile_001",
            "requested_scope": {"root_domains": ["example.org"]},
            "engines": ["fofa"],
            "result_limit": 50,
            "purpose": "toolbox_asset_discovery",
        }
    )

    assert api.get_task(created["task_id"])["status"] == "queued"
    TaskWorker(
        task_repository=task_repo,
        result_repository=result_repo,
        queue=queue,
        source_client=FixtureSourceClient("tests/fixtures/fofa_results.json"),
    ).run_once()
    assert api.get_results(created["task_id"], limit=1)["page"]["next_cursor"] == "1"
