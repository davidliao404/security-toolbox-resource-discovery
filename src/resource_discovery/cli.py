from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .audit import AuditEvent, JsonlAuditLogger
from .execution import run_discovery
from .report_renderer import render_html_report, render_markdown_report
from .task_store import FileTaskStore


def run_fixture_demo(seeds_path, fixture_path) -> dict:
    return run_discovery(seeds_path=seeds_path, mode="fixture", fixture_path=fixture_path)


def run_and_maybe_save(
    seeds_path,
    mode="fixture",
    fixture_path=None,
    fofa_email=None,
    fofa_key=None,
    fofa_base_url=None,
    allow_live_fofa=False,
    save_dir=None,
    audit_log=None,
) -> dict:
    audit_logger = JsonlAuditLogger(audit_log) if audit_log is not None else None
    payload = run_discovery(
        seeds_path=seeds_path,
        mode=mode,
        fixture_path=fixture_path,
        fofa_email=fofa_email,
        fofa_key=fofa_key,
        fofa_base_url=fofa_base_url or "https://fofa.info/api/v1/search/all",
        allow_live_fofa=allow_live_fofa,
    )
    _record(audit_logger, payload, "task_started", {"mode": mode})
    if save_dir is not None:
        saved_path = FileTaskStore(save_dir).save(payload)
        payload = {**payload, "saved_snapshot_path": _display_path(saved_path)}
        _record(audit_logger, payload, "snapshot_saved", {"path": _display_path(saved_path)})
    _record(
        audit_logger,
        payload,
        "task_completed",
        {
            "status": payload.get("task", {}).get("status"),
            "asset_count": len(payload.get("assets", [])),
            "risk_hint_count": len(payload.get("risk_hints", [])),
        },
    )
    return payload


def list_snapshots(save_dir, tenant_id) -> list[dict]:
    return FileTaskStore(save_dir).list(tenant_id)


def load_snapshot(save_dir, tenant_id, task_id) -> dict:
    return FileTaskStore(save_dir).load(tenant_id, task_id)


def export_report(payload: dict, output_path, report_format: str, audit_log=None):
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if report_format == "markdown":
        text = render_markdown_report(payload)
    elif report_format == "html":
        text = render_html_report(payload)
    else:
        raise ValueError(f"Unsupported report format: {report_format}")
    path.write_text(text, encoding="utf-8")
    if audit_log is not None:
        _record(
            JsonlAuditLogger(audit_log),
            payload,
            "report_exported",
            {"path": _display_path(path), "format": report_format},
        )
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run offline FOFA resource discovery PoC.")
    parser.add_argument("--seeds", required=True, help="Path to seeds JSON file.")
    parser.add_argument("--mode", choices=["fixture", "dry-run", "live"], default="fixture")
    parser.add_argument("--fixture", help="Path to FOFA-like fixture JSON file.")
    parser.add_argument("--fofa-email", help="FOFA account email for live mode.")
    parser.add_argument("--fofa-key", help="FOFA API key for live mode.")
    parser.add_argument("--fofa-base-url", help="FOFA-compatible search endpoint.")
    parser.add_argument("--allow-live-fofa", action="store_true", help="Explicitly enable live FOFA API calls.")
    parser.add_argument("--save-dir", help="Directory for persisted task snapshots.")
    parser.add_argument("--list-snapshots", action="store_true", help="List persisted task snapshot summaries.")
    parser.add_argument("--show-snapshot", help="Load and print a persisted task snapshot by task ID.")
    parser.add_argument("--tenant-id", help="Tenant ID for listing or showing snapshots.")
    parser.add_argument("--export-report", help="Write manager-readable report to this path.")
    parser.add_argument("--report-format", choices=["markdown", "html"], default="markdown")
    parser.add_argument("--audit-log", help="Append JSONL audit events to this file.")
    args = parser.parse_args()
    credentials = fofa_credentials_from_env()
    fofa_email = args.fofa_email if args.fofa_email is not None else credentials["fofa_email"]
    fofa_key = args.fofa_key if args.fofa_key is not None else credentials["fofa_key"]
    fofa_base_url = args.fofa_base_url if args.fofa_base_url is not None else credentials["fofa_base_url"]
    if args.list_snapshots:
        payload = list_snapshots(_required_save_dir(args.save_dir), _required_tenant_id(args.tenant_id))
    elif args.show_snapshot:
        payload = load_snapshot(
            _required_save_dir(args.save_dir),
            _required_tenant_id(args.tenant_id),
            args.show_snapshot,
        )
    else:
        payload = run_and_maybe_save(
            seeds_path=args.seeds,
            mode=args.mode,
            fixture_path=args.fixture,
            fofa_email=fofa_email,
            fofa_key=fofa_key,
            fofa_base_url=fofa_base_url,
            allow_live_fofa=args.allow_live_fofa,
            save_dir=args.save_dir,
            audit_log=args.audit_log,
        )
    if args.export_report and isinstance(payload, dict) and payload.get("report"):
        saved_report = export_report(payload, args.export_report, args.report_format, audit_log=args.audit_log)
        payload = {**payload, "exported_report_path": _display_path(saved_report)}
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _required_save_dir(save_dir):
    if not save_dir:
        raise SystemExit("--save-dir is required")
    return save_dir


def _required_tenant_id(tenant_id):
    if not tenant_id:
        raise SystemExit("--tenant-id is required")
    return tenant_id


def _display_path(path: Path) -> str:
    return path.as_posix()


def fofa_credentials_from_env() -> dict:
    return {
        "fofa_email": os.environ.get("FOFA_API_EMAIL"),
        "fofa_key": os.environ.get("FOFA_API_KEY"),
        "fofa_base_url": os.environ.get("FOFA_BASE_URL", "https://fofa.info/api/v1/search/all"),
    }


def _record(logger, payload: dict, event_type: str, details: dict) -> None:
    if logger is None:
        return
    task = payload.get("task") or {}
    logger.record(
        AuditEvent(
            event_type=event_type,
            tenant_id=task.get("tenant_id", "unknown"),
            task_id=task.get("task_id", "unknown"),
            details=details,
        )
    )


if __name__ == "__main__":
    main()
