import json

from resource_discovery.repositories import FileScopeProfileRepository


def test_scope_profile_repository_loads_example_profile(tmp_path):
    profile_path = tmp_path / "tenant_poc.scope_profile_001.json"
    profile_path.write_text(open("examples/scope_profile.json", encoding="utf-8").read(), encoding="utf-8")

    profile = FileScopeProfileRepository(tmp_path).load_active("tenant_poc", "scope_profile_001")

    assert profile.tenant_id == "tenant_poc"
    assert profile.profile_id == "scope_profile_001"
    assert profile.default_scope == {"root_domains": ["example.org"]}


def test_scope_profile_repository_rejects_inactive_profile(tmp_path):
    payload = json.loads(open("examples/scope_profile.json", encoding="utf-8").read())
    payload["status"] = "inactive"
    (tmp_path / "tenant_poc.scope_profile_001.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )

    try:
        FileScopeProfileRepository(tmp_path).load_active("tenant_poc", "scope_profile_001")
    except ValueError as exc:
        assert "not active" in str(exc)
    else:
        raise AssertionError("Expected inactive profile to be rejected")


def test_scope_profile_repository_rejects_profile_id_mismatch(tmp_path):
    payload = json.loads(open("examples/scope_profile.json", encoding="utf-8").read())
    payload["profile_id"] = "scope_profile_other"
    (tmp_path / "tenant_poc.scope_profile_001.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )

    try:
        FileScopeProfileRepository(tmp_path).load_active("tenant_poc", "scope_profile_001")
    except ValueError as exc:
        assert "does not match requested profile" in str(exc)
    else:
        raise AssertionError("Expected mismatched profile ID to be rejected")


def test_scope_profile_repository_preserves_approval_metadata(tmp_path):
    payload = json.loads(open("examples/scope_profile.json", encoding="utf-8").read())
    payload["approval"] = {
        "approved_by": "security-admin",
        "approved_at": "2026-05-25T10:00:00+08:00",
        "ticket_id": "SEC-2026-0525",
    }
    (tmp_path / "tenant_poc.scope_profile_001.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )

    profile = FileScopeProfileRepository(tmp_path).load_active("tenant_poc", "scope_profile_001")

    assert profile.approval == {
        "approved_by": "security-admin",
        "approved_at": "2026-05-25T10:00:00+08:00",
        "ticket_id": "SEC-2026-0525",
    }
