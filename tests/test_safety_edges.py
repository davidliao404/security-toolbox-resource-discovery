import pytest

from resource_discovery.models import DiscoverySeed, SourceQueryPlan
from resource_discovery.safety import DiscoveryPolicy, SafetyViolation, enforce_plan_quota, validate_seeds


def _seed(seed_type, value, note="approval"):
    return DiscoverySeed(seed_id="seed_001", type=seed_type, value=value, authorization_note=note)


def test_validate_seeds_rejects_seed_count_above_policy():
    seeds = [_seed("root_domain", f"example{i}.com") for i in range(2)]

    with pytest.raises(SafetyViolation, match="Seed count"):
        validate_seeds(seeds, DiscoveryPolicy(max_seed_count=1))


def test_validate_seeds_requires_authorization_note_and_value():
    with pytest.raises(SafetyViolation, match="authorization_note"):
        validate_seeds([_seed("root_domain", "example.com", note="")])

    with pytest.raises(SafetyViolation, match="value is empty"):
        validate_seeds([_seed("root_domain", " ")], DiscoveryPolicy(require_authorization_note=False))


def test_validate_seeds_rejects_invalid_domain_short_org_and_unknown_type():
    with pytest.raises(SafetyViolation, match="valid domain"):
        validate_seeds([_seed("root_domain", "not a domain")])

    with pytest.raises(SafetyViolation, match="too short"):
        validate_seeds([_seed("organization_name", "AB")])

    with pytest.raises(SafetyViolation, match="Unsupported seed type"):
        validate_seeds([_seed("freeform_query", 'body="secret"')])


def test_validate_seeds_rejects_invalid_or_too_broad_cidr():
    with pytest.raises(SafetyViolation, match="valid IP CIDR"):
        validate_seeds([_seed("ip_cidr", "not-cidr")])

    with pytest.raises(SafetyViolation, match="too broad"):
        validate_seeds([_seed("ip_cidr", "10.0.0.0/8")])


def test_enforce_plan_quota_rejects_page_and_result_budget():
    plan = SourceQueryPlan(
        plan_id="plan_001",
        task_id="task_1",
        source="fofa",
        seed_id="seed_001",
        source_query='domain="example.com"',
        query_type="root_domain",
        page_limit=2,
        result_limit=2000,
    )

    with pytest.raises(SafetyViolation, match="page budget"):
        enforce_plan_quota([plan], DiscoveryPolicy(max_total_pages=1))

    with pytest.raises(SafetyViolation, match="result limit"):
        enforce_plan_quota([plan], DiscoveryPolicy(max_total_pages=10, max_result_limit_per_plan=1000))
