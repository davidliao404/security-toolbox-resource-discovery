from resource_discovery.models import SourceQueryPlan
from resource_discovery.uncover_client import (
    FixtureUncoverSourceClient,
    UncoverCommandSourceClient,
    parse_uncover_jsonl,
)


def _plan():
    return SourceQueryPlan(
        plan_id="plan_001",
        task_id="dt_uncover_001",
        source="fofa",
        seed_id="seed_001",
        source_query='domain="example.org"',
        query_type="domain",
        result_limit=10,
    )


def test_parse_uncover_jsonl_normalizes_fofa_rows():
    rows = parse_uncover_jsonl(
        '{"ip":"203.0.113.10","port":"443","host":"vpn.example.org","source":"fofa","timestamp":"2026-05-19 12:00:00"}\n'
    )

    assert rows == [
        {
            "ip": "203.0.113.10",
            "port": 443,
            "host": "vpn.example.org",
            "source": "fofa",
            "lastupdatetime": "2026-05-19 12:00:00",
            "protocol": "unknown",
            "service": "unknown",
        }
    ]


def test_fixture_uncover_source_client_filters_by_query_type():
    client = FixtureUncoverSourceClient("tests/fixtures/uncover_fofa_results.jsonl")

    rows = client.fetch(_plan())

    assert len(rows) == 2
    assert rows[0]["host"] == "vpn.example.org"
    assert rows[0]["lastupdatetime"] == "2026-05-19 12:00:00"


def test_fixture_uncover_source_client_respects_result_limit():
    client = FixtureUncoverSourceClient("tests/fixtures/uncover_fofa_results.jsonl")
    plan = SourceQueryPlan(
        plan_id="plan_001",
        task_id="dt_uncover_001",
        source="fofa",
        seed_id="seed_001",
        source_query='domain="example.org"',
        query_type="domain",
        result_limit=1,
    )

    rows = client.fetch(plan)

    assert len(rows) == 1


def test_uncover_rows_flow_into_service_freshness():
    from resource_discovery.normalizer import normalize_fofa_results

    client = FixtureUncoverSourceClient("tests/fixtures/uncover_fofa_results.jsonl")
    batch = normalize_fofa_results("dt_uncover_001", _plan(), client.fetch(_plan()))

    assert batch.services[0].freshness["status"] == "fresh"
    assert batch.services[1].freshness["status"] == "stale"
    assert batch.evidences[0].evidence["freshness"]["meaning"] == (
        "provider_observation_time_not_liveness_proof"
    )


def test_uncover_command_source_client_builds_fofa_command_and_parses_output():
    calls = []

    def fake_runner(command):
        calls.append(command)
        return (
            '{"ip":"203.0.113.10","port":"443","host":"vpn.example.org",'
            '"source":"fofa","timestamp":"2026-05-19 12:00:00"}\n'
        )

    client = UncoverCommandSourceClient(
        provider_config_path="artifacts/uncover/provider-config.yaml",
        runner=fake_runner,
    )

    rows = client.fetch(_plan())

    assert calls == [
        [
            "uncover",
            "-ff",
            'domain="example.org"',
            "-e",
            "fofa",
            "-j",
            "-silent",
            "-l",
            "10",
            "-provider",
            "artifacts/uncover/provider-config.yaml",
        ]
    ]
    assert rows[0]["host"] == "vpn.example.org"
