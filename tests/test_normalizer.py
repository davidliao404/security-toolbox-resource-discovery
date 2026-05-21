from pathlib import Path

from resource_discovery.models import DiscoverySeed
from resource_discovery.models import SourceQueryPlan
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


def test_normalizer_maps_fofa_link_to_url():
    seed = DiscoverySeed(seed_id="s1", type="root_domain", value="example.org")
    plan = plan_fofa_queries("dt_001", [seed])[0]

    batch = normalize_fofa_results(
        "dt_001",
        plan,
        [
            {
                "ip": "203.0.113.10",
                "host": "vpn.example.org",
                "port": 443,
                "protocol": "https",
                "product": "ExampleVPN",
                "link": "https://vpn.example.org/",
            }
        ],
    )

    assert batch.services[0].url == "https://vpn.example.org/"


def test_normalizer_preserves_extended_fofa_evidence_fields():
    plan = SourceQueryPlan(
        plan_id="plan_001",
        task_id="dt_001",
        source="fofa",
        seed_id="s1",
        source_query='domain="example.org"',
        query_type="domain",
    )
    rows = [
        {
            "ip": "203.0.113.10",
            "host": "vpn.example.org",
            "domain": "example.org",
            "port": "443",
            "protocol": "https",
            "title": "VPN Portal",
            "product": "ExampleVPN",
            "version": "1.2.3",
            "server": "nginx",
            "asn": "64500",
            "org": "Example Limited",
            "country": "HK",
            "header_hash": "hh",
            "banner_hash": "bb",
            "cname": "edge.example-cdn.net",
            "lastupdatetime": "2026-05-20T00:00:00Z",
        }
    ]

    batch = normalize_fofa_results("dt_001", plan, rows)

    evidence = batch.evidences[0].evidence
    assert evidence["server"] == "nginx"
    assert evidence["asn"] == "64500"
    assert evidence["org"] == "Example Limited"
    assert evidence["header_hash"] == "hh"
    assert evidence["banner_hash"] == "bb"
    assert evidence["cname"] == "edge.example-cdn.net"
    assert batch.assets[0].asn == "64500"
    assert batch.assets[0].country_or_region == "HK"
    assert batch.services[0].version == "1.2.3"


def test_normalizer_scores_ownership_when_authorized_scope_is_provided():
    plan = SourceQueryPlan(
        plan_id="plan_001",
        task_id="dt_001",
        source="fofa",
        seed_id="s1",
        source_query='domain="example.org"',
        query_type="domain",
    )

    batch = normalize_fofa_results(
        "dt_001",
        plan,
        [
            {
                "ip": "203.0.113.10",
                "host": "vpn.example.org",
                "domain": "example.org",
                "port": "443",
                "protocol": "https",
                "confidence": 0.1,
            }
        ],
        authorized_scope={"root_domains": ["example.org"]},
    )

    assert batch.assets[0].ownership_confidence == 0.95
