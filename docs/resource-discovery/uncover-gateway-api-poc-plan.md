# Uncover + FOFA 网关 API POC 计划

## 1. 目标调整

资源发现网关的第一目标从“输出管理者报告”调整为“向安全工具箱提供资产探测任务 API”。管理者报告、风险线索和整改建议功能保留，但不作为工具箱调用主路径。

主链路：

```text
安全工具箱
-> 创建资产探测任务 API
-> 网关校验租户授权范围
-> 网关调用 uncover/FOFA
-> 网关归一化、去重、保存任务快照
-> 安全工具箱查询任务状态和结果
```

## 2. POC 范围

本阶段只关注 FOFA。

- 使用 uncover 作为优先评估的外部执行器。
- 保留原生 FOFA client 作为 fallback。
- 不引入真实 HTTP 框架，先实现 API handler 函数。
- 不提交 API Key。
- 真实 API 验证只使用已授权目标，并将真实快照保存到被 Git 忽略的 `artifacts/`。

## 3. 后台配置与范围约束

安全人员采访客户后，在网关后台录入 `TenantScopeProfile`。客户在安全工具箱中只能提交该配置范围内的缩小范围。

示例：

```json
{
  "tenant_id": "tenant_001",
  "profile_id": "scope_profile_001",
  "status": "active",
  "allowed_root_domains": ["example.com"],
  "allowed_domains": ["www.example.com", "vpn.example.com"],
  "allowed_ip_cidrs": ["203.0.113.0/24"],
  "allowed_org_names": ["Example Limited"],
  "default_scope": {
    "root_domains": ["example.com"]
  },
  "allowed_engines": ["fofa"],
  "provider_profile_id": "provider_fofa_hk_001",
  "limits": {
    "max_results_per_task": 200,
    "max_queries_per_task": 10
  },
  "created_by": "security_operator_hash",
  "authorization_note": "Customer interview confirmed ownership."
}
```

约束：

- 客户不能提交任意 FOFA 原生查询语句。
- 客户请求范围不得超过后台配置。
- 客户不填缩小范围时，使用后台 `default_scope`。
- `default_scope` 必须由安全人员明确配置。
- 超范围输入会进入 `rejected_scope`，任务不应静默扩大。

## 4. API 契约

### 4.1 查询范围配置

```http
GET /api/v1/discovery/scope-profile
```

返回：

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

### 4.2 创建资产探测任务

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
    "ip_cidrs": ["203.0.113.16/28"]
  },
  "engines": ["fofa"],
  "result_limit": 100,
  "purpose": "toolbox_asset_discovery"
}
```

响应：

```json
{
  "task_id": "dt_20260520_000001",
  "status": "success",
  "accepted_scope": {},
  "rejected_scope": [],
  "query_plan_summary": {
    "engines": ["fofa"],
    "planned_queries": 3
  },
  "status_url": "/api/v1/discovery/tasks/dt_20260520_000001",
  "result_url": "/api/v1/discovery/tasks/dt_20260520_000001/results"
}
```

### 4.3 查询任务状态

```http
GET /api/v1/discovery/tasks/{task_id}
```

返回：

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

### 4.4 拉取任务结果

```http
GET /api/v1/discovery/tasks/{task_id}/results?cursor=&limit=100
```

返回：

```json
{
  "task_id": "dt_20260520_000001",
  "assets": [],
  "services": [],
  "source_evidence": [],
  "page": {
    "next_cursor": null
  }
}
```

## 5. uncover 集成方式

POC 阶段优先实现 `UncoverSourceClient`：

```text
SourceQueryPlan
-> uncover -ff "<fofa_query>" -e fofa -j -silent -l <limit> -provider <config>
-> JSONL parser
-> normalized provider rows
```

uncover 支持：

- `-ff` FOFA 查询。
- `-e fofa` 指定 FOFA 引擎。
- `-j` JSONL 输出。
- `-l` 结果限制。
- `-provider` 指定 provider config。

参考：

- ProjectDiscovery uncover: https://github.com/projectdiscovery/uncover
- FOFA 中转站接口说明：`full=false` 默认搜索一年内数据，`lastupdatetime` 表示 FOFA 最后更新时间。

## 6. 情报时间与 freshness

FOFA 可返回 `lastupdatetime` 字段，该字段表示 FOFA 最后更新时间，不等同于资产当前在线证明。FOFA 默认搜索一年内数据，`full=true` 才搜索全部历史数据。

网关处理原则：

- 将 `lastupdatetime` 归一化为 `last_seen` 或 `last_updated_at`。
- 增加 `freshness` 标注：
  - `fresh`：90 天内。
  - `aging`：90 至 180 天。
  - `stale`：超过 180 天。
  - `unknown`：来源未返回时间。
- `stale` 不代表资产已下线，只表示情报陈旧，需要本地安全工具箱复核。
- 网关不做云端主动探活。

## 7. 验证标准

必须验证：

- 后台授权范围能约束客户请求范围。
- 超范围请求被拒绝并返回明确原因。
- uncover fixture JSONL 能被解析并归一化。
- API handler 能创建任务、查询状态、返回结果。
- 结果中包含 freshness。
- 原生 FOFA fallback 仍可运行。
- 完整 pytest 通过。
