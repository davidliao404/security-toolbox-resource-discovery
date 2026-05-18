from __future__ import annotations

from html import escape
from typing import Any


def render_markdown_report(payload: dict[str, Any]) -> str:
    report = payload["report"]
    task = payload.get("task", {})
    summary = report["executive_summary"]
    services = payload.get("services", [])
    risks = payload.get("risk_hints", [])
    remediation = payload.get("remediation", {})

    lines = [
        "# 互联网暴露面管理者报告",
        "",
        f"- 任务 ID：`{task.get('task_id', report.get('task_id'))}`",
        f"- 任务状态：`{task.get('status', 'unknown')}`",
        f"- 资产数量：{summary.get('asset_count', 0)}",
        f"- 暴露服务数量：{summary.get('service_count', 0)}",
        f"- 高优先级线索：{summary.get('high_risk_hint_count', 0)}",
        "",
        "## 管理者摘要",
        "",
        summary["summary_text"],
        "",
        "所有发现均来自被动资产发现数据，需结合本地验证确认。",
        "",
        "## 优先处置建议",
        "",
    ]
    recommendation_section = _section(report, "优先处置建议")
    lines.extend(f"- {item}" for item in recommendation_section.get("items", []))
    lines.extend(["", "## 关键风险线索", ""])
    for risk in risks:
        lines.append(
            f"- **{risk['severity']}** {risk['title']}：{risk['manager_summary']} "
            f"(置信度 {risk['confidence']})"
        )
    lines.extend(["", "## 整改优先级", ""])
    for action in remediation.get("actions", [])[:10]:
        lines.append(
            f"{action['priority']}. [{action['severity']}] {action['target']} - "
            f"{action['recommended_action']}（建议负责人：{action['owner_hint']}）"
        )
    lines.extend(
        [
            "",
            "## 技术附录：暴露服务",
            "",
            "| 域名 | IP | 端口 | 协议 | 服务 | 标题 |",
            "| --- | --- | ---: | --- | --- | --- |",
        ]
    )
    for service in services:
        lines.append(
            "| {domain} | {ip} | {port} | {protocol} | {service} | {title} |".format(
                domain=_md_cell(service.get("domain")),
                ip=_md_cell(service.get("ip")),
                port=service.get("port", ""),
                protocol=_md_cell(service.get("protocol")),
                service=_md_cell(service.get("service")),
                title=_md_cell(service.get("title")),
            )
        )
    return "\n".join(lines) + "\n"


def render_html_report(payload: dict[str, Any]) -> str:
    markdown = render_markdown_report(payload)
    lines = [
        "<!doctype html>",
        '<html lang="zh-CN">',
        "<head>",
        '<meta charset="utf-8">',
        "<title>互联网暴露面管理者报告</title>",
        "<style>body{font-family:Arial,sans-serif;line-height:1.6;margin:40px;}"
        "table{border-collapse:collapse;width:100%;}th,td{border:1px solid #ddd;padding:6px;}"
        "code{background:#f5f5f5;padding:2px 4px;}</style>",
        "</head>",
        "<body>",
    ]
    in_table = False
    for line in markdown.splitlines():
        if line.startswith("# "):
            lines.append(f"<h1>{escape(line[2:])}</h1>")
        elif line.startswith("## "):
            if in_table:
                lines.append("</tbody></table>")
                in_table = False
            lines.append(f"<h2>{escape(line[3:])}</h2>")
        elif line.startswith("| ") and " --- " not in line:
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if not in_table:
                lines.append("<table><tbody>")
                in_table = True
            tag = "th" if cells and cells[0] == "域名" else "td"
            lines.append("<tr>" + "".join(f"<{tag}>{escape(cell)}</{tag}>" for cell in cells) + "</tr>")
        elif line.startswith("| "):
            continue
        elif line.startswith("- "):
            lines.append(f"<p>{escape(line)}</p>")
        elif line:
            lines.append(f"<p>{escape(line)}</p>")
    if in_table:
        lines.append("</tbody></table>")
    lines.extend(["</body>", "</html>"])
    return "\n".join(lines) + "\n"


def _section(report: dict[str, Any], title: str) -> dict[str, Any]:
    for section in report.get("sections", []):
        if section.get("title") == title:
            return section
    return {"items": []}


def _md_cell(value: Any) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ")
