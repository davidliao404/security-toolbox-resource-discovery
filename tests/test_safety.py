import pytest

from resource_discovery.models import DiscoverySeed
from resource_discovery.query_planner import plan_fofa_queries
from resource_discovery.safety import DiscoveryPolicy, SafetyViolation, enforce_plan_quota, validate_seeds


def test_validate_seeds_requires_authorization_note():
    seeds = [DiscoverySeed(seed_id="s1", type="root_domain", value="example.org")]

    with pytest.raises(SafetyViolation, match="authorization_note"):
        validate_seeds(seeds)


def test_validate_seeds_rejects_large_ipv4_ranges_by_default():
    seeds = [
        DiscoverySeed(
            seed_id="s1",
            type="ip_cidr",
            value="203.0.0.0/16",
            authorization_note="Authorized test range",
        )
    ]

    with pytest.raises(SafetyViolation, match="too broad"):
        validate_seeds(seeds)


def test_validate_seeds_accepts_authorized_domain_org_and_small_ip_range():
    seeds = [
        DiscoverySeed(
            seed_id="s1",
            type="root_domain",
            value="example.org",
            authorization_note="Authorized domain",
        ),
        DiscoverySeed(
            seed_id="s2",
            type="organization_name",
            value="Example Organization",
            authorization_note="Authorized organization name",
        ),
        DiscoverySeed(
            seed_id="s3",
            type="ip_cidr",
            value="203.0.113.0/24",
            authorization_note="Authorized IP range",
        ),
    ]

    validate_seeds(seeds)


def test_enforce_plan_quota_blocks_excessive_pages():
    seeds = [
        DiscoverySeed(
            seed_id=f"s{index}",
            type="root_domain",
            value=f"example{index}.org",
            authorization_note="Authorized domain",
        )
        for index in range(4)
    ]
    plans = plan_fofa_queries("dt_001", seeds, page_limit=10)

    with pytest.raises(SafetyViolation, match="page budget"):
        enforce_plan_quota(plans, DiscoveryPolicy(max_total_pages=30))
