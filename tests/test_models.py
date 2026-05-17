from resource_discovery.models import SourceEvidence


def test_source_evidence_serialization_preserves_trace_fields():
    evidence = SourceEvidence(
        evidence_id="ev_001",
        task_id="dt_001",
        source="fofa",
        source_query='domain="example.org"',
        raw_reference="fofa:fixture:1",
        first_seen="2026-05-17T10:00:00+08:00",
        last_seen="2026-05-17T10:00:00+08:00",
        confidence=0.82,
        evidence={"domain": "vpn.example.org"},
        normalized_fields=["domain", "ip", "port"],
    )

    serialized = evidence.to_dict()

    assert serialized["source_query"] == 'domain="example.org"'
    assert serialized["raw_reference"] == "fofa:fixture:1"
    assert serialized["confidence"] == 0.82
    assert serialized["first_seen"] == "2026-05-17T10:00:00+08:00"
    assert serialized["last_seen"] == "2026-05-17T10:00:00+08:00"
    assert serialized["evidence"] == {"domain": "vpn.example.org"}
    assert serialized["normalized_fields"] == ["domain", "ip", "port"]
