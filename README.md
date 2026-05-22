# 安全工具箱互联网暴露面资源发现 PoC

这是“安全工具箱”互联网暴露面资源发现模块的第一版可执行 PoC。当前实现默认使用离线 fixture 数据，验证从资产种子到资产探测结果、风险线索和管理者报告草稿的最小链路；真实 FOFA 兼容调用必须显式开启，并且只能用于已授权目标。本项目不会执行云端主动扫描。

## 当前能力

- 根据根域名、组织名、IP 段生成受控 FOFA 查询计划。
- 从 FOFA-like fixture 数据加载资产发现结果。
- 归一化为资产、暴露服务和来源证据。
- 按 `domain_or_ip + port + protocol + service` 去重。
- 生成远程访问、管理后台、测试环境、数据库暴露和中间件暴露等被动风险线索。
- 生成管理者摘要报告和技术附录数据。
- 提供已单元测试的 FOFA API 适配器边界，用于后续真实凭据接入；默认 CLI 仍只运行离线 fixture。
- 在执行前校验授权说明、种子数量、IP 段范围和查询页数预算，避免误用真实 SaaS 能力。
- 输出任务信封，包含 `success`、`partial_success`、`failed` 等状态、错误列表、配额消耗和报告快照。
- 根据风险线索生成整改优先级，给出建议负责人和本地验证动作。
- 风险识别规则来自包内 `risk_rules.yml`，可配置端口、关键字、严重级别、处置建议和优先级。
- 支持双轨风险分析接口：默认 `rules_only` 只使用规则库；`rules_plus_llm` 作为显式注入的大模型增强扩展点，使用最小化上下文并在报告与审计中标识来源。
- 支持面向安全工具箱的网关 API handler：查询租户授权范围、创建资产探测任务、查询任务状态、拉取资产探测结果。
- 网关 API handler 当前采用轻量异步模式：`create_task` 返回 `queued`，由 `TaskWorker` 执行后写入结果。
- 支持租户授权范围约束：客户请求只能缩小后台安全人员录入的范围，不能扩大。
- 支持 uncover FOFA JSONL fixture 和 sidecar 命令客户端，POC 阶段只启用 FOFA。
- 支持测绘情报 freshness 标注，区分 `fresh`、`aging`、`stale`、`unknown`，但不把陈旧情报等同于资产已下线。
- 支持网关 API 活动审计，覆盖范围查看、任务请求、范围拒绝、任务排队、worker 执行和结果拉取。
- 支持网关短期留存策略基线：任务元数据 180 天、结果快照 90 天、审计日志 365 天。
- 支持无框架 HTTP adapter，验证签名鉴权、路由、异步任务创建和分页结果拉取语义，后续可接入 FastAPI、Flask 或企业网关。

安全工具箱 API 契约见：

- `docs/resource-discovery/toolbox-api-contract.md`
- `docs/resource-discovery/toolbox-handoff.md`
- `docs/resource-discovery/production-readiness-checklist.md`

## 专业被动 EASM 工作流

当前网关边界保持不变：云端只做授权范围内的被动发现、证据归一化、短期结果和审计；长期资产库、本地探活、漏洞验证、弱口令检查、处置闭环和报告归档仍由安全工具箱负责。

推荐工具箱团队按三步联调：

1. 使用 `discovery_strategy="baseline"` 打通基本链路。
   - 适合低配额、首次联调和普通客户。
   - 只生成基础被动查询，例如根域名、组织名和 IP 段。
   - 返回结果包含 `assets`、`services`、`source_evidence`、`ownership_confidence` 和 `freshness`。

2. 使用 `discovery_strategy="easm"` 做更完整的被动发现。
   - 仍然不执行云端主动扫描或漏洞验证。
   - 会在授权范围内生成更多 FOFA 查询计划，例如 `domain`、`host` 后缀、`cert.domain`、`cert.subject.org`、`title` 和 `org`。
   - 可能因为租户 `max_queries_per_task` 不足被拒绝，此时工具箱应提示缩小范围或回退 `baseline`。

3. 在工具箱本地消费结果。
   - `ownership_confidence` 只表示归属置信度，不是最终资产确认。
   - `freshness` 只表示外部测绘平台观测时间，不表示当前在线状态。
   - `source_evidence.evidence` 可能包含 `server`、`product`、`version`、`asn`、`org`、`cname`、`header_hash`、`banner_hash` 等复核字段。
   - 新增或消失的资产/服务应写成“本次外部测绘是否观察到”，不要直接写成“上线”或“下线”。
   - 本仓库提供 `compare_snapshots(before, after)` 作为第一版 ID 级变更检测工具。

网关 API 请求示例：

```json
{
  "profile_id": "scope_profile_001",
  "requested_scope": {
    "root_domains": ["example.com"]
  },
  "engines": ["fofa"],
  "discovery_strategy": "easm",
  "result_limit": 100,
  "purpose": "toolbox_asset_discovery"
}
```

常见策略错误：

- `invalid_discovery_strategy`：策略不是 `baseline` 或 `easm`。
- `query_plan_budget_exceeded`：策略展开后的查询数超过租户 `max_queries_per_task`。

## 本地运行

创建虚拟环境并安装测试依赖：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

如果系统没有可用 `python`，可使用 Codex 工作区自带 Python 路径创建 `.venv`。

从另一台电脑继续工作：

```powershell
git clone git@github.com:davidliao404/security-toolbox-resource-discovery.git
cd security-toolbox-resource-discovery
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q
```

仓库包含 GitHub Actions CI，推送到 `master` 或创建 PR 时会自动运行 `python -m pytest -q`。

运行测试：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

## 工具箱联调交付版

安装联调依赖：

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

启动 HTTP 服务：

```powershell
.\.venv\Scripts\python.exe -m uvicorn resource_discovery.http_app:app --host 127.0.0.1 --port 8000
```

单独运行一轮 worker：

```powershell
.\.venv\Scripts\python.exe -m resource_discovery.worker_cli --sqlite-path artifacts\integration\resource-discovery.sqlite3
```

生成签名：

```powershell
$timestamp = "2026-05-22T10:00:00+00:00"
$nonce = "nonce-demo-001"
$signature = .\.venv\Scripts\python.exe .\scripts\sign_request.py --secret local-dev-secret --method GET --path /api/v1/discovery/scope-profile --timestamp $timestamp --nonce $nonce
```


使用 docker compose 启动 API 与 worker：

```powershell
Copy-Item .\config\client-secrets.example.json .\config\client-secrets.json
# 如需修改联调密钥，编辑 config\client-secrets.json，并同步签名脚本里的 --secret 参数。
docker compose up --build
```

compose 默认使用：

- SQLite volume：`discovery-data:/data/resource-discovery.sqlite3`
- 客户端密钥配置：`config/client-secrets.example.json` 挂载为容器内 `/app/config/client-secrets.json`
- API：`http://127.0.0.1:8000`
- worker：循环消费同一个 SQLite 队列表

查询授权范围：

```powershell
curl.exe http://127.0.0.1:8000/api/v1/discovery/scope-profile `
  -H "X-Tenant-Id: tenant_poc" `
  -H "X-Client-Id: toolbox" `
  -H "X-Timestamp: $timestamp" `
  -H "X-Nonce: $nonce" `
  -H "X-Signature: $signature"
```

运行离线 PoC：

```powershell
.\.venv\Scripts\python.exe -m resource_discovery.cli --seeds examples\seeds.json --fixture tests\fixtures\fofa_results.json
```

只查看将要执行的受控查询计划，不调用任何外部 API：

```powershell
.\.venv\Scripts\python.exe -m resource_discovery.cli --mode dry-run --seeds examples\seeds.json
```

真实 FOFA 调用被默认禁用。后续需要真实调用时，必须同时提供凭据和显式开关：

```powershell
.\.venv\Scripts\python.exe -m resource_discovery.cli --mode live --seeds examples\seeds.json --fofa-email <email> --fofa-key <key> --allow-live-fofa
```

不要对未授权目标运行 live mode。

使用 FOFA 兼容中转站时，可以只使用 API Key，并通过环境变量配置：

```powershell
$env:FOFA_API_KEY = "<key>"
$env:FOFA_BASE_URL = "http://fofa.icu/api/v1/search/all"
.\.venv\Scripts\python.exe -m resource_discovery.cli --mode live --seeds .\artifacts\authorized-seeds.json --allow-live-fofa --page-limit 1 --result-limit 20 --save-dir .\artifacts\snapshots --audit-log .\artifacts\audit.jsonl
```

`artifacts/` 已被 Git 忽略，用于保存真实查询快照、报告和审计日志。

FOFA client 默认显式使用 `full=false`，即只查询供应商默认的一年内数据；如果未来要启用 `full=true` 搜索全部历史数据，应先评估费用、配额和陈旧情报占比。

运行受控 live 验证脚本：

```powershell
$env:FOFA_API_KEY = "<key>"
$env:FOFA_BASE_URL = "http://fofa.icu/api/v1/search/all"
.\.venv\Scripts\python.exe .\scripts\live_fofa_validation.py --domain china-entercom.com --page-limit 1 --result-limit 20
```

脚本只输出摘要，不打印 API Key；真实种子和完整查询快照会写入 `artifacts/live-validation/`。

命令会向 stdout 输出 JSON，其中包含：

- `task`
- `report`
- `assets`
- `services`
- `risk_hints`
- `remediation`
- `source_evidence`
- `analysis`
- `snapshot`

当某个供应商查询失败但其他查询成功时，执行结果会降级为 `partial_success`，保留已获取结果并在 `task.errors` 中记录失败来源、查询类型和错误信息。

## 风险分析模式

默认模式是规则库分析：

```powershell
.\.venv\Scripts\python.exe -m resource_discovery.cli --seeds examples\seeds.json --fixture tests\fixtures\fofa_results.json --analysis-mode rules_only
```

`rules_only` 不会向第三方大模型发送资产、域名、标题、组件或风险线索。报告会显示“分析来源”，审计日志会记录 `analysis_mode`、`llm_enabled`、`web_search_enabled` 和 `data_sharing_level`。

`rules_plus_llm` 已作为代码扩展点存在，用于后续接入客户显式授权的大模型 API Key。当前 PoC 尚未内置真实大模型供应商连接器；如果没有显式注入 `llm_enricher`，执行会拒绝继续，避免误把敏感暴露面数据发给第三方。

也可以使用租户级 JSON 配置统一控制分析模式。配置文件会覆盖命令行上的 `--analysis-mode`、`--web-search-enabled` 和 `--data-sharing-level`：

```powershell
.\.venv\Scripts\python.exe -m resource_discovery.cli --seeds examples\seeds.json --fixture tests\fixtures\fofa_results.json --tenant-analysis-config examples\tenant_analysis_rules_only.json
```

示例文件：

- `examples/tenant_analysis_rules_only.json`：默认规则库模式。
- `examples/tenant_analysis_llm.example.json`：LLM 增强配置样例，不包含 API Key，包含授权记录字段；当前需要上层服务显式注入模型增强器后才能运行。

预设提示语模板已放在 `src/resource_discovery/prompt_templates.py`，设计说明见 `docs/resource-discovery/llm-prompt-templates.md`。模板只接收最小化上下文，要求模型输出结构化 JSON，并明确禁止宣称漏洞已确认或生成攻击步骤。
模型增强结果会在进入报告前做安全校验：置信度调整限制在 `-0.2` 到 `0.2`，未知风险 ID 会被忽略，摘要会截断到 200 字以内。
如果未来模型连接器返回 token 和费用估算，`analysis.usage` 与 `llm_analysis_used` 审计事件会保留清洗后的 `prompt_tokens`、`completion_tokens`、`total_tokens` 和 `estimated_cost_usd`。

大模型增强路径的当前约束：

- 默认关闭，必须显式启用。
- 启用时必须存在未撤销的客户授权记录。
- 默认不发送原始 SaaS 响应。
- 最小化上下文只保留风险类别、严重级别、端口、服务和哈希化资产标识。
- 大模型只能给出置信度调整建议和外部上下文摘要，不能把被动线索改写为“已确认漏洞”。
- 报告中会区分规则置信度和增强后置信度。

保存任务快照：

```powershell
.\.venv\Scripts\python.exe -m resource_discovery.cli --seeds examples\seeds.json --fixture tests\fixtures\fofa_results.json --save-dir .\artifacts\snapshots
```

列出某个租户的快照摘要：

```powershell
.\.venv\Scripts\python.exe -m resource_discovery.cli --seeds examples\seeds.json --list-snapshots --tenant-id tenant_poc --save-dir .\artifacts\snapshots
```

读取某个任务快照：

```powershell
.\.venv\Scripts\python.exe -m resource_discovery.cli --seeds examples\seeds.json --show-snapshot dt_poc_001 --tenant-id tenant_poc --save-dir .\artifacts\snapshots
```

导出管理者可读报告：

```powershell
.\.venv\Scripts\python.exe -m resource_discovery.cli --seeds examples\seeds.json --fixture tests\fixtures\fofa_results.json --export-report .\artifacts\reports\dt_poc_001.md --report-format markdown
```

也可以导出 HTML：

```powershell
.\.venv\Scripts\python.exe -m resource_discovery.cli --seeds examples\seeds.json --fixture tests\fixtures\fofa_results.json --export-report .\artifacts\reports\dt_poc_001.html --report-format html
```

记录 JSONL 审计日志：

```powershell
.\.venv\Scripts\python.exe -m resource_discovery.cli --seeds examples\seeds.json --fixture tests\fixtures\fofa_results.json --save-dir .\artifacts\snapshots --export-report .\artifacts\reports\dt_poc_001.md --audit-log .\artifacts\audit.jsonl
```

## 安全边界

当前 PoC 默认只使用 fixture 数据，不调用真实 FOFA API，不保存 SaaS 密钥，不执行端口扫描、漏洞验证、弱口令验证或渗透测试。live 模式必须显式传入凭据、FOFA 兼容中转站地址和 `--allow-live-fofa`，并且只能用于已授权目标。所有风险项均为被动发现线索，需要在客户私有化安全工具箱内进行本地验证。

风险规则说明：

- 默认规则文件：`src/resource_discovery/risk_rules.yml`
- 当前规则覆盖远程访问入口、管理后台、测试环境、数据库/检索服务暴露、中间件/运维服务暴露。
- 规则只生成被动风险线索，不确认漏洞存在。
- 调整规则后运行 `.\.venv\Scripts\python.exe -m pytest -q` 验证报告和整改优先级未被破坏。

默认安全护栏：

- 每个输入种子必须提供 `authorization_note`。
- 单次任务最多 20 个种子。
- IPv4 CIDR 默认不得宽于 `/24`。
- 单次任务默认最多 30 个查询页。
- 单个查询计划默认最多 1000 条结果。
- FOFA API 客户端在缺少 email 或 key 时会直接拒绝构造，不会尝试联网。
- `live` 模式必须显式传入 `--allow-live-fofa`，否则会在执行前停止。
- `rules_plus_llm` 模式必须显式注入大模型增强器；当前 CLI 不内置真实供应商调用。
- 快照存储按 `tenant_id/task_id.json` 写入，并拒绝包含路径穿越字符的不安全标识。
- HTML 报告会对内容做转义，避免把发现结果中的标题或服务字段当作 HTML 执行。
- 审计日志采用 JSONL 追加写入，记录任务开始、快照保存、任务完成和报告导出事件。
- FOFA 兼容中转站支持 key-only 鉴权，不需要把 API Key 写入仓库。
