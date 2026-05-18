from resource_discovery.execution import run_discovery
from resource_discovery.report_renderer import render_html_report, render_markdown_report


def _payload():
    return run_discovery(
        seeds_path="examples/seeds.json",
        mode="fixture",
        fixture_path="tests/fixtures/fofa_results.json",
    )


def test_render_markdown_report_contains_manager_sections_and_appendix():
    markdown = render_markdown_report(_payload())

    assert markdown.startswith("# 互联网暴露面管理者报告")
    assert "## 管理者摘要" in markdown
    assert "本次被动发现识别到 4 个疑似互联网暴露资产" in markdown
    assert "## 优先处置建议" in markdown
    assert "## 整改优先级" in markdown
    assert "建议负责人：IT 管理员" in markdown
    assert "## 技术附录：暴露服务" in markdown
    assert "| vpn.example.org | 203.0.113.10 | 443 | https | vpn |" in markdown
    assert "所有发现均来自被动资产发现数据，需结合本地验证确认。" in markdown


def test_render_html_report_escapes_content_and_contains_summary():
    payload = _payload()
    payload["services"][0]["title"] = "<script>alert(1)</script>"

    html = render_html_report(payload)

    assert html.startswith("<!doctype html>")
    assert "<h1>互联网暴露面管理者报告</h1>" in html
    assert "本次被动发现识别到 4 个疑似互联网暴露资产" in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<script>alert(1)</script>" not in html
