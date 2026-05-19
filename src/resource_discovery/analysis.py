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
    llm_provider: str | None = None,
    llm_model: str | None = None,
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
        llm_provider=llm_provider,
        llm_model=llm_model,
    )
    enrichment = llm_enricher.enrich(context)
    provider = enrichment.get("provider") or llm_provider
    model = enrichment.get("model") or llm_model
    enriched_payload = {**enrichment, "provider": provider, "model": model}
    return enrich_risk_hints(risk_hints, enriched_payload), {
        "analysis_mode": "rules_plus_llm",
        "llm_enabled": True,
        "web_search_enabled": web_search_enabled,
        "data_sharing_level": data_sharing_level,
        "provider": provider,
        "model": model,
    }


def build_minimal_llm_context(
    risk_hints: list[dict[str, Any]],
    web_search_enabled: bool,
    data_sharing_level: str = "minimal",
    llm_provider: str | None = None,
    llm_model: str | None = None,
) -> dict[str, Any]:
    return {
        "data_sharing_level": data_sharing_level,
        "web_search_enabled": web_search_enabled,
        "llm_provider": llm_provider,
        "llm_model": llm_model,
        "risks": [_minimal_risk_context(risk) for risk in risk_hints],
    }


def enrich_risk_hints(
    risk_hints: list[dict[str, Any]],
    enrichment: dict[str, Any],
) -> list[dict[str, Any]]:
    raw_items = enrichment.get("items", [])
    if not isinstance(raw_items, list):
        raw_items = []
    items = {
        item.get("risk_hint_id"): item
        for item in raw_items
        if isinstance(item, dict) and item.get("risk_hint_id")
    }
    enriched: list[dict[str, Any]] = []
    for risk in risk_hints:
        item = items.get(risk.get("risk_hint_id"))
        if item is None:
            enriched.append(risk)
            continue
        confidence_adjustment = _bounded_adjustment(item.get("confidence_adjustment", 0))
        enriched.append(
            {
                **risk,
                "analysis_confidence": _adjusted_confidence(
                    risk.get("confidence", 0),
                    confidence_adjustment,
                ),
                "llm_enrichment": {
                    "provider": enrichment.get("provider"),
                    "model": enrichment.get("model"),
                    "confidence_adjustment": confidence_adjustment,
                    "external_context_summary": _safe_summary(
                        item.get("external_context_summary", "")
                    ),
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


def _bounded_adjustment(value: Any) -> float:
    try:
        adjustment = float(value)
    except (TypeError, ValueError):
        adjustment = 0.0
    return round(min(max(adjustment, -0.2), 0.2), 4)


def _safe_summary(value: Any, max_length: int = 200) -> str:
    text = str(value or "").strip()
    if len(text) <= max_length:
        return text
    return text[:max_length]
