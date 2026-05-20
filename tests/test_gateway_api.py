from resource_discovery.gateway_api import DiscoveryGatewayApi
from resource_discovery.scope_guard import TenantScopeProfile
from resource_discovery.source_client import FixtureSourceClient
from resource_discovery.uncover_client import FixtureUncoverSourceClient


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


def test_create_discovery_task_executes_with_accepted_scope(tmp_path):
    response = _api(tmp_path).create_task(
        {
            "profile_id": "scope_profile_001",
            "requested_scope": {"domains": ["vpn.example.org"]},
            "engines": ["fofa"],
            "result_limit": 50,
            "purpose": "toolbox_asset_discovery",
        }
    )

    assert response["status"] == "success"
    assert type(response["status"]) is str
    assert response["accepted_scope"] == {"domains": ["vpn.example.org"]}
    assert response["rejected_scope"] == []
    assert response["query_plan_summary"] == {"engines": ["fofa"], "planned_queries": 1}
    assert response["status_url"].endswith(response["task_id"])
    assert response["result_url"].endswith(f"{response['task_id']}/results")


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


def test_get_task_and_results_return_toolbox_payload(tmp_path):
    api = _api(tmp_path)
    created = api.create_task(
        {
            "profile_id": "scope_profile_001",
            "requested_scope": {"root_domains": ["example.org"]},
            "engines": ["fofa"],
            "result_limit": 50,
            "purpose": "toolbox_asset_discovery",
        }
    )

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
    api = DiscoveryGatewayApi(
        profile=_profile(),
        source_client=FixtureUncoverSourceClient("tests/fixtures/uncover_fofa_results.jsonl"),
        snapshot_dir=tmp_path,
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
    results = api.get_results(created["task_id"])

    assert created["status"] == "success"
    assert results["services"][0]["freshness"]["status"] == "fresh"
    assert results["services"][1]["freshness"]["status"] == "stale"
