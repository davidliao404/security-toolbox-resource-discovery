import pytest

from resource_discovery.analysis import (
    LlmAnalysisUnavailable,
    build_minimal_llm_context,
    enrich_risk_hints,
)
from resource_discovery.cli import run_and_maybe_save
from resource_discovery.execution import run_discovery


def test_rules_only_analysis_returns_metadata_without_llm_enrichment():
    payload = run_discovery(
        seeds_path="examples/seeds.json",
        mode="fixture",
        fixture_path="tests/fixtures/fofa_results.json",
        analysis_mode="rules_only",
    )

    assert payload["analysis"] == {
        "analysis_mode": "rules_only",
        "llm_enabled": False,
        "web_search_enabled": False,
        "data_sharing_level": "none",
    }
    assert "llm_enrichment" not in payload["risk_hints"][0]


def test_cli_run_and_maybe_save_passes_analysis_configuration():
    payload = run_and_maybe_save(
        seeds_path="examples/seeds.json",
        mode="fixture",
        fixture_path="tests/fixtures/fofa_results.json",
        analysis_mode="rules_only",
        web_search_enabled=True,
        data_sharing_level="minimal",
    )

    assert payload["analysis"] == {
        "analysis_mode": "rules_only",
        "llm_enabled": False,
        "web_search_enabled": False,
        "data_sharing_level": "none",
    }


def test_rules_plus_llm_requires_explicit_enricher():
    with pytest.raises(LlmAnalysisUnavailable, match="LLM enricher"):
        run_discovery(
            seeds_path="examples/seeds.json",
            mode="fixture",
            fixture_path="tests/fixtures/fofa_results.json",
            analysis_mode="rules_plus_llm",
        )


def test_rules_plus_llm_uses_injected_enricher_with_minimal_context():
    class FakeEnricher:
        def enrich(self, context):
            assert context["data_sharing_level"] == "minimal"
            assert "raw_response" not in context
            assert context["risks"][0]["target_hash"]
            return {
                "provider": "fake",
                "model": "fake-risk-model",
                "items": [
                    {
                        "risk_hint_id": context["risks"][0]["risk_hint_id"],
                        "confidence_adjustment": 0.05,
                        "external_context_summary": "公开资料显示该类服务应优先复核。",
                    }
                ],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 25,
                    "total_tokens": 125,
                    "estimated_cost_usd": 0.0012,
                },
            }

    payload = run_discovery(
        seeds_path="examples/seeds.json",
        mode="fixture",
        fixture_path="tests/fixtures/fofa_results.json",
        analysis_mode="rules_plus_llm",
        llm_enricher=FakeEnricher(),
        web_search_enabled=True,
        data_sharing_level="minimal",
    )

    assert payload["analysis"]["analysis_mode"] == "rules_plus_llm"
    assert payload["analysis"]["llm_enabled"] is True
    assert payload["analysis"]["web_search_enabled"] is True
    assert payload["analysis"]["usage"] == {
        "prompt_tokens": 100,
        "completion_tokens": 25,
        "total_tokens": 125,
        "estimated_cost_usd": 0.0012,
    }
    assert payload["risk_hints"][0]["llm_enrichment"]["provider"] == "fake"
    assert payload["risk_hints"][0]["analysis_confidence"] == pytest.approx(
        min(payload["risk_hints"][0]["confidence"] + 0.05, 1.0)
    )


def test_minimal_llm_context_hashes_target_and_keeps_no_raw_target():
    risks = [
        {
            "risk_hint_id": "risk_1",
            "category": "remote_access",
            "severity": "high",
            "technical_evidence": ["target: vpn.example.org", "port: 443", "service: vpn"],
            "confidence": 0.78,
        }
    ]

    context = build_minimal_llm_context(risks, web_search_enabled=False)

    assert context["risks"][0]["target_hash"]
    assert "vpn.example.org" not in str(context)
    assert context["risks"][0]["port"] == "443"


def test_llm_enrichment_clamps_confidence_adjustment_and_truncates_summary():
    risk = {
        "risk_hint_id": "risk_1",
        "category": "remote_access",
        "severity": "high",
        "technical_evidence": ["target: vpn.example.org", "port: 443", "service: vpn"],
        "confidence": 0.78,
    }

    enriched = enrich_risk_hints(
        [risk],
        {
            "provider": "fake",
            "model": "fake-risk-model",
            "items": [
                {
                    "risk_hint_id": "risk_1",
                    "confidence_adjustment": 0.9,
                    "external_context_summary": "高" * 500,
                }
            ],
        },
    )

    assert enriched[0]["llm_enrichment"]["confidence_adjustment"] == 0.2
    assert enriched[0]["analysis_confidence"] == 0.98
    assert len(enriched[0]["llm_enrichment"]["external_context_summary"]) <= 200


def test_llm_enrichment_ignores_unknown_risk_ids():
    risk = {
        "risk_hint_id": "risk_1",
        "category": "remote_access",
        "severity": "high",
        "technical_evidence": ["target: vpn.example.org", "port: 443", "service: vpn"],
        "confidence": 0.78,
    }

    enriched = enrich_risk_hints(
        [risk],
        {
            "provider": "fake",
            "model": "fake-risk-model",
            "items": [
                {
                    "risk_hint_id": "risk_unknown",
                    "confidence_adjustment": 0.1,
                    "external_context_summary": "不应进入报告",
                }
            ],
        },
    )

    assert "llm_enrichment" not in enriched[0]


def test_llm_usage_metadata_is_sanitized():
    class FakeEnricher:
        def enrich(self, context):
            return {
                "provider": "fake",
                "model": "fake-risk-model",
                "items": [],
                "usage": {
                    "prompt_tokens": -100,
                    "completion_tokens": "12",
                    "estimated_cost_usd": "-3",
                    "ignored": "field",
                },
            }

    payload = run_discovery(
        seeds_path="examples/seeds.json",
        mode="fixture",
        fixture_path="tests/fixtures/fofa_results.json",
        analysis_mode="rules_plus_llm",
        llm_enricher=FakeEnricher(),
        data_sharing_level="minimal",
    )

    assert payload["analysis"]["usage"] == {
        "prompt_tokens": 0,
        "completion_tokens": 12,
        "total_tokens": 12,
        "estimated_cost_usd": 0.0,
    }
