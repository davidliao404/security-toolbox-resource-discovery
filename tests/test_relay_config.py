import os

import pytest

from resource_discovery.cli import fofa_credentials_from_env
from resource_discovery.execution import LiveExecutionDisabled, run_discovery


def test_fofa_credentials_from_env_reads_key_only_relay_config(monkeypatch):
    monkeypatch.setenv("FOFA_API_KEY", "secret")
    monkeypatch.setenv("FOFA_BASE_URL", "http://fofa.icu/api/v1/search/all")
    monkeypatch.delenv("FOFA_API_EMAIL", raising=False)

    credentials = fofa_credentials_from_env()

    assert credentials == {
        "fofa_email": None,
        "fofa_key": "secret",
        "fofa_base_url": "http://fofa.icu/api/v1/search/all",
    }


def test_live_mode_accepts_key_only_relay_config_with_injected_client():
    class EmptyClient:
        def fetch(self, plan):
            return []

    payload = run_discovery(
        seeds_path="examples/seeds.json",
        mode="live",
        allow_live_fofa=True,
        fofa_key="secret",
        fofa_base_url="http://fofa.icu/api/v1/search/all",
        page_limit=1,
        result_limit=20,
        source_client=EmptyClient(),
    )

    assert payload["mode"] == "live"
    assert payload["live_api_enabled"] is True
    assert payload["task"]["status"] == "success"
    assert payload["task"]["quota_usage"]["planned_pages"] == 3


def test_live_mode_requires_key_even_when_email_is_absent():
    with pytest.raises(LiveExecutionDisabled, match="FOFA credentials"):
        run_discovery(
            seeds_path="examples/seeds.json",
            mode="live",
            allow_live_fofa=True,
            fofa_email=None,
            fofa_key=None,
        )
