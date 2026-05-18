from __future__ import annotations

from typing import Any


SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
CATEGORY_RANK = {
    "database_exposure": 0,
    "admin_portal": 1,
    "remote_access": 2,
    "middleware_exposure": 3,
    "test_environment": 4,
}


def build_remediation_plan(risk_hints: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(
        risk_hints,
        key=lambda risk: (
            SEVERITY_RANK.get(risk.get("severity"), 9),
            CATEGORY_RANK.get(risk.get("category"), 9),
            -float(risk.get("confidence", 0)),
            risk.get("title", ""),
        ),
    )
    actions = []
    for index, risk in enumerate(ordered, start=1):
        actions.append(
            {
                "priority": index,
                "severity": risk.get("severity"),
                "category": risk.get("category"),
                "title": risk.get("title"),
                "target": _target_from_evidence(risk.get("technical_evidence", [])),
                "manager_summary": risk.get("manager_summary"),
                "recommended_action": risk.get("recommended_action"),
                "owner_hint": _owner_for(risk.get("category")),
                "verification_required": bool(risk.get("verification_required", True)),
                "confidence": risk.get("confidence", 0),
            }
        )
    return {
        "summary": {
            "total_actions": len(actions),
            "high_priority_actions": sum(
                1 for action in actions if action.get("severity") in {"critical", "high"}
            ),
        },
        "actions": actions,
    }


def _target_from_evidence(evidence: list[str]) -> str:
    for item in evidence:
        if item.startswith("target: "):
            return item.removeprefix("target: ")
    return "unknown"


def _owner_for(category: str | None) -> str:
    if category in {"database_exposure", "middleware_exposure"}:
        return "IT 管理员"
    if category in {"admin_portal", "remote_access"}:
        return "IT 管理员"
    return "系统负责人"
