import pytest

from resource_discovery.models import DiscoverySeed
from resource_discovery.query_planner import plan_fofa_queries


def test_plans_fofa_queries_for_supported_seed_types():
    seeds = [
        DiscoverySeed(seed_id="s1", type="root_domain", value="example.org"),
        DiscoverySeed(seed_id="s2", type="organization_name", value="Example Org"),
        DiscoverySeed(seed_id="s3", type="ip_cidr", value="203.0.113.0/24"),
    ]

    plans = plan_fofa_queries("dt_001", seeds)

    assert [plan.query_type for plan in plans] == ["domain", "organization", "ip_range"]
    assert plans[0].source_query == 'domain="example.org"'
    assert plans[1].source_query == 'cert.subject.org="Example Org" || title="Example Org"'
    assert plans[2].source_query == 'ip="203.0.113.0/24"'


def test_rejects_unsupported_seed_type():
    seeds = [DiscoverySeed(seed_id="s1", type="freeform_query", value='body="secret"')]

    with pytest.raises(ValueError, match="Unsupported seed type"):
        plan_fofa_queries("dt_001", seeds)
