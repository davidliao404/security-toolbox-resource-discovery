# 安全工具箱资产探测 API 契约

## 1. 目标

本文定义安全工具箱调用资源发现网关的第一版 API 契约。网关负责根据后台安全人员配置的租户授权范围，调用 FOFA/uncover 等外部测绘能力，返回短期资产探测任务结果。

安全工具箱负责：

- 发起资产探测任务。
- 轮询任务状态。
- 拉取资产、服务和来源证据。
- 将需要长期保留的资产结果写入工具箱本地资产库。
- 发起本地验证、巡检和处置。

资源发现网关负责：

- 校验租户、客户端和请求签名。
- 校验客户请求范围不超过后台授权范围。
- 创建异步资产探测任务。
- 调用 uncover/FOFA。
- 归一化、去重、标注 freshness。
- 短期保存任务状态、结果和审计。

## 2. 通用约定

### 2.1 路径前缀

```text
/api/v1/discovery
```

### 2.2 认证字段

生产环境请求必须包含：

- `X-Tenant-Id`
- `X-Client-Id`
- `X-Timestamp`
- `X-Nonce`
- `X-Signature`

POC handler 暂不实现签名校验，但 API 契约按生产要求保留这些字段。

### 2.2.1 签名算法

第一版建议使用 HMAC-SHA256。签名原文为：

```text
METHOD
PATH
X-Timestamp
X-Nonce
SHA256(request_body)
```

示例：

```text
POST
/api/v1/discovery/tasks
2026-05-20T12:00:00+00:00
nonce-001
4f8f...
```

约定：

- `METHOD` 使用大写。
- `PATH` 不包含域名。
- `request_body` 使用实际发送的 UTF-8 字节；`GET` 请求 body 为空字节。
- `X-Signature` 为 HMAC-SHA256 十六进制字符串。
- 网关默认时间窗建议 5 分钟。
- `X-Nonce` 在时间窗内只能使用一次，重复使用视为重放请求。
- 签名失败、时间窗失败、nonce 重放均不得返回签名计算细节。

### 2.3 状态枚举

任务状态：

- `queued`：任务已创建，等待执行。
- `running`：任务正在执行。
- `success`：任务成功完成。
- `partial_success`：至少一个查询成功，但存在供应商或查询失败。
- `failed`：任务失败，没有可用结果。
- `cancelled`：任务被取消。

请求级状态：

- `rejected`：请求未创建任务，通常因为范围越权、profile 不匹配或参数错误。

### 2.4 错误对象

错误统一为：

```json
{
  "code": "scope_out_of_bounds",
  "message": "Requested scope is outside the tenant authorized scope.",
  "recoverable": false,
  "details": {}
}
```

首批错误码：

| code | 含义 | recoverable |
| --- | --- | --- |
| `profile_id_mismatch` | 请求 profile 与租户当前 profile 不一致 | false |
| `scope_out_of_bounds` | 请求范围超过后台授权范围 | false |
| `engine_not_allowed` | 请求的测绘引擎未授权 | false |
| `result_limit_exceeded` | 请求结果上限超过租户配置 | false |
| `provider_auth_failed` | 外部供应商认证失败 | true |
| `provider_rate_limited` | 外部供应商限速 | true |
| `provider_timeout` | 外部供应商超时 | true |
| `provider_bad_response` | 外部供应商返回无法解析 | true |
| `normalization_failed` | 结果归一化失败 | true |
| `internal_error` | 网关内部错误 | true |

### 2.5 分页

分页字段：

```json
{
  "page": {
    "next_cursor": "100",
    "limit": 100,
    "type": "assets"
  }
}
```

约定：

- `cursor` 第一版使用字符串形式的偏移量。
- `limit` 默认 100。
- `limit` 应受网关上限保护。
- `type` 表示当前分页的数据类型，首批取值为 `assets`、`services`、`source_evidence`。
- 重复请求同一个 cursor 应返回稳定结果。

## 3. 查询租户授权范围

```http
GET /api/v1/discovery/scope-profile
```

用途：工具箱调用页渲染可选范围。工具箱页面不在本项目范围，但可依赖该接口展示客户可缩小的探测范围。

响应：

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

说明：

- `default_scope` 由安全人员在网关后台配置。
- 工具箱可不填缩小范围，此时使用 `default_scope`。
- 返回内容不包含外部供应商 API Key。

## 4. 创建资产探测任务

```http
POST /api/v1/discovery/tasks
```

请求：

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
  "result_limit": 100,
  "purpose": "toolbox_asset_discovery"
}
```

异步主路径响应：

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

约束：

- 工具箱不能提交 FOFA 原生查询语句。
- `requested_scope` 只能缩小 `TenantScopeProfile`。
- `result_limit` 不能超过 profile 中的 `max_results_per_task`。
- 第一版只允许 `engines=["fofa"]`。

## 5. 查询任务状态

```http
GET /api/v1/discovery/tasks/{task_id}
```

响应：

```json
{
  "task_id": "dt_20260520_000001",
  "tenant_id": "tenant_001",
  "status": "success",
  "created_at": "2026-05-20T10:00:00+08:00",
  "started_at": "2026-05-20T10:00:03+08:00",
  "finished_at": "2026-05-20T10:00:18+08:00",
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

工具箱建议：

- `queued` 或 `running` 时继续轮询。
- `success` 或 `partial_success` 时拉取结果。
- `failed` 时展示错误并允许用户重试。
- `cancelled` 时停止轮询。

## 6. 拉取任务结果

```http
GET /api/v1/discovery/tasks/{task_id}/results?result_type=assets&cursor=&limit=100
```

`result_type` 取值：

| result_type | 返回数组 |
| --- | --- |
| `assets` | `assets` |
| `services` | `services` |
| `source_evidence` | `source_evidence` |

响应：

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
  "services": [
    {
      "service_id": "svc_001",
      "asset_id": "asset_001",
      "ip": "203.0.113.10",
      "domain": "vpn.example.com",
      "port": 443,
      "protocol": "https",
      "service": "vpn",
      "title": "VPN Portal",
      "product": "ExampleVPN",
      "freshness": {
        "status": "fresh",
        "last_observed_at": "2026-05-19T12:00:00+00:00",
        "age_days": 0,
        "stale_after_days": 180,
        "meaning": "provider_observation_time_not_liveness_proof"
      },
      "sources": ["fofa"],
      "evidence_ids": ["ev_001"]
    }
  ],
  "source_evidence": [
    {
      "evidence_id": "ev_001",
      "source": "fofa",
      "source_query": "domain=\"example.com\"",
      "raw_reference": "fofa:fixture:plan_001:1",
      "first_seen": "2026-05-19T12:00:00+00:00",
      "last_seen": "2026-05-19T12:00:00+00:00",
      "confidence": 0.7,
      "normalized_fields": ["ip", "host", "port"],
      "evidence": {
        "ip": "203.0.113.10",
        "domain": "vpn.example.com",
        "port": 443,
        "freshness": {
          "status": "fresh",
          "meaning": "provider_observation_time_not_liveness_proof"
        }
      }
    }
  ],
  "page": {
    "next_cursor": null,
    "limit": 100,
    "type": "assets"
  }
}
```

说明：

- 第一版结果主路径不返回 `report`。
- `risk_hints`、`remediation`、`report` 可作为后续或兼容接口保留。
- 工具箱应将需要长期保留的 `assets` 和 `services` 写入本地。
- `source_evidence` 可按客户策略短期或长期保留。

## 7. freshness 语义

`freshness` 只表示外部测绘平台的观测或更新时间。

| status | 含义 |
| --- | --- |
| `fresh` | 90 天内被供应商更新或观测 |
| `aging` | 90 至 180 天 |
| `stale` | 超过 180 天 |
| `unknown` | 来源没有返回更新时间 |

重要约束：

- `stale` 不代表资产已下线。
- 网关不做云端主动探活。
- 工具箱可基于 `stale` 发起本地验证任务。
- 报告或 UI 不应写“资产已关停”，只能写“测绘情报陈旧，需复核”。

## 8. 工具箱建议长期保存字段

建议工具箱长期保存：

- `task_id`
- `asset_id`
- `asset_type`
- `domain`
- `ip`
- `root_domain`
- `service_id`
- `port`
- `protocol`
- `service`
- `title`
- `product`
- `freshness`
- `sources`
- 结果导入时间
- 本地验证状态
- 本地处置状态

建议工具箱谨慎保存或短期保存：

- `source_query`
- `raw_reference`
- `source_evidence.evidence`

不应由工具箱保存：

- FOFA/uncover API Key。
- 网关 provider config。
- 网关后台授权配置原文，除非有单独权限设计。

## 9. 轮询建议

工具箱推荐轮询策略：

- 前 30 秒：每 3 秒轮询一次。
- 30 秒后：每 10 秒轮询一次。
- 超过 5 分钟：提示后台继续执行，可稍后刷新。
- 任务进入终态后停止轮询。

终态：

- `success`
- `partial_success`
- `failed`
- `cancelled`

## 10. 当前 POC 与生产差异

当前 POC：

- 使用 Python handler 模拟 API。
- 使用文件存储。
- 支持 fixture 和 live FOFA 验证。
- `create_task` 已采用 queued 模式，结果由轻量 worker 写入。
- 已拆分任务 repository 和结果 repository。
- 已支持按 `assets`、`services`、`source_evidence` 分页拉取结果。
- 已增加网关审计、TTL 策略和 live 验证脚本。

下一阶段：

- 接入真实 HTTP API 框架。
- 接入可靠队列和生产数据库。
- 实现签名鉴权、nonce 防重放和租户级配额。
- 将 FOFA/uncover 错误映射接入 worker 重试策略。
