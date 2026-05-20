from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from .execution import run_discovery
from .task_store import _safe_id


def validate_live_config(env: Mapping[str, str | None]) -> dict[str, str | None]:
    api_key = (env.get("FOFA_API_KEY") or "").strip()
    base_url = (env.get("FOFA_BASE_URL") or "").strip()
    if not api_key:
        raise ValueError("FOFA_API_KEY is required")
    if not base_url:
        raise ValueError("FOFA_BASE_URL is required")
    return {
        "fofa_key": api_key,
        "fofa_base_url": base_url,
        "fofa_email": (env.get("FOFA_API_EMAIL") or "").strip() or None,
    }


def build_live_seed_payload(domain: str) -> dict:
    safe_domain = _safe_id(domain.strip(), "domain")
    return {
        "tenant_id": "tenant_live_validation",
        "task_id": f"dt_live_{safe_domain.replace('.', '_')}",
        "seeds": [
            {
                "seed_id": "seed_001",
                "type": "root_domain",
                "value": safe_domain,
                "authorization_note": "Live validation domain explicitly authorized by customer.",
            }
        ],
    }


def run_live_validation(
    domain: str,
    *,
    output_dir: str | Path = "artifacts/live-validation",
    env: Mapping[str, str | None] | None = None,
    page_limit: int = 1,
    result_limit: int = 50,
) -> dict:
    config = validate_live_config(env or os.environ)
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    seed_path = target_dir / f"seeds-{timestamp}.json"
    seed_path.write_text(json.dumps(build_live_seed_payload(domain), ensure_ascii=False, indent=2), encoding="utf-8")
    payload = run_discovery(
        seeds_path=seed_path,
        mode="live",
        fofa_email=config["fofa_email"],
        fofa_key=config["fofa_key"],
        fofa_base_url=config["fofa_base_url"] or "",
        allow_live_fofa=True,
        page_limit=page_limit,
        result_limit=result_limit,
    )
    snapshot_path = target_dir / f"snapshot-{timestamp}.json"
    snapshot_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return build_summary(payload, snapshot_path=snapshot_path.as_posix())


def build_summary(payload: dict, *, snapshot_path: str) -> dict:
    freshness_counts: dict[str, int] = {}
    for service in payload.get("services", []):
        status = ((service.get("freshness") or {}).get("status")) or "unknown"
        freshness_counts[status] = freshness_counts.get(status, 0) + 1
    return {
        "status": (payload.get("task") or {}).get("status", "unknown"),
        "asset_count": len(payload.get("assets", [])),
        "service_count": len(payload.get("services", [])),
        "freshness_counts": freshness_counts,
        "snapshot_path": snapshot_path,
    }
