from resource_discovery.cli import export_report, run_and_maybe_save


def test_export_report_writes_markdown_file(tmp_path):
    payload = run_and_maybe_save(
        seeds_path="examples/seeds.json",
        mode="fixture",
        fixture_path="tests/fixtures/fofa_results.json",
    )
    output_path = tmp_path / "report.md"

    saved_path = export_report(payload, output_path, "markdown")

    assert saved_path == output_path
    text = output_path.read_text(encoding="utf-8")
    assert "# 互联网暴露面管理者报告" in text
    assert "## 技术附录：暴露服务" in text


def test_export_report_writes_html_file(tmp_path):
    payload = run_and_maybe_save(
        seeds_path="examples/seeds.json",
        mode="fixture",
        fixture_path="tests/fixtures/fofa_results.json",
    )
    output_path = tmp_path / "report.html"

    saved_path = export_report(payload, output_path, "html")

    assert saved_path == output_path
    text = output_path.read_text(encoding="utf-8")
    assert "<!doctype html>" in text
    assert "<h1>互联网暴露面管理者报告</h1>" in text
