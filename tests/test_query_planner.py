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


def test_baseline_query_plans_include_stage_and_intent_metadata():
    seeds = [DiscoverySeed(seed_id="s1", type="root_domain", value="example.org")]

    plans = plan_fofa_queries("dt_001", seeds)

    assert len(plans) == 1
    assert plans[0].stage == "seed"
    assert plans[0].query_intent == "root_domain_match"
    assert plans[0].derived_from == ["s1"]


def test_default_strategy_preserves_existing_query_count_and_queries():
    seeds = [
        DiscoverySeed(seed_id="s1", type="root_domain", value="example.org"),
        DiscoverySeed(seed_id="s2", type="organization_name", value="Example Org"),
        DiscoverySeed(seed_id="s3", type="ip_cidr", value="203.0.113.0/24"),
    ]

    plans = plan_fofa_queries("dt_001", seeds)

    assert [plan.source_query for plan in plans] == [
        'domain="example.org"',
        'cert.subject.org="Example Org" || title="Example Org"',
        'ip="203.0.113.0/24"',
    ]


def test_easm_strategy_generates_controlled_passive_query_templates():
    seeds = [
        DiscoverySeed(seed_id="s1", type="root_domain", value="example.org"),
        DiscoverySeed(seed_id="s2", type="organization_name", value="Example Org"),
        DiscoverySeed(seed_id="s3", type="ip_cidr", value="203.0.113.0/24"),
    ]

    plans = plan_fofa_queries("dt_001", seeds, strategy="easm")

    assert [plan.query_intent for plan in plans] == [
        "root_domain_match",
        "host_suffix_match",
        "certificate_domain_match",
        "organization_certificate_match",
        "organization_title_match",
        "asn_organization_match",
        "ip_range_match",
    ]
    assert [plan.source_query for plan in plans] == [
        'domain="example.org"',
        'host=".example.org"',
        'cert.domain="example.org"',
        'cert.subject.org="Example Org"',
        'title="Example Org"',
        'org="Example Org"',
        'ip="203.0.113.0/24"',
    ]


def test_rejects_unsupported_discovery_strategy():
    seeds = [DiscoverySeed(seed_id="s1", type="root_domain", value="example.org")]

    with pytest.raises(ValueError, match="Unsupported discovery strategy"):
        plan_fofa_queries("dt_001", seeds, strategy="active")


def test_rejects_unsupported_seed_type():
    seeds = [DiscoverySeed(seed_id="s1", type="freeform_query", value='body="secret"')]

    with pytest.raises(ValueError, match="Unsupported seed type"):
        plan_fofa_queries("dt_001", seeds)


def test_rejects_empty_seed_value_for_each_strategy():
    seeds = [DiscoverySeed(seed_id="s1", type="root_domain", value=" ")]

    with pytest.raises(ValueError, match="value is empty"):
        plan_fofa_queries("dt_001", seeds)
    with pytest.raises(ValueError, match="value is empty"):
        plan_fofa_queries("dt_001", seeds, strategy="easm")


def test_fofa_query_values_escape_quotes_and_backslashes():
    seeds = [DiscoverySeed(seed_id="s1", type="organization_name", value='Example "A\\B"')]

    plans = plan_fofa_queries("dt_001", seeds)

    assert '\\"A\\\\B\\"' in plans[0].source_query
