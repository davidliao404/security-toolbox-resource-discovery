import pytest

from resource_discovery.discovery_workflow import DiscoveryWorkflowConfig, build_query_plans
from resource_discovery.models import DiscoverySeed


def test_workflow_uses_baseline_strategy_by_default():
    config = DiscoveryWorkflowConfig()
    seeds = [DiscoverySeed(seed_id="s1", type="root_domain", value="example.org")]

    plans = build_query_plans("dt_001", seeds, config)

    assert len(plans) == 1
    assert plans[0].query_intent == "root_domain_match"


def test_workflow_uses_easm_strategy_when_requested():
    config = DiscoveryWorkflowConfig(strategy="easm")
    seeds = [DiscoverySeed(seed_id="s1", type="root_domain", value="example.org")]

    plans = build_query_plans("dt_001", seeds, config)

    assert [plan.query_intent for plan in plans] == [
        "root_domain_match",
        "host_suffix_match",
        "certificate_domain_match",
    ]


def test_workflow_enforces_max_plans_before_provider_calls():
    config = DiscoveryWorkflowConfig(strategy="easm", max_query_plans=2)
    seeds = [
        DiscoverySeed(seed_id="s1", type="root_domain", value="example.org"),
        DiscoverySeed(seed_id="s2", type="organization_name", value="Example Org"),
    ]

    with pytest.raises(ValueError, match="query plan budget"):
        build_query_plans("dt_001", seeds, config)
