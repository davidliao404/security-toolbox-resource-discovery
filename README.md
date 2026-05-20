# 安全工具箱互联网暴露面资源发现 PoC

这是“安全工具箱”互联网暴露面资源发现模块的第一版可执行 PoC。当前实现默认使用离线 fixture 数据，验证从资产种子到管理者报告草稿的最小链路，不需要 FOFA 密钥，也不会执行云端主动扫描。

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
- 支持租户授权范围约束：客户请求只能缩小后台安全人员录入的范围，不能扩大。
- 支持 uncover FOFA JSONL fixture 和 sidecar 命令客户端，POC 阶段只启用 FOFA。
- 支持测绘情报 freshness 标注，区分 `fresh`、`aging`、`stale`、`unknown`，但不把陈旧情报等同于资产已下线。

安全工具箱 API 契约见：

- `docs/resource-discovery/toolbox-api-contract.md`

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

当前 PoC 只使用 fixture 数据，不调用真实 FOFA API，不保存 SaaS 密钥，不执行端口扫描、漏洞验证、弱口令验证或渗透测试。所有风险项均为被动发现线索，需要在客户私有化安全工具箱内进行本地验证。

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
