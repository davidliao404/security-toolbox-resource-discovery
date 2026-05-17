from __future__ import annotations

from datetime import datetime, timezone

from .models import DiscoveredAsset, ExposedService, ExposureReport, RiskHint


def build_exposure_report(
    task_id: str,
    tenant_id: str,
    assets: list[DiscoveredAsset],
    services: list[ExposedService],
    risk_hints: list[RiskHint],
) -> ExposureReport:
    high_risks = [risk for risk in risk_hints if risk.severity in {"critical", "high"}]
    generated_at = datetime.now(timezone.utc).isoformat()
    summary_text = (
        f"本次被动发现识别到 {len(assets)} 个疑似互联网暴露资产、"
        f"{len(services)} 个暴露服务，其中 {len(high_risks)} 项建议优先复核。"
    )
    recommendations = [
        risk.recommended_action for risk in high_risks[:5]
    ] or ["未发现高优先级线索，建议保留周期性暴露面复查。"]
    sections = [
        {
            "title": "管理者摘要",
            "items": [summary_text, "所有发现均来自被动资产发现数据，需结合本地验证确认。"],
        },
        {
            "title": "优先处置建议",
            "items": recommendations,
        },
        {
            "title": "关键风险线索",
            "items": [risk.title for risk in high_risks[:10]],
        },
    ]
    return ExposureReport(
        report_id=f"report_{task_id}",
        task_id=task_id,
        tenant_id=tenant_id,
        report_type="manager_summary",
        generated_at=generated_at,
        executive_summary={
            "asset_count": len(assets),
            "service_count": len(services),
            "high_risk_hint_count": len(high_risks),
            "risk_hint_count": len(risk_hints),
            "summary_text": summary_text,
        },
        sections=sections,
        appendix_refs=["asset_list", "service_list", "source_evidence"],
    )
