from resource_discovery.errors import ApiError
from resource_discovery.gateway_api import DiscoveryGatewayApi
from resource_discovery.scope_guard import TenantScopeProfile
from resource_discovery.source_client import FixtureSourceClient


def _profile():
    return TenantScopeProfile(
        tenant_id="tenant_poc",
        profile_id="scope_profile_001",
        allowed_root_domains=["example.org"],
        default_scope={"root_domains": ["example.org"]},
        allowed_engines=["fofa"],
        limits={"max_results_per_task": 100, "max_queries_per_task": 10},
        authorization_note="Confirmed by customer interview.",
    )


def _api(tmp_path):
    return DiscoveryGatewayApi(
        profile=_profile(),
        source_client=FixtureSourceClient("tests/fixtures/fofa_results.json"),
        snapshot_dir=tmp_path,
    )


def test_api_error_serializes_to_contract_shape():
    error = ApiError(
        code="scope_out_of_bounds",
        message="Requested scope is outside the tenant authorized scope.",
        recoverable=False,
        details={"profile_id": "scope_profile_001"},
    )

    assert error.to_dict() == {
        "code": "scope_out_of_bounds",
        "message": "Requested scope is outside the tenant authorized scope.",
        "recoverable": False,
        "details": {"profile_id": "scope_profile_001"},
    }


def test_profile_id_mismatch_returns_errors_array(tmp_path):
    response = _api(tmp_path).create_task(
        {
            "profile_id": "wrong_profile",
            "requested_scope": {"root_domains": ["example.org"]},
            "engines": ["fofa"],
            "result_limit": 50,
        }
    )

    assert response["status"] == "rejected"
    assert response["errors"][0]["code"] == "profile_id_mismatch"
    assert response["errors"][0]["recoverable"] is False


def test_scope_rejection_returns_contract_error(tmp_path):
    response = _api(tmp_path).create_task(
        {
            "profile_id": "scope_profile_001",
            "requested_scope": {"root_domains": ["other.org"]},
            "engines": ["fofa"],
            "result_limit": 50,
        }
    )

    assert response["status"] == "rejected"
    assert response["errors"][0]["code"] == "scope_out_of_bounds"
    assert response["errors"][0]["details"]["rejected_scope"][0]["value"] == "other.org"
