from __future__ import annotations

import hashlib
from typing import Any, Protocol


class LlmAnalysisUnavailable(RuntimeError):
    """Raised when LLM analysis is requested without an enabled enricher."""


class LlmRiskEnricher(Protocol):
    def enrich(self, context: dict[str, Any]) -> dict[str, Any]:
        """Return enrichment data for the supplied minimal risk context."""


def apply_analysis(
    risk_hints: list[dict[str, Any]],
    analysis_mode: str = "rules_only",
    llm_enricher: LlmRiskEnricher | None = None,
    web_search_enabled: bool = False,
    data_sharing_level: str = "none",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if analysis_mode == "rules_only":
        return risk_hints, {
            "analysis_mode": "rules_only",
            "llm_enabled": False,
            "web_search_enabled": False,
            "data_sharing_level": "none",
        }
    if analysis_mode != "rules_plus_llm":
        raise ValueError(f"Unsupported analysis_mode: {analysis_mode}")
    if llm_enricher is None:
        raise LlmAnalysisUnavailable("rules_plus_llm requires an explicit LLM enricher")

    context = build_minimal_llm_context(
        risk_hints,
        web_search_enabled=web_search_enabled,
        data_sharing_level=data_sharing_level,
    )
    enrichment = llm_enricher.enrich(context)
    return enrich_risk_hints(risk_hints, enrichment), {
        "analysis_mode": "rules_plus_llm",
        "llm_enabled": True,
        "web_search_enabled": web_search_enabled,
        "data_sharing_level": data_sharing_level,
        "provider": enrichment.get("provider"),
        "model": enrichment.get("model"),
    }


def build_minimal_llm_context(
    risk_hints: list[dict[str, Any]],
    web_search_enabled: bool,
    data_sharing_level: str = "minimal",
) -> dict[str, Any]:
    return {
        "data_sharing_level": data_sharing_level,
        "web_search_enabled": web_search_enabled,
        "risks": [_minimal_risk_context(risk) for risk in risk_hints],
    }


def enrich_risk_hints(
    risk_hints: list[dict[str, Any]],
    enrichment: dict[str, Any],
) -> list[dict[str, Any]]:
    items = {
        item.get("risk_hint_id"): item
        for item in enrichment.get("items", [])
        if item.get("risk_hint_id")
    }
    enriched: list[dict[str, Any]] = []
    for risk in risk_hints:
        item = items.get(risk.get("risk_hint_id"))
        if item is None:
            enriched.append(risk)
            continue
        enriched.append(
            {
                **risk,
                "analysis_confidence": _adjusted_confidence(
                    risk.get("confidence", 0),
                    item.get("confidence_adjustment", 0),
                ),
                "llm_enrichment": {
                    "provider": enrichment.get("provider"),
                    "model": enrichment.get("model"),
                    "confidence_adjustment": item.get("confidence_adjustment", 0),
                    "external_context_summary": item.get("external_context_summary", ""),
                },
            }
        )
    return enriched


def _minimal_risk_context(risk: dict[str, Any]) -> dict[str, Any]:
    evidence = risk.get("technical_evidence", [])
    target = _evidence_value(evidence, "target")
    return {
        "risk_hint_id": risk.get("risk_hint_id"),
        "category": risk.get("category"),
        "severity": risk.get("severity"),
        "confidence": risk.get("confidence"),
        "target_hash": _hash_value(target),
        "port": _evidence_value(evidence, "port"),
        "service": _evidence_value(evidence, "service"),
    }


def _evidence_value(evidence: list[str], key: str) -> str:
    prefix = f"{key}: "
    for item in evidence:
        if item.startswith(prefix):
            return item.removeprefix(prefix)
    return ""


def _hash_value(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16] if value else ""


def _adjusted_confidence(base_confidence: Any, adjustment: Any) -> float:
    try:
        adjusted = float(base_confidence) + float(adjustment)
    except (TypeError, ValueError):
        adjusted = 0.0
    return round(min(max(adjusted, 0.0), 1.0), 4)
