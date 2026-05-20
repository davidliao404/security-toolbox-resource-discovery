from datetime import datetime, timezone

from resource_discovery.request_auth import (
    AuthError,
    InMemoryNonceStore,
    build_signature,
    verify_signature,
)


def test_build_and_verify_request_signature():
    now = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)
    signature = build_signature(
        secret="client-secret",
        method="POST",
        path="/api/v1/discovery/tasks",
        timestamp="2026-05-20T12:00:00+00:00",
        nonce="nonce-001",
        body=b'{"profile_id":"scope_profile_001"}',
    )

    result = verify_signature(
        secret="client-secret",
        method="POST",
        path="/api/v1/discovery/tasks",
        timestamp="2026-05-20T12:00:00+00:00",
        nonce="nonce-001",
        body=b'{"profile_id":"scope_profile_001"}',
        signature=signature,
        now=now,
        nonce_store=InMemoryNonceStore(),
    )

    assert result is True


def test_verify_signature_rejects_replay_nonce():
    now = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)
    nonce_store = InMemoryNonceStore()
    signature = build_signature(
        secret="client-secret",
        method="GET",
        path="/api/v1/discovery/scope-profile",
        timestamp="2026-05-20T12:00:00+00:00",
        nonce="nonce-001",
        body=b"",
    )

    verify_signature(
        secret="client-secret",
        method="GET",
        path="/api/v1/discovery/scope-profile",
        timestamp="2026-05-20T12:00:00+00:00",
        nonce="nonce-001",
        body=b"",
        signature=signature,
        now=now,
        nonce_store=nonce_store,
    )

    try:
        verify_signature(
            secret="client-secret",
            method="GET",
            path="/api/v1/discovery/scope-profile",
            timestamp="2026-05-20T12:00:00+00:00",
            nonce="nonce-001",
            body=b"",
            signature=signature,
            now=now,
            nonce_store=nonce_store,
        )
    except AuthError as exc:
        assert exc.code == "replay_detected"
    else:
        raise AssertionError("Expected replay nonce to be rejected")


def test_verify_signature_rejects_stale_timestamp_and_bad_signature():
    now = datetime(2026, 5, 20, 12, 10, tzinfo=timezone.utc)
    signature = build_signature(
        secret="client-secret",
        method="GET",
        path="/api/v1/discovery/scope-profile",
        timestamp="2026-05-20T12:00:00+00:00",
        nonce="nonce-001",
        body=b"",
    )

    try:
        verify_signature(
            secret="client-secret",
            method="GET",
            path="/api/v1/discovery/scope-profile",
            timestamp="2026-05-20T12:00:00+00:00",
            nonce="nonce-001",
            body=b"",
            signature=signature,
            now=now,
            allowed_skew_seconds=60,
            nonce_store=InMemoryNonceStore(),
        )
    except AuthError as exc:
        assert exc.code == "timestamp_out_of_window"
    else:
        raise AssertionError("Expected stale timestamp to be rejected")

    try:
        verify_signature(
            secret="client-secret",
            method="GET",
            path="/api/v1/discovery/scope-profile",
            timestamp="2026-05-20T12:10:00+00:00",
            nonce="nonce-002",
            body=b"",
            signature="bad",
            now=now,
            nonce_store=InMemoryNonceStore(),
        )
    except AuthError as exc:
        assert exc.code == "invalid_signature"
    else:
        raise AssertionError("Expected bad signature to be rejected")
