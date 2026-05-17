from __future__ import annotations

import hashlib

from .models import ExposedService, RiskHint


REMOTE_ACCESS_PORTS = {22, 3389, 5900, 8443}
DATABASE_PORTS = {3306, 5432, 1433, 1521, 6379, 27017, 9200}
MIDDLEWARE_PORTS = {8080, 8161, 9000, 9090}


def _risk_id(task_id: str, service_id: str, category: str) -> str:
    digest = hashlib.sha1(f"{task_id}|{service_id}|{category}".encode("utf-8")).hexdigest()[:12]
    return f"risk_{digest}"


def generate_risk_hints(task_id: str, services: list[ExposedService]) -> list[RiskHint]:
    hints: list[RiskHint] = []
    for service in services:
        text = " ".join(
            value.lower()
            for value in [service.service, service.title, service.product, service.domain, service.url]
            if value
        )
        categories = _categories_for_service(service, text)
        for category, severity, title, summary, action in categories:
            hints.append(
                RiskHint(
                    risk_hint_id=_risk_id(task_id, service.service_id, category),
                    task_id=task_id,
                    asset_id=service.asset_id,
                    service_id=service.service_id,
                    category=category,
                    severity=severity,
                    title=title,
                    manager_summary=summary,
                    technical_evidence=[
                        f"target: {service.domain or service.ip}",
                        f"port: {service.port}",
                        f"service: {service.service}",
                    ],
                    recommended_action=action,
                    confidence=0.78,
                    verification_required=True,
                )
            )
    return hints


def _categories_for_service(service: ExposedService, text: str) -> list[tuple[str, str, str, str, str]]:
    categories: list[tuple[str, str, str, str, str]] = []
    if service.port in REMOTE_ACCESS_PORTS or any(keyword in text for keyword in ["vpn", "rdp", "ssh", "remote"]):
        categories.append(
            (
                "remote_access",
                "high",
                "发现疑似互联网暴露的远程访问入口",
                "该入口可能允许员工或管理员从互联网访问内部系统，建议优先复核访问控制。",
                "在安全工具箱中创建本地验证任务，确认访问控制、MFA 和补丁状态。",
            )
        )
    if any(keyword in text for keyword in ["admin", "manage", "console", "后台", "管理"]):
        categories.append(
            (
                "admin_portal",
                "high",
                "发现疑似互联网暴露的管理后台",
                "管理后台暴露会增加未授权访问风险，建议确认是否必须公网访问。",
                "复核后台来源限制、认证策略和公网暴露必要性。",
            )
        )
    if any(keyword in text for keyword in ["test", "dev", "staging", "uat"]):
        categories.append(
            (
                "test_environment",
                "medium",
                "发现疑似测试环境暴露在互联网",
                "测试环境通常缺少正式安全加固，建议确认是否应对公网开放。",
                "确认环境用途，优先下线不必要暴露或增加访问控制。",
            )
        )
    if service.port in DATABASE_PORTS:
        categories.append(
            (
                "database_exposure",
                "high",
                "发现疑似数据库或检索服务暴露",
                "数据库和检索服务公网暴露可能导致数据泄露，建议立即复核。",
                "确认服务归属、网络访问控制和认证配置。",
            )
        )
    if service.port in MIDDLEWARE_PORTS or any(keyword in text for keyword in ["jenkins", "tomcat", "weblogic"]):
        categories.append(
            (
                "middleware_exposure",
                "medium",
                "发现疑似中间件或运维服务暴露",
                "中间件和运维服务暴露可能扩大攻击面，建议确认版本和访问控制。",
                "创建本地巡检任务，检查版本、补丁和认证策略。",
            )
        )
    return categories
