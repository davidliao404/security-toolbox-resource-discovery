import json

import pytest

from resource_discovery.analysis_config import (
    AnalysisConfigError,
    TenantAnalysisConfig,
    load_tenant_analysis_config,
)
from resource_discovery.cli import run_and_maybe_save
from resource_discovery.execution import run_discovery


def _authorized_llm_config(**overrides):
    values = {
        "tenant_id": "tenant_poc",
        "llm_enabled": True,
        "llm_provider": "openai",
        "llm_model": "gpt-5.5",
        "web_search_enabled": True,
        "data_sharing_level": "minimal",
        "authorization_id": "llm_auth_001",
        "authorized_at": "2026-05-20T00:00:00Z",
        "authorized_by": "tenant_admin_hash",
    }
    values.update(overrides)
    return TenantAnalysisConfig(**values)


def test_disabled_tenant_analysis_config_resolves_rules_only():
    config = TenantAnalysisConfig(tenant_id="tenant_poc", llm_enabled=False)

    options = config.resolve_options("tenant_poc")

    assert options == {
        "analysis_mode": "rules_only",
        "web_search_enabled": False,
        "data_sharing_level": "none",
        "llm_provider": None,
        "llm_model": None,
        "llm_authorization_id": None,
    }


def test_enabled_tenant_analysis_config_requires_minimal_data_sharing():
    config = _authorized_llm_config(data_sharing_level="none")

    with pytest.raises(AnalysisConfigError, match="minimal"):
        config.resolve_options("tenant_poc")


def test_enabled_tenant_analysis_config_resolves_rules_plus_llm():
    config = _authorized_llm_config()

    options = config.resolve_options("tenant_poc")

    assert options == {
        "analysis_mode": "rules_plus_llm",
        "web_search_enabled": True,
        "data_sharing_level": "minimal",
        "llm_provider": "openai",
        "llm_model": "gpt-5.5",
        "llm_authorization_id": "llm_auth_001",
    }


def test_enabled_tenant_analysis_config_requires_authorization_record():
    config = TenantAnalysisConfig(
        tenant_id="tenant_poc",
        llm_enabled=True,
        llm_provider="openai",
        llm_model="gpt-5.5",
        data_sharing_level="minimal",
    )

    with pytest.raises(AnalysisConfigError, match="authorization"):
        config.resolve_options("tenant_poc")


def test_enabled_tenant_analysis_config_rejects_revoked_authorization():
    config = _authorized_llm_config(revoked_at="2026-05-20T01:00:00Z")

    with pytest.raises(AnalysisConfigError, match="revoked"):
        config.resolve_options("tenant_poc")


def test_tenant_analysis_config_rejects_tenant_mismatch():
    config = TenantAnalysisConfig(tenant_id="tenant_other", llm_enabled=False)

    with pytest.raises(AnalysisConfigError, match="tenant_id"):
        config.resolve_options("tenant_poc")


def test_load_tenant_analysis_config_from_json(tmp_path):
    path = tmp_path / "analysis-config.json"
    path.write_text(
        json.dumps(
            {
                "tenant_id": "tenant_poc",
                "llm_enabled": False,
                "web_search_enabled": True,
                "data_sharing_level": "minimal",
            }
        ),
        encoding="utf-8",
    )

    config = load_tenant_analysis_config(path)

    assert config.resolve_options("tenant_poc")["analysis_mode"] == "rules_only"
    assert config.resolve_options("tenant_poc")["data_sharing_level"] == "none"


def test_example_llm_tenant_analysis_config_is_valid():
    config = load_tenant_analysis_config("examples/tenant_analysis_llm.example.json")

    options = config.resolve_options("tenant_poc")

    assert options["analysis_mode"] == "rules_plus_llm"
    assert options["llm_authorization_id"] == "llm_auth_example_001"


def test_run_discovery_uses_enabled_tenant_analysis_config_with_injected_enricher():
    class FakeEnricher:
        def enrich(self, context):
            assert context["llm_provider"] == "openai"
            assert context["llm_model"] == "gpt-5.5"
            return {
                "items": [
                    {
                        "risk_hint_id": context["risks"][0]["risk_hint_id"],
                        "confidence_adjustment": 0.02,
                        "external_context_summary": "模型配置来自租户级授权。",
                    }
                ],
            }

    payload = run_discovery(
        seeds_path="examples/seeds.json",
        mode="fixture",
        fixture_path="tests/fixtures/fofa_results.json",
        tenant_analysis_config=_authorized_llm_config(),
        llm_enricher=FakeEnricher(),
    )

    assert payload["analysis"]["analysis_mode"] == "rules_plus_llm"
    assert payload["analysis"]["provider"] == "openai"
    assert payload["analysis"]["model"] == "gpt-5.5"
    assert payload["analysis"]["authorization_id"] == "llm_auth_001"


def test_run_and_maybe_save_uses_tenant_analysis_config_over_flags():
    payload = run_and_maybe_save(
        seeds_path="examples/seeds.json",
        mode="fixture",
        fixture_path="tests/fixtures/fofa_results.json",
        tenant_analysis_config=TenantAnalysisConfig(tenant_id="tenant_poc", llm_enabled=False),
        analysis_mode="rules_plus_llm",
        web_search_enabled=True,
        data_sharing_level="minimal",
    )

    assert payload["analysis"]["analysis_mode"] == "rules_only"
    assert payload["analysis"]["web_search_enabled"] is False
    assert payload["analysis"]["data_sharing_level"] == "none"
