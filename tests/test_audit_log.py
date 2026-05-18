import json

from resource_discovery.audit import AuditEvent, JsonlAuditLogger
from resource_discovery.cli import export_report, run_and_maybe_save


def test_jsonl_audit_logger_appends_events(tmp_path):
    logger = JsonlAuditLogger(tmp_path / "audit.jsonl")

    logger.record(AuditEvent(event_type="task_started", tenant_id="tenant_poc", task_id="dt_poc_001"))
    logger.record(
        AuditEvent(
            event_type="task_completed",
            tenant_id="tenant_poc",
            task_id="dt_poc_001",
            details={"status": "success"},
        )
    )

    lines = (tmp_path / "audit.jsonl").read_text(encoding="utf-8").splitlines()
    events = [json.loads(line) for line in lines]

    assert [event["event_type"] for event in events] == ["task_started", "task_completed"]
    assert events[1]["details"] == {"status": "success"}
    assert events[0]["occurred_at"]


def test_run_and_save_records_audit_events(tmp_path):
    payload = run_and_maybe_save(
        seeds_path="examples/seeds.json",
        mode="fixture",
        fixture_path="tests/fixtures/fofa_results.json",
        save_dir=tmp_path / "snapshots",
        audit_log=tmp_path / "audit.jsonl",
    )

    events = [
        json.loads(line)
        for line in (tmp_path / "audit.jsonl").read_text(encoding="utf-8").splitlines()
    ]

    assert payload["task"]["status"] == "success"
    assert [event["event_type"] for event in events] == [
        "task_started",
        "snapshot_saved",
        "task_completed",
    ]
    assert events[-1]["details"]["status"] == "success"


def test_export_report_records_audit_event(tmp_path):
    payload = run_and_maybe_save(
        seeds_path="examples/seeds.json",
        mode="fixture",
        fixture_path="tests/fixtures/fofa_results.json",
    )
    export_report(payload, tmp_path / "report.md", "markdown", audit_log=tmp_path / "audit.jsonl")

    event = json.loads((tmp_path / "audit.jsonl").read_text(encoding="utf-8").splitlines()[0])

    assert event["event_type"] == "report_exported"
    assert event["tenant_id"] == "tenant_poc"
    assert event["task_id"] == "dt_poc_001"
    assert event["details"]["format"] == "markdown"
