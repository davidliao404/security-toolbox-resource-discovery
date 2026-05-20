# 互联网暴露面资源发现模块数据模型设计

## 1. 设计目标

数据模型用于统一外部 SaaS 返回结果，使“安全工具箱”可以稳定展示管理者报告、技术附录和本地处置任务。

设计原则：

- 归一化字段服务产品和报告。
- 来源字段服务审计和证据链。
- 置信度字段服务误报控制。
- 原始响应最小化保存。
- 模型保持可扩展，支持后续多供应商。

## 2. 发现任务模型 `DiscoveryTask`

```json
{
  "task_id": "dt_20260517_000001",
  "tenant_id": "tenant_001",
  "operator_id": "user_001",
  "region": "hk",
  "status": "running",
  "purpose": "quarterly_exposure_review",
  "language": "zh-CN",
  "created_at": "2026-05-17T10:00:00+08:00",
  "started_at": "2026-05-17T10:01:00+08:00",
  "finished_at": null,
  "quota_estimate": {
    "source": "fofa",
    "estimated_queries": 3,
    "estimated_pages": 10
  },
  "summary": {
    "seed_count": 3,
    "asset_count": 0,
    "service_count": 0,
    "risk_hint_count": 0
  }
}
```

字段说明：

| 字段 | 说明 |
| --- | --- |
| `task_id` | 发现任务唯一标识 |
| `tenant_id` | 租户标识 |
| `operator_id` | 操作者标识 |
| `region` | 任务执行区域，取值 `hk` 或 `cn` |
| `status` | 任务状态 |
| `purpose` | 任务目的 |
| `language` | 报告语言 |
| `quota_estimate` | 配额消耗预估 |
| `summary` | 任务结果摘要 |

## 3. 查询输入模型 `DiscoverySeed`

```json
{
  "seed_id": "seed_001",
  "type": "root_domain",
  "value": "example.org",
  "label": "Main public website domain",
  "authorization_note": "Customer-provided domain for exposure review"
}
```

支持类型：

| 类型 | 示例 | 说明 |
| --- | --- | --- |
| `root_domain` | `example.org` | 根域名 |
| `organization_name` | `Example Charity Limited` | 组织名称 |
| `ip_cidr` | `203.0.113.0/24` | IP 段 |
| `email_domain` | `example.org` | 邮箱域 |

MVP 必做：`root_domain`、`organization_name`、`ip_cidr`。

## 4. 查询计划模型 `SourceQueryPlan`

```json
{
  "plan_id": "plan_001",
  "task_id": "dt_20260517_000001",
  "source": "fofa",
  "seed_id": "seed_001",
  "source_query": "domain=\"example.org\"",
  "query_type": "domain",
  "page_limit": 10,
  "result_limit": 1000,
  "created_at": "2026-05-17T10:01:00+08:00"
}
```

要求：

- `source_query` 必须可审计。
- 用户原始输入和供应商查询语法必须分开保存。
- 查询计划不得包含 SaaS 密钥。

## 5. 资产模型 `DiscoveredAsset`

```json
{
  "asset_id": "asset_001",
  "task_id": "dt_20260517_000001",
  "asset_type": "domain",
  "domain": "vpn.example.org",
  "ip": "203.0.113.10",
  "root_domain": "example.org",
  "asn": "AS64500",
  "country_or_region": "HK",
  "ownership_confidence": 0.82,
  "first_seen": "2026-05-17T10:03:00+08:00",
  "last_seen": "2026-05-17T10:03:00+08:00",
  "sources": ["fofa"]
}
```

资产类型：

- `domain`
- `ip`
- `url`
- `certificate_subject`

置信度建议：

| 分数 | 含义 |
| --- | --- |
| `0.90 - 1.00` | 高置信，域名或 IP 与输入种子直接匹配 |
| `0.70 - 0.89` | 中高置信，证书、标题或组织名强相关 |
| `0.40 - 0.69` | 中低置信，需要人工确认 |
| `< 0.40` | 默认不进入管理者摘要，只进入待复核列表 |

## 6. 暴露服务模型 `ExposedService`

```json
{
  "service_id": "svc_001",
  "asset_id": "asset_001",
  "task_id": "dt_20260517_000001",
  "ip": "203.0.113.10",
  "domain": "vpn.example.org",
  "port": 443,
  "protocol": "https",
  "service": "vpn",
  "title": "Example VPN Portal",
  "product": "ExampleVPN",
  "version": "unknown",
  "url": "https://vpn.example.org/",
  "banner_hash": "hash_001",
  "tls": {
    "enabled": true,
    "certificate_fingerprint": "sha256:example",
    "subject": "CN=vpn.example.org",
    "issuer": "Example CA",
    "not_after": "2026-12-31T23:59:59+08:00"
  },
  "first_seen": "2026-05-17T10:03:00+08:00",
  "last_seen": "2026-05-17T10:03:00+08:00"
}
```

## 7. 风险线索模型 `RiskHint`

```json
{
  "risk_hint_id": "risk_001",
  "task_id": "dt_20260517_000001",
  "asset_id": "asset_001",
  "service_id": "svc_001",
  "category": "remote_access",
  "severity": "high",
  "title": "发现疑似互联网暴露的远程访问入口",
  "manager_summary": "该入口可能允许员工或管理员从互联网访问内部系统，建议优先确认是否必要暴露。",
  "technical_evidence": [
    "domain: vpn.example.org",
    "port: 443",
    "title contains: VPN"
  ],
  "recommended_action": "在安全工具箱中创建本地验证任务，确认访问控制、MFA 和补丁状态。",
  "confidence": 0.78,
  "verification_required": true
}
```

风险类别：

- `remote_access`
- `admin_portal`
- `test_environment`
- `database_exposure`
- `middleware_exposure`
- `outdated_component`
- `unknown_high_value_service`

严重级别：

- `critical`
- `high`
- `medium`
- `low`
- `info`

MVP 默认不输出 `critical` 漏洞结论，除非只是表达“需紧急复核的暴露线索”。

## 8. 分析配置模型 `TenantAnalysisConfig`

```json
{
  "tenant_id": "tenant_001",
  "llm_enabled": false,
  "llm_provider": null,
  "llm_model": null,
  "web_search_enabled": false,
  "data_sharing_level": "none",
  "authorization_id": null,
  "authorized_at": null,
  "authorized_by": null,
  "revoked_at": null
}
```

字段说明：

| 字段 | 说明 |
| --- | --- |
| `tenant_id` | 配置所属租户，必须与任务租户一致 |
| `llm_enabled` | 是否允许大模型增强分析，默认关闭 |
| `llm_provider` | 大模型供应商，启用时必填 |
| `llm_model` | 大模型名称，启用时必填 |
| `web_search_enabled` | 是否允许模型侧网络搜索，必须单独配置 |
| `data_sharing_level` | 数据共享范围，当前取值 `none` 或 `minimal` |
| `authorization_id` | 客户授权记录 ID，启用时必填 |
| `authorized_at` | 客户授权时间，启用时必填 |
| `authorized_by` | 授权人脱敏摘要，启用时必填 |
| `revoked_at` | 撤销时间；存在时不得继续调用大模型 |

约束：

- `llm_enabled=false` 时强制 `rules_only`，并忽略模型供应商、模型名称、网络搜索和共享范围。
- `llm_enabled=true` 时必须使用 `data_sharing_level=minimal`。
- `llm_enabled=true` 时必须存在未撤销的授权记录。
- 配置不得包含模型 API Key；密钥必须走独立密钥管理。

## 9. 分析结果模型 `AnalysisMetadata`

```json
{
  "analysis_mode": "rules_only",
  "llm_enabled": false,
  "web_search_enabled": false,
  "data_sharing_level": "none",
  "provider": null,
  "model": null,
  "authorization_id": null
}
```

用途：

- 在报告中标识分析来源。
- 在审计日志中记录是否使用大模型增强。
- 帮助售前和客户解释结论来自规则还是可选外部上下文。

## 10. 报告模型 `ExposureReport`

```json
{
  "report_id": "report_001",
  "task_id": "dt_20260517_000001",
  "tenant_id": "tenant_001",
  "report_type": "manager_summary",
  "generated_at": "2026-05-17T10:10:00+08:00",
  "executive_summary": {
    "asset_count": 25,
    "service_count": 60,
    "high_risk_hint_count": 5,
    "new_asset_count": 25,
    "summary_text": "本次被动发现识别到 25 个疑似互联网暴露资产，其中 5 项建议优先复核。"
  },
  "sections": [
    {
      "title": "优先处置建议",
      "items": ["确认 VPN 入口访问控制", "复核疑似测试环境是否需要公网暴露"]
    }
  ],
  "appendix_refs": ["asset_list", "service_list", "source_evidence"]
}
```

## 11. SaaS 来源追踪模型 `SourceEvidence`

```json
{
  "evidence_id": "ev_001",
  "task_id": "dt_20260517_000001",
  "source": "fofa",
  "source_query": "domain=\"example.org\"",
  "raw_reference": "fofa:result:page=1:index=3",
  "first_seen": "2026-05-17T10:03:00+08:00",
  "last_seen": "2026-05-17T10:03:00+08:00",
  "confidence": 0.82,
  "evidence": {
    "ip": "203.0.113.10",
    "domain": "vpn.example.org",
    "port": 443,
    "title": "Example VPN Portal"
  },
  "normalized_fields": ["ip", "domain", "port", "protocol", "title", "product"]
}
```

必须保留字段：

- `source`
- `source_query`
- `raw_reference`
- `first_seen`
- `last_seen`
- `confidence`
- `evidence`
- `normalized_fields`

## 12. 去重键设计

主去重键：

```text
domain_or_ip + port + protocol + service
```

示例：

```text
vpn.example.org|443|https|vpn
203.0.113.10|22|ssh|openssh
```

辅助去重：

- `certificate_fingerprint`
- `banner_hash`
- `url`
- `ip + port`
- `domain + title`

去重规则：

- 同一主键的服务合并为一条暴露服务。
- 多个来源证据全部保留。
- 置信度取加权结果，不简单取最高值。
- 冲突字段保留来源标记。

## 13. 快照与留存

短期快照包含：

- 任务元数据。
- 脱敏输入摘要。
- 归一化资产。
- 风险线索。
- 报告结构。
- 来源证据摘要。

短期快照不应包含：

- SaaS 密钥。
- 完整未脱敏原始响应。
- 与任务无关的个人信息。
- 超出授权范围的查询目标。

具体保留时长在执行阶段由产品和合规策略配置，文档默认建议 30 至 90 天。
