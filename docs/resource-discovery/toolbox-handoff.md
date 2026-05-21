# 安全工具箱对接交接说明

## 1. 交接目标

本文面向安全工具箱开发团队，说明如何对接资源发现网关的第一版资产探测 API。

当前网关目标不是替代安全工具箱做扫描或验证，而是提供受授权范围约束的互联网资产发现任务：

```text
安全工具箱
-> 获取租户授权范围
-> 创建异步资产探测任务
-> 轮询任务状态
-> 分页拉取资产、服务、来源证据
-> 在工具箱本地保存需要长期使用的结果
-> 发起本地验证、巡检和处置
```

工具箱调用页、资产库、巡检任务和处置工作流由工具箱团队实现；本网关只提供 API 契约和短期结果缓存。

## 2. API 总览

路径前缀：

```text
/api/v1/discovery
```

首批接口：

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `GET` | `/scope-profile` | 获取租户可探测范围、默认范围和限额 |
| `POST` | `/tasks` | 创建异步资产探测任务 |
| `GET` | `/tasks/{task_id}` | 查询任务状态 |
| `GET` | `/tasks/{task_id}/results` | 按类型分页拉取任务结果 |

生产环境请求必须带签名鉴权字段：

- `X-Tenant-Id`
- `X-Client-Id`
- `X-Timestamp`
- `X-Nonce`
- `X-Signature`

PoC handler 暂未实现完整 HTTP 鉴权，但工具箱侧应按生产契约预留这些字段。

## 3. 查询授权范围

工具箱页面在创建任务前应先请求：

```http
GET /api/v1/discovery/scope-profile
```

响应示例：

```json
{
  "tenant_id": "tenant_001",
  "profile_id": "scope_profile_001",
  "allowed_scope_summary": {
    "root_domains": ["example.com"],
    "domains": ["vpn.example.com"],
    "ip_cidrs": ["203.0.113.0/24"],
    "org_names": ["Example Limited"]
  },
  "default_scope": {
    "root_domains": ["example.com"]
  },
  "allowed_engines": ["fofa"],
  "limits": {
    "max_results_per_task": 200,
    "max_queries_per_task": 10
  }
}
```

工具箱页面可以允许用户缩小范围，例如只查某个子域名或较小 IP 段；但不能允许用户输入任意 FOFA 查询语句，也不能绕过 `allowed_scope_summary`。

## 4. 创建任务

请求：

```http
POST /api/v1/discovery/tasks
```

```json
{
  "profile_id": "scope_profile_001",
  "requested_scope": {
    "root_domains": ["example.com"],
    "domains": ["vpn.example.com"],
    "ip_cidrs": ["203.0.113.16/28"],
    "org_names": []
  },
  "engines": ["fofa"],
  "discovery_strategy": "baseline",
  "result_limit": 100,
  "purpose": "toolbox_asset_discovery"
}
```

成功响应：

```json
{
  "task_id": "dt_20260520_000001",
  "status": "queued",
  "accepted_scope": {
    "root_domains": ["example.com"],
    "domains": ["vpn.example.com"],
    "ip_cidrs": ["203.0.113.16/28"]
  },
  "rejected_scope": [],
  "query_plan_summary": {
    "engines": ["fofa"],
    "strategy": "baseline",
    "planned_queries": 3
  },
  "status_url": "/api/v1/discovery/tasks/dt_20260520_000001",
  "result_url": "/api/v1/discovery/tasks/dt_20260520_000001/results"
}
```

范围越权响应：

```json
{
  "status": "rejected",
  "accepted_scope": {},
  "rejected_scope": [
    {
      "type": "root_domain",
      "value": "other.com",
      "reason": "outside_tenant_allowed_scope"
    }
  ],
  "errors": [
    {
      "code": "scope_out_of_bounds",
      "message": "Requested scope is outside the tenant authorized scope.",
      "recoverable": false,
      "details": {
        "profile_id": "scope_profile_001"
      }
    }
  ]
}
```

工具箱处理建议：

- `queued`：进入轮询状态。
- `rejected`：不要重试同一请求，提示用户缩小范围或联系安全服务人员更新后台授权配置。
- 不要在客户端侧拼接供应商查询语句；只提交结构化范围。
- 默认使用 `discovery_strategy="baseline"`，适合普通联调和低配额客户。
- 需要更完整的被动互联网资产发现时，可使用 `discovery_strategy="easm"`；该策略仍只做被动发现，但会生成更多 FOFA 查询计划，可能因为租户 `max_queries_per_task` 不足被拒绝。
- 如果返回 `invalid_discovery_strategy`，工具箱应回退到 `baseline` 或刷新服务端配置；如果返回 `query_plan_budget_exceeded`，工具箱应提示用户缩小范围或使用 `baseline`。

## 5. 轮询任务状态

请求：

```http
GET /api/v1/discovery/tasks/{task_id}
```

响应示例：

```json
{
  "task_id": "dt_20260520_000001",
  "tenant_id": "tenant_001",
  "status": "success",
  "engine_status": [
    {
      "engine": "fofa",
      "status": "success",
      "result_count": 58
    }
  ],
  "errors": []
}
```

状态处理：

| status | 工具箱动作 |
| --- | --- |
| `queued` | 继续轮询 |
| `running` | 继续轮询 |
| `success` | 拉取结果 |
| `partial_success` | 拉取已有结果，同时展示失败来源 |
| `failed` | 展示错误，允许重新创建任务 |
| `cancelled` | 停止轮询 |

推荐轮询节奏：

- 前 30 秒：每 3 秒一次。
- 30 秒后：每 10 秒一次。
- 超过 5 分钟：提示任务仍在后台执行，允许稍后刷新。
- 进入终态后停止轮询。

## 6. 拉取结果与分页

请求：

```http
GET /api/v1/discovery/tasks/{task_id}/results?result_type=assets&cursor=&limit=100
```

`result_type` 取值：

| result_type | 返回数组 |
| --- | --- |
| `assets` | `assets` |
| `services` | `services` |
| `source_evidence` | `source_evidence` |

第一版为了避免单次响应过大，建议工具箱按类型分别拉取：

1. 拉取 `assets`，写入本地资产表。
2. 拉取 `services`，关联资产并写入暴露服务表。
3. 按需拉取 `source_evidence`，用于证据链、问题复核和售后排查。

响应示例：

```json
{
  "task_id": "dt_20260520_000001",
  "assets": [
    {
      "asset_id": "asset_001",
      "asset_type": "domain",
      "domain": "vpn.example.com",
      "ip": "203.0.113.10",
      "root_domain": "example.com",
      "ownership_confidence": 0.86,
      "first_seen": "2026-05-17T10:03:00+08:00",
      "last_seen": "2026-05-19T12:00:00+00:00",
      "sources": ["fofa"],
      "evidence_ids": ["ev_001"]
    }
  ],
  "services": [],
  "source_evidence": [],
  "page": {
    "next_cursor": "100",
    "limit": 100,
    "type": "assets"
  }
}
```

分页约定：

- `cursor` 第一版是字符串偏移量。
- `next_cursor=null` 表示当前类型已拉完。
- `limit` 默认 100，工具箱不应假设可以无限放大。
- 同一任务完成后，同一个 cursor 应返回稳定结果。

## 7. freshness 解释

`freshness` 表示外部测绘平台返回的观测或更新时间，不表示当前资产一定在线。

| status | 解释 | 工具箱建议 |
| --- | --- | --- |
| `fresh` | 90 天内有供应商观测或更新 | 可优先进入本地验证 |
| `aging` | 90 至 180 天 | 可作为普通待复核线索 |
| `stale` | 超过 180 天 | 标记为陈旧情报，仍可本地验证 |
| `unknown` | 来源没有更新时间 | 保留证据并降低置信度 |

界面文案不要写“资产已关停”或“漏洞已确认”。推荐写法：

- “该线索来自外部测绘数据，最近观测时间较早，建议在本地验证是否仍暴露。”
- “该服务疑似暴露在互联网，需结合安全工具箱巡检确认访问控制。”

## 8. 错误码表

| code | 含义 | 是否建议自动重试 |
| --- | --- | --- |
| `profile_id_mismatch` | 工具箱使用了过期或错误的授权范围配置 | 否，重新获取 scope profile |
| `scope_out_of_bounds` | 请求范围超过后台授权范围 | 否，提示缩小范围 |
| `engine_not_allowed` | 请求的测绘引擎未授权 | 否，刷新配置或联系服务人员 |
| `result_limit_exceeded` | 请求结果上限超过租户配置 | 否，降低上限 |
| `invalid_discovery_strategy` | 请求的发现策略不受支持 | 否，回退到 `baseline` 或刷新配置 |
| `query_plan_budget_exceeded` | 发现策略展开后的查询数超过租户上限 | 否，缩小范围或使用 `baseline` |
| `provider_auth_failed` | 外部供应商认证失败 | 否，交由网关管理员处理 |
| `provider_rate_limited` | 外部供应商限速 | 是，延迟重试 |
| `provider_timeout` | 外部供应商超时 | 是，延迟重试 |
| `provider_bad_response` | 外部供应商返回无法解析 | 是，延迟重试并记录 |
| `normalization_failed` | 结果归一化失败 | 是，保留任务 ID 便于排查 |
| `internal_error` | 网关内部异常 | 是，延迟重试并告警 |

## 9. 工具箱建议持久化字段

建议长期保存：

- `task_id`
- `asset_id`
- `asset_type`
- `domain`
- `ip`
- `root_domain`
- `ownership_confidence`
- `first_seen`
- `last_seen`
- `service_id`
- `port`
- `protocol`
- `service`
- `title`
- `product`
- `freshness`
- `sources`
- `evidence_ids`
- 结果导入时间
- 本地验证状态
- 本地处置状态

建议短期保存或按客户策略保存：

- `source_evidence`
- `source_query`
- `raw_reference`
- `normalized_fields`
- 供应商返回的证据摘要

不应保存：

- FOFA API Key。
- uncover provider 配置。
- 网关后台授权配置原文。
- 客户访谈记录原文。
- 未脱敏操作者个人资料。

## 10. 安全注意事项

- 工具箱不接触外部 SaaS 密钥。
- 工具箱不得把用户输入透传为 FOFA 原生查询语句。
- 每次创建任务都必须带 `profile_id`，避免使用过期配置。
- 工具箱展示 `rejected_scope` 时应避免暗示用户可以绕过后台授权。
- 结果需要长期保存时，应写入工具箱本地资产库；网关只做短期缓存。
- 对 `partial_success` 不要直接判定失败，应允许用户查看已发现结果。
- 对 `stale` 线索不要直接隐藏，陈旧情报仍可能指向历史暴露或供应商未更新。

## 11. 对接验收建议

工具箱团队完成对接后，至少验证：

- 能获取 scope profile 并按配置渲染可选范围。
- 创建任务时，越权范围会被拒绝。
- 创建任务成功后，能轮询到终态。
- 能分别分页拉取 `assets`、`services`、`source_evidence`。
- 能正确展示 `partial_success` 和供应商错误。
- 能解释 freshness，不把被动发现结论写成漏洞确认。
- 能将需要长期使用的资产和服务保存到本地。
- 不在日志、浏览器存储或数据库中保存 FOFA API Key。
