import pytest

from resource_discovery.execution import LiveExecutionDisabled, run_discovery


def test_dry_run_returns_query_plans_without_assets_or_live_api():
    payload = run_discovery(
        seeds_path="examples/seeds.json",
        mode="dry-run",
        fixture_path=None,
    )

    assert payload["mode"] == "dry-run"
    assert payload["live_api_enabled"] is False
    assert [plan["query_type"] for plan in payload["query_plans"]] == [
        "domain",
        "organization",
        "ip_range",
    ]
    assert payload["assets"] == []
    assert payload["services"] == []
    assert payload["risk_hints"] == []


def test_fixture_mode_requires_fixture_path():
    with pytest.raises(ValueError, match="fixture_path"):
        run_discovery(seeds_path="examples/seeds.json", mode="fixture", fixture_path=None)


def test_live_mode_requires_explicit_allow_live_flag():
    with pytest.raises(LiveExecutionDisabled, match="explicitly enabled"):
        run_discovery(
            seeds_path="examples/seeds.json",
            mode="live",
            fixture_path=None,
            fofa_email="user@example.org",
            fofa_key="secret",
            allow_live_fofa=False,
        )


def test_live_mode_requires_credentials_after_enable_flag():
    with pytest.raises(LiveExecutionDisabled, match="FOFA credentials"):
        run_discovery(
            seeds_path="examples/seeds.json",
            mode="live",
            fixture_path=None,
            allow_live_fofa=True,
        )
