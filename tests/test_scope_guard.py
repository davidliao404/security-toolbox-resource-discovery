import pytest

from resource_discovery.scope_guard import (
    ScopeValidationError,
    TenantScopeProfile,
    validate_requested_scope,
)


def _profile():
    return TenantScopeProfile(
        tenant_id="tenant_poc",
        profile_id="scope_profile_001",
        allowed_root_domains=["example.com"],
        allowed_domains=["www.example.com", "vpn.example.com"],
        allowed_ip_cidrs=["203.0.113.0/24"],
        allowed_org_names=["Example Limited"],
        default_scope={"root_domains": ["example.com"]},
        allowed_engines=["fofa"],
        provider_profile_id="provider_fofa_hk_001",
        limits={"max_results_per_task": 200, "max_queries_per_task": 10},
        created_by="security_operator_hash",
        authorization_note="Customer interview confirmed ownership.",
    )


def test_scope_profile_summary_is_safe_for_toolbox_display():
    summary = _profile().to_toolbox_summary()

    assert summary == {
        "tenant_id": "tenant_poc",
        "profile_id": "scope_profile_001",
        "allowed_scope_summary": {
            "root_domains": ["example.com"],
            "domains": ["www.example.com", "vpn.example.com"],
            "ip_cidrs": ["203.0.113.0/24"],
            "org_names": ["Example Limited"],
        },
        "default_scope": {"root_domains": ["example.com"]},
        "allowed_engines": ["fofa"],
        "limits": {"max_results_per_task": 200, "max_queries_per_task": 10},
    }


def test_validate_requested_scope_accepts_subset_scope():
    result = validate_requested_scope(
        _profile(),
        {
            "domains": ["vpn.example.com"],
            "ip_cidrs": ["203.0.113.16/28"],
        },
        engines=["fofa"],
        result_limit=100,
    )

    assert result.accepted_scope == {
        "domains": ["vpn.example.com"],
        "ip_cidrs": ["203.0.113.16/28"],
    }
    assert result.rejected_scope == []


def test_validate_requested_scope_accepts_subdomain_of_allowed_root_and_org():
    result = validate_requested_scope(
        _profile(),
        {
            "domains": ["api.example.com"],
            "org_names": ["Example Limited"],
        },
        engines=["fofa"],
        result_limit=100,
    )

    assert result.accepted_scope == {
        "domains": ["api.example.com"],
        "org_names": ["Example Limited"],
    }
    assert result.rejected_scope == []


def test_validate_requested_scope_uses_default_scope_when_empty():
    result = validate_requested_scope(_profile(), {}, engines=["fofa"], result_limit=100)

    assert result.accepted_scope == {"root_domains": ["example.com"]}
    assert result.rejected_scope == []


def test_validate_requested_scope_rejects_domain_outside_profile():
    result = validate_requested_scope(
        _profile(),
        {"root_domains": ["other.com"]},
        engines=["fofa"],
        result_limit=100,
    )

    assert result.accepted_scope == {}
    assert result.rejected_scope == [
        {
            "type": "root_domain",
            "value": "other.com",
            "reason": "outside_tenant_allowed_scope",
        }
    ]


def test_validate_requested_scope_rejects_wider_cidr():
    result = validate_requested_scope(
        _profile(),
        {"ip_cidrs": ["203.0.112.0/23"]},
        engines=["fofa"],
        result_limit=100,
    )

    assert result.accepted_scope == {}
    assert result.rejected_scope[0]["reason"] == "outside_tenant_allowed_scope"


def test_validate_requested_scope_rejects_invalid_cidr_and_org():
    result = validate_requested_scope(
        _profile(),
        {"ip_cidrs": ["not-cidr"], "org_names": ["Other Limited"]},
        engines=["fofa"],
        result_limit=100,
    )

    assert [item["type"] for item in result.rejected_scope] == ["ip_cidr", "organization_name"]


def test_validate_requested_scope_rejects_inactive_profile():
    profile = TenantScopeProfile(
        tenant_id="tenant_poc",
        profile_id="scope_profile_001",
        status="inactive",
    )

    with pytest.raises(ScopeValidationError, match="not active"):
        validate_requested_scope(profile, {}, engines=["fofa"], result_limit=100)


def test_validate_requested_scope_rejects_disallowed_engine():
    with pytest.raises(ScopeValidationError, match="engine"):
        validate_requested_scope(_profile(), {}, engines=["quake"], result_limit=100)


def test_validate_requested_scope_rejects_result_limit_above_profile():
    with pytest.raises(ScopeValidationError, match="result_limit"):
        validate_requested_scope(_profile(), {}, engines=["fofa"], result_limit=500)
