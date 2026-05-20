from datetime import datetime, timezone

from resource_discovery.retention import RetentionPolicy, cleanup_expired_files, is_expired


def test_retention_policy_detects_expired_result_file(tmp_path):
    now = datetime(2026, 5, 20, tzinfo=timezone.utc)
    path = tmp_path / "result.json"
    path.write_text("{}", encoding="utf-8")

    assert is_expired(path, now=now, retention_days=90, modified_at=now.replace(year=2025)) is True
    assert is_expired(path, now=now, retention_days=180, modified_at=now) is False


def test_cleanup_expired_files_deletes_only_expired_files(tmp_path):
    now = datetime(2026, 5, 20, tzinfo=timezone.utc)
    expired = tmp_path / "tenant_a" / "expired.json"
    active = tmp_path / "tenant_a" / "active.json"
    expired.parent.mkdir()
    expired.write_text("expired", encoding="utf-8")
    active.write_text("active", encoding="utf-8")

    deleted = cleanup_expired_files(
        tmp_path,
        retention_days=30,
        now=now,
        modified_at_by_path={
            expired: now.replace(year=2025),
            active: now,
        },
    )

    assert deleted == [expired]
    assert not expired.exists()
    assert active.exists()


def test_retention_policy_defines_gateway_defaults():
    policy = RetentionPolicy.gateway_default()

    assert policy.task_metadata_days == 180
    assert policy.result_snapshot_days == 90
    assert policy.audit_log_days == 365
