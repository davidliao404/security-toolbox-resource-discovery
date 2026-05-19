from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class RuleMatch:
    ports: list[int]
    keywords: list[str]


@dataclass(frozen=True)
class RiskRule:
    category: str
    severity: str
    title: str
    manager_summary: str
    recommended_action: str
    owner_hint: str
    priority_rank: int
    match: RuleMatch


@dataclass(frozen=True)
class RiskRuleSet:
    version: int
    default_confidence: float
    rules: list[RiskRule]


def load_risk_rules(path: str | Path | None = None) -> RiskRuleSet:
    if path is None:
        with resources.files("resource_discovery").joinpath("risk_rules.yml").open(
            "r",
            encoding="utf-8",
        ) as handle:
            payload = yaml.safe_load(handle)
    else:
        payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return _parse_ruleset(payload)


def rule_matches(rule: RiskRule, port: int, text: str) -> bool:
    port_match = port in rule.match.ports
    text_lower = text.lower()
    keyword_match = any(keyword.lower() in text_lower for keyword in rule.match.keywords)
    return port_match or keyword_match


def _parse_ruleset(payload: dict[str, Any]) -> RiskRuleSet:
    return RiskRuleSet(
        version=int(payload.get("version", 1)),
        default_confidence=float(payload.get("default_confidence", 0.78)),
        rules=[_parse_rule(item) for item in payload.get("rules", [])],
    )


def _parse_rule(payload: dict[str, Any]) -> RiskRule:
    match = payload.get("match") or {}
    return RiskRule(
        category=payload["category"],
        severity=payload["severity"],
        title=payload["title"],
        manager_summary=payload["manager_summary"],
        recommended_action=payload["recommended_action"],
        owner_hint=payload.get("owner_hint", "IT 管理员"),
        priority_rank=int(payload.get("priority_rank", 100)),
        match=RuleMatch(
            ports=[int(port) for port in match.get("ports", [])],
            keywords=[str(keyword) for keyword in match.get("keywords", [])],
        ),
    )
