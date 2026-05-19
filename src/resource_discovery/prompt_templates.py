from __future__ import annotations

import json
from typing import Any


def render_risk_confidence_prompt(context: dict[str, Any]) -> str:
    return _render_prompt(
        purpose="风险置信度增强",
        instructions=[
            "你是互联网暴露面报告的安全分析助手。",
            "只能基于输入中的最小化被动发现线索和可公开检索的信息进行判断。",
            "不要宣称漏洞已确认，不要输出攻击步骤，不要补充输入中不存在的资产归属。",
            "如果启用了网络搜索，只能用于确认公开风险背景、产品生命周期或常见暴露风险。",
            "输出必须是 JSON，不要输出 Markdown。",
        ],
        output_schema={
            "items": [
                {
                    "risk_hint_id": "string",
                    "confidence_adjustment": "number between -0.2 and 0.2",
                    "external_context_summary": "manager-readable short Chinese summary",
                    "reasoning_evidence": ["short public-context bullet"],
                }
            ]
        },
        context=context,
    )


def render_manager_summary_prompt(context: dict[str, Any]) -> str:
    return _render_prompt(
        purpose="管理者摘要增强",
        instructions=[
            "你是面向非技术管理者的安全报告编辑助手。",
            "把技术线索改写为清晰、克制、可行动的中文说明。",
            "保留证据链，明确这些结论来自被动发现线索，需要后续本地验证。",
            "不得编造资产归属、业务影响、攻击事实或漏洞确认结论。",
            "输出必须是 JSON，不要输出 Markdown。",
        ],
        output_schema={
            "items": [
                {
                    "risk_hint_id": "string",
                    "manager_summary": "manager-readable Chinese summary",
                    "evidence_note": "short evidence-chain explanation",
                }
            ]
        },
        context=context,
    )


def render_remediation_prompt(context: dict[str, Any]) -> str:
    return _render_prompt(
        purpose="整改建议增强",
        instructions=[
            "你是企业 IT 管理者的安全整改建议助手。",
            "整改建议必须指向本地安全工具箱验证、访问控制复核、配置加固或下线不必要暴露。",
            "不要生成攻击步骤、利用代码、绕过认证方法或弱口令尝试建议。",
            "可以给出优先级调整建议，但不能覆盖规则引擎的确定性证据。",
            "输出必须是 JSON，不要输出 Markdown。",
        ],
        output_schema={
            "items": [
                {
                    "risk_hint_id": "string",
                    "priority_adjustment": "integer between -2 and 2",
                    "recommended_action": "safe local verification or remediation action",
                    "owner_hint": "suggested owner role",
                }
            ]
        },
        context=context,
    )


def _render_prompt(
    purpose: str,
    instructions: list[str],
    output_schema: dict[str, Any],
    context: dict[str, Any],
) -> str:
    return "\n".join(
        [
            f"# 任务：{purpose}",
            "",
            "## 约束",
            *[f"- {instruction}" for instruction in instructions],
            "",
            "## 输出格式",
            json.dumps(output_schema, ensure_ascii=False, indent=2),
            "",
            "## 输入上下文",
            json.dumps(context, ensure_ascii=False, indent=2, sort_keys=True),
        ]
    )
