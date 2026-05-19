from __future__ import annotations

import hashlib

from .models import ExposedService, RiskHint
from .risk_rules import RiskRule, load_risk_rules, rule_matches


def _risk_id(task_id: str, service_id: str, category: str) -> str:
    digest = hashlib.sha1(f"{task_id}|{service_id}|{category}".encode("utf-8")).hexdigest()[:12]
    return f"risk_{digest}"


def generate_risk_hints(task_id: str, services: list[ExposedService]) -> list[RiskHint]:
    ruleset = load_risk_rules()
    hints: list[RiskHint] = []
    for service in services:
        text = " ".join(
            value.lower()
            for value in [service.service, service.title, service.product, service.domain, service.url]
            if value
        )
        for rule in _matching_rules(service, text, ruleset.rules):
            hints.append(
                RiskHint(
                    risk_hint_id=_risk_id(task_id, service.service_id, rule.category),
                    task_id=task_id,
                    asset_id=service.asset_id,
                    service_id=service.service_id,
                    category=rule.category,
                    severity=rule.severity,
                    title=rule.title,
                    manager_summary=rule.manager_summary,
                    technical_evidence=[
                        f"target: {service.domain or service.ip}",
                        f"port: {service.port}",
                        f"service: {service.service}",
                    ],
                    recommended_action=rule.recommended_action,
                    confidence=ruleset.default_confidence,
                    verification_required=True,
                )
            )
    return hints


def _matching_rules(service: ExposedService, text: str, rules: list[RiskRule]) -> list[RiskRule]:
    return [rule for rule in rules if rule_matches(rule, service.port, text)]
