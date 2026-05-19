from resource_discovery.analysis import build_minimal_llm_context
from resource_discovery.prompt_templates import (
    render_manager_summary_prompt,
    render_remediation_prompt,
    render_risk_confidence_prompt,
)


def _context():
    return build_minimal_llm_context(
        [
            {
                "risk_hint_id": "risk_1",
                "category": "remote_access",
                "severity": "high",
                "technical_evidence": ["target: vpn.example.org", "port: 443", "service: vpn"],
                "confidence": 0.78,
            }
        ],
        web_search_enabled=True,
        data_sharing_level="minimal",
        llm_provider="openai",
        llm_model="gpt-5.5",
    )


def test_risk_confidence_prompt_uses_minimal_context_and_schema():
    prompt = render_risk_confidence_prompt(_context())

    assert "不要宣称漏洞已确认" in prompt
    assert "confidence_adjustment" in prompt
    assert "external_context_summary" in prompt
    assert "target_hash" in prompt
    assert "vpn.example.org" not in prompt


def test_manager_summary_prompt_keeps_manager_language_boundary():
    prompt = render_manager_summary_prompt(_context())

    assert "面向非技术管理者" in prompt
    assert "保留证据链" in prompt
    assert "不得编造资产归属" in prompt


def test_remediation_prompt_preserves_local_verification_boundary():
    prompt = render_remediation_prompt(_context())

    assert "本地安全工具箱验证" in prompt
    assert "不要生成攻击步骤" in prompt
    assert "优先级调整建议" in prompt
