# 互联网暴露面资源发现 PoC 交付指南

## 1. 当前交付范围

当前仓库已经完成从设计到可执行 PoC 的闭环：

- 第一阶段需求、架构、数据模型、安全合规和 PoC 计划文档。
- 离线 FOFA-like fixture 数据链路。
- 受控查询规划和安全护栏。
- dry-run、fixture、live 三种执行模式隔离。
- 任务状态、部分成功、错误列表、配额记录和报告快照。
- 本地 JSON 快照保存、列出和读取。
- 管理者可读 Markdown/HTML 报告导出。
- JSONL 审计日志。
- 风险线索整改优先级。
- YAML 风险规则库。
- 双轨风险分析接口：默认规则库，可选大模型增强扩展点。

当前默认不调用真实 FOFA API，不需要 SaaS 密钥。

## 2. 快速开始

```powershell
git clone git@github.com:davidliao404/security-toolbox-resource-discovery.git
cd security-toolbox-resource-discovery
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q
```

如果系统没有可用 `python`，可使用 Codex 工作区自带 Python 创建 `.venv`。

仓库已配置 GitHub Actions CI。推送到 `master` 或创建 Pull Request 时，CI 会安装开发依赖并执行完整 pytest 测试。

## 3. 运行离线 PoC

```powershell
.\.venv\Scripts\python.exe -m resource_discovery.cli `
  --seeds examples\seeds.json `
  --fixture tests\fixtures\fofa_results.json
```

预期输出包含：

- `task.status = success`
- `report`
- `assets`
- `services`
- `risk_hints`
- `remediation`
- `source_evidence`
- `analysis`
- `snapshot`

## 4. 查看查询计划

dry-run 不调用外部 API，只输出受控 FOFA 查询计划：

```powershell
.\.venv\Scripts\python.exe -m resource_discovery.cli `
  --mode dry-run `
  --seeds examples\seeds.json
```

## 5. 保存和读取快照

保存任务快照：

```powershell
.\.venv\Scripts\python.exe -m resource_discovery.cli `
  --seeds examples\seeds.json `
  --fixture tests\fixtures\fofa_results.json `
  --save-dir .\artifacts\snapshots
```

列出快照：

```powershell
.\.venv\Scripts\python.exe -m resource_discovery.cli `
  --seeds examples\seeds.json `
  --list-snapshots `
  --tenant-id tenant_poc `
  --save-dir .\artifacts\snapshots
```

读取快照：

```powershell
.\.venv\Scripts\python.exe -m resource_discovery.cli `
  --seeds examples\seeds.json `
  --show-snapshot dt_poc_001 `
  --tenant-id tenant_poc `
  --save-dir .\artifacts\snapshots
```

## 6. 导出管理者报告

导出 Markdown：

```powershell
.\.venv\Scripts\python.exe -m resource_discovery.cli `
  --seeds examples\seeds.json `
  --fixture tests\fixtures\fofa_results.json `
  --export-report .\artifacts\reports\dt_poc_001.md `
  --report-format markdown
```

导出 HTML：

```powershell
.\.venv\Scripts\python.exe -m resource_discovery.cli `
  --seeds examples\seeds.json `
  --fixture tests\fixtures\fofa_results.json `
  --export-report .\artifacts\reports\dt_poc_001.html `
  --report-format html
```

## 7. 审计日志

```powershell
.\.venv\Scripts\python.exe -m resource_discovery.cli `
  --seeds examples\seeds.json `
  --fixture tests\fixtures\fofa_results.json `
  --save-dir .\artifacts\snapshots `
  --export-report .\artifacts\reports\dt_poc_001.md `
  --audit-log .\artifacts\audit.jsonl
```

审计日志记录：

- `task_started`
- `snapshot_saved`
- `task_completed`
- `report_exported`

任务完成事件会记录分析模式字段：

- `analysis_mode`
- `llm_enabled`
- `web_search_enabled`
- `data_sharing_level`

## 8. 风险分析模式

默认模式：

```powershell
.\.venv\Scripts\python.exe -m resource_discovery.cli `
  --seeds examples\seeds.json `
  --fixture tests\fixtures\fofa_results.json `
  --analysis-mode rules_only
```

`rules_only` 仅使用 `src/resource_discovery/risk_rules.yml`，不向第三方大模型发送任何发现结果。

可选增强模式：

```text
rules_plus_llm
```

当前 PoC 已保留 `rules_plus_llm` 代码接口，但尚未内置真实大模型供应商连接器。该模式必须由上层服务显式注入 `llm_enricher` 后才能运行；否则会拒绝执行。这样做是为了防止在没有客户授权、没有模型供应商配置、没有费用和合规边界时误发数据。

租户级配置文件可以统一控制分析模式：

```powershell
.\.venv\Scripts\python.exe -m resource_discovery.cli `
  --seeds examples\seeds.json `
  --fixture tests\fixtures\fofa_results.json `
  --tenant-analysis-config examples\tenant_analysis_rules_only.json
```

配置文件字段：

- `tenant_id`：必须与任务中的租户一致。
- `llm_enabled`：默认关闭；关闭时强制 `rules_only`。
- `llm_provider`：启用 LLM 时必须提供，例如 `openai`。
- `llm_model`：启用 LLM 时必须提供，例如 `gpt-5.5`。
- `web_search_enabled`：是否允许模型侧网络搜索。
- `data_sharing_level`：当前只允许 `none` 或 `minimal`；启用 LLM 时必须是 `minimal`。

示例文件：

- `examples/tenant_analysis_rules_only.json`
- `examples/tenant_analysis_llm.example.json`

预设提示语模板：

- `render_risk_confidence_prompt(context)`
- `render_manager_summary_prompt(context)`
- `render_remediation_prompt(context)`

模板实现位于 `src/resource_discovery/prompt_templates.py`，设计说明见 `docs/resource-discovery/llm-prompt-templates.md`。

增强模式的最小化上下文包含：

- 风险线索 ID。
- 风险类别和严重级别。
- 规则置信度。
- 端口和服务。
- 哈希化资产标识。

增强模式默认不包含：

- 原始 FOFA/中转站响应。
- 明文域名或 IP。
- 客户内部备注。
- SaaS API Key。
- 本地扫描或验证结果。

报告会显示“分析来源”，并在有增强结果时显示“大模型补充”和“增强后置信度”。规则置信度不会被覆盖，大模型只提供额外解释和置信度调整建议。

## 9. 安全边界

当前 PoC 明确不做：

- 云端主动扫描。
- 云端漏洞验证。
- 云端弱口令验证。
- 云端渗透测试。
- 未授权目标查询。

默认安全护栏：

- 每个输入种子必须提供 `authorization_note`。
- 单次任务最多 20 个种子。
- IPv4 CIDR 默认不得宽于 `/24`。
- 单次任务默认最多 30 个查询页。
- 单个查询计划默认最多 1000 条结果。
- `live` 模式必须显式传入 `--allow-live-fofa`。
- 缺少 FOFA email/key 时不会构造真实 API 客户端。
- `rules_plus_llm` 必须显式注入大模型增强器，当前 CLI 不直接调用第三方模型。

## 10. 真实 FOFA 接入条件

进入真实 FOFA 调用前必须具备：

- 已授权的客户测试目标。
- FOFA API email 和 key。
- 明确任务区域和数据处理边界。
- 明确配额上限。
- 明确是否允许保存真实查询快照。

真实调用命令模板：

```powershell
.\.venv\Scripts\python.exe -m resource_discovery.cli `
  --mode live `
  --seeds .\authorized-seeds.json `
  --fofa-email <email> `
  --fofa-key <key> `
  --allow-live-fofa `
  --save-dir .\artifacts\snapshots `
  --audit-log .\artifacts\audit.jsonl
```

如果使用 FOFA 兼容中转站，可使用 key-only 配置：

```powershell
$env:FOFA_API_KEY = "<key>"
$env:FOFA_BASE_URL = "http://fofa.icu/api/v1/search/all"
.\.venv\Scripts\python.exe -m resource_discovery.cli `
  --mode live `
  --seeds .\artifacts\authorized-seeds.json `
  --allow-live-fofa `
  --page-limit 1 `
  --result-limit 20 `
  --save-dir .\artifacts\snapshots `
  --export-report .\artifacts\reports\authorized-domain.md `
  --audit-log .\artifacts\audit.jsonl
```

真实查询产生的 `artifacts/` 内容默认不提交到 Git。

## 11. 当前验证命令

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

当前完整测试覆盖：

- 查询规划。
- 安全护栏。
- FOFA API 适配器。
- fixture 数据源。
- 归一化。
- 去重。
- 风险线索。
- 整改优先级。
- YAML 风险规则加载。
- 报告构建。
- Markdown/HTML 渲染。
- CLI 执行模式。
- 快照存储。
- 审计日志。
- 风险分析模式。
- 大模型增强扩展点的数据最小化。

## 12. 后续优化 TODO

后续优化集中记录在 `docs/resource-discovery/todo.md`。

当前重要 TODO：

- 为双轨风险分析补充真实大模型供应商连接器和费用/token 审计。

已完成：

- 将硬编码风险规则迁移为包内 `src/resource_discovery/risk_rules.yml`。
- 增加 `rules_only` / `rules_plus_llm` 分析模式接口。
- 报告和审计日志标识分析来源。
- 增加租户级分析配置文件加载与安全校验。
- 增加大模型增强提示语模板。
