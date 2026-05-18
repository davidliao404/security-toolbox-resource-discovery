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

## 本地运行

创建虚拟环境并安装测试依赖：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

如果系统没有可用 `python`，可使用 Codex 工作区自带 Python 路径创建 `.venv`。

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

命令会向 stdout 输出 JSON，其中包含：

- `task`
- `report`
- `assets`
- `services`
- `risk_hints`
- `remediation`
- `source_evidence`
- `snapshot`

当某个供应商查询失败但其他查询成功时，执行结果会降级为 `partial_success`，保留已获取结果并在 `task.errors` 中记录失败来源、查询类型和错误信息。

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

默认安全护栏：

- 每个输入种子必须提供 `authorization_note`。
- 单次任务最多 20 个种子。
- IPv4 CIDR 默认不得宽于 `/24`。
- 单次任务默认最多 30 个查询页。
- 单个查询计划默认最多 1000 条结果。
- FOFA API 客户端在缺少 email 或 key 时会直接拒绝构造，不会尝试联网。
- `live` 模式必须显式传入 `--allow-live-fofa`，否则会在执行前停止。
- 快照存储按 `tenant_id/task_id.json` 写入，并拒绝包含路径穿越字符的不安全标识。
- HTML 报告会对内容做转义，避免把发现结果中的标题或服务字段当作 HTML 执行。
- 审计日志采用 JSONL 追加写入，记录任务开始、快照保存、任务完成和报告导出事件。
