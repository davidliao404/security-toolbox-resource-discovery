from pathlib import Path

from resource_discovery.models import DiscoverySeed
from resource_discovery.normalizer import normalize_fofa_results
from resource_discovery.query_planner import plan_fofa_queries
from resource_discovery.source_client import FixtureSourceClient


def test_normalizes_fofa_fixture_results():
    fixture = Path("tests/fixtures/fofa_results.json")
    seed = DiscoverySeed(seed_id="s1", type="root_domain", value="example.org")
    plan = plan_fofa_queries("dt_001", [seed])[0]
    rows = FixtureSourceClient(fixture).fetch(plan)

    batch = normalize_fofa_results("dt_001", plan, rows)

    assert batch.assets
    assert batch.services
    assert batch.evidences
    assert batch.services[0].domain == "vpn.example.org"
    assert batch.services[0].port == 443
    assert batch.evidences[0].source == "fofa"
    assert batch.evidences[0].source_query == 'domain="example.org"'
    assert batch.evidences[0].raw_reference.startswith("fofa:fixture:")
