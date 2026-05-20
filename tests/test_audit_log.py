import json

from resource_discovery.analysis_config import TenantAnalysisConfig
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
    assert events[-1]["details"]["analysis_mode"] == "rules_only"
    assert events[-1]["details"]["llm_enabled"] is False


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


def test_run_and_save_records_llm_analysis_audit_event(tmp_path):
    class FakeEnricher:
        def enrich(self, context):
            return {
                "items": [
                    {
                        "risk_hint_id": context["risks"][0]["risk_hint_id"],
                        "confidence_adjustment": 0.01,
                        "external_context_summary": "租户已授权模型增强。",
                    }
                ],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15,
                    "estimated_cost_usd": 0.0003,
                },
            }

    run_and_maybe_save(
        seeds_path="examples/seeds.json",
        mode="fixture",
        fixture_path="tests/fixtures/fofa_results.json",
        tenant_analysis_config=TenantAnalysisConfig(
            tenant_id="tenant_poc",
            llm_enabled=True,
            llm_provider="openai",
            llm_model="gpt-5.5",
            web_search_enabled=True,
            data_sharing_level="minimal",
        ),
        llm_enricher=FakeEnricher(),
        audit_log=tmp_path / "audit.jsonl",
    )

    events = [
        json.loads(line)
        for line in (tmp_path / "audit.jsonl").read_text(encoding="utf-8").splitlines()
    ]

    assert [event["event_type"] for event in events] == [
        "task_started",
        "llm_analysis_used",
        "task_completed",
    ]
    assert events[1]["details"] == {
        "provider": "openai",
        "model": "gpt-5.5",
        "web_search_enabled": True,
        "data_sharing_level": "minimal",
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15,
            "estimated_cost_usd": 0.0003,
        },
    }
