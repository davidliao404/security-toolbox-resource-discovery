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

## 8. 安全边界

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

## 9. 真实 FOFA 接入条件

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

## 10. 当前验证命令

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
- 报告构建。
- Markdown/HTML 渲染。
- CLI 执行模式。
- 快照存储。
- 审计日志。
