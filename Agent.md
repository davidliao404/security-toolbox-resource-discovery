# Agent 接手指南

## 1. 项目定位

本仓库是“安全工具箱”的互联网暴露面资源发现模块 PoC。

当前目标是提供一个可被安全工具箱调用的资源发现网关能力：

```text
安全工具箱
-> 资源发现网关 API
-> 租户授权范围校验
-> FOFA / uncover 等外部测绘能力
-> 归一化、去重、freshness 标注、风险线索
-> 安全工具箱异步查询结果
```

网关不是主动扫描器，不做云端漏洞验证、不做渗透测试、不替代客户本地安全工具箱。安全工具箱仍是客户本地的验证、巡检、处置和长期资产库中心。

## 2. 当前能力状态

已具备的 PoC 主链路：

- 受控 FOFA 查询计划生成。
- fixture、原生 FOFA fallback、uncover JSONL / sidecar 适配。
- 租户授权范围模型 `TenantScopeProfile`。
- 客户请求范围只能缩小后台配置，不能扩大。
- 异步任务 API handler：创建任务、查询状态、分页拉取结果。
- 无框架 HTTP adapter：签名鉴权、路由、任务创建、结果分页。
- 文件型 task/result/scope profile repository。
- 结果按 `assets`、`services`、`source_evidence` 分类型分页。
- `fresh`、`aging`、`stale`、`unknown` freshness 标注。
- 风险规则库 `risk_rules.yml`。
- 可选 LLM 增强分析接口，默认关闭。
- HMAC-SHA256 请求签名、时间窗校验、nonce 防重放基础库。
- 网关审计事件和短期留存策略。
- live FOFA 兼容中转站验证脚本。

重要文档：

- `README.md`
- `docs/resource-discovery/toolbox-api-contract.md`
- `docs/resource-discovery/toolbox-handoff.md`
- `docs/resource-discovery/production-readiness-checklist.md`
- `docs/resource-discovery/security-compliance.md`
- `docs/resource-discovery/uncover-gateway-api-poc-plan.md`

## 3. 绝对安全边界

必须遵守：

- 不提交任何 FOFA Key、API Key、token、客户凭据。
- 不对未授权目标运行 live mode。
- 不把 `stale` 解释为资产已下线。
- 不把被动发现线索写成漏洞已确认。
- 不允许工具箱提交原生 FOFA 查询语句。
- 不做云端主动端口扫描、漏洞验证、弱口令验证、目录爆破或攻击链验证。
- 不把网关做成客户长期资产库；长期资产和处置记录应回到安全工具箱本地。
- `artifacts/` 是真实快照和本地验证输出目录，已被 Git 忽略，不要强行纳入版本库。

live 验证只允许使用客户已授权范围，例如当前测试域名 `china-entercom.com`。不要在文档或日志中打印真实 API Key。

## 4. 本地环境

推荐命令：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q
```

如果 `.venv` 已存在，直接运行：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

运行离线 PoC：

```powershell
.\.venv\Scripts\python.exe -m resource_discovery.cli --seeds examples\seeds.json --fixture tests\fixtures\fofa_results.json
```

查看 dry-run 查询计划：

```powershell
.\.venv\Scripts\python.exe -m resource_discovery.cli --mode dry-run --seeds examples\seeds.json
```

live 验证脚本：

```powershell
$env:FOFA_API_KEY = "<key>"
$env:FOFA_BASE_URL = "http://fofa.icu/api/v1/search/all"
.\.venv\Scripts\python.exe .\scripts\live_fofa_validation.py --domain china-entercom.com --page-limit 1 --result-limit 20
```

脚本只应输出摘要；完整快照写入 `artifacts/live-validation/`。

## 5. 代码地图

核心模块：

- `src/resource_discovery/gateway_api.py`：网关 API handler。
- `src/resource_discovery/gateway_http.py`：无框架 HTTP adapter。
- `src/resource_discovery/request_auth.py`：HMAC 签名、时间窗、nonce 防重放。
- `src/resource_discovery/scope_guard.py`：租户范围校验。
- `src/resource_discovery/repositories.py`：task/result/scope profile repository。
- `src/resource_discovery/task_queue.py`：轻量内存队列。
- `src/resource_discovery/worker.py`：异步任务 worker。
- `src/resource_discovery/execution.py`：发现任务执行主链路。
- `src/resource_discovery/fofa_client.py`：原生 FOFA 兼容 client。
- `src/resource_discovery/uncover_client.py`：uncover JSONL 和 sidecar client。
- `src/resource_discovery/normalizer.py`：FOFA-like 行归一化。
- `src/resource_discovery/deduplicator.py`：资产和服务去重。
- `src/resource_discovery/freshness.py`：测绘情报更新时间语义。
- `src/resource_discovery/risk_hints.py`：风险线索生成。
- `src/resource_discovery/risk_rules.yml`：规则库。
- `src/resource_discovery/analysis.py`：规则 / LLM 双轨分析入口。
- `src/resource_discovery/retention.py`：留存与清理策略。
- `src/resource_discovery/audit.py`：审计事件和 JSONL logger。

示例与脚本：

- `examples/seeds.json`
- `examples/scope_profile.json`
- `examples/tenant_analysis_rules_only.json`
- `examples/tenant_analysis_llm.example.json`
- `scripts/live_fofa_validation.py`

## 6. 测试地图

常用测试：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

重点测试文件：

- `tests/test_gateway_api.py`
- `tests/test_gateway_http.py`
- `tests/test_request_auth.py`
- `tests/test_scope_guard.py`
- `tests/test_scope_profile_repository.py`
- `tests/test_repositories.py`
- `tests/test_worker.py`
- `tests/test_gateway_results_pagination.py`
- `tests/test_fofa_client.py`
- `tests/test_uncover_client.py`
- `tests/test_freshness.py`
- `tests/test_task_state.py`
- `tests/test_audit_log.py`
- `tests/test_retention.py`

新增行为应优先补测试，再改实现。失败时先定位根因，不要随机试改。

## 7. 开发规则

工作方式：

- 先读相关文档和测试，再改代码。
- 需求不明确时优先做保守假设，并在文档里记录。
- 任何新功能或 bugfix 先写测试。
- 文件编辑优先使用 patch，避免无关格式 churn。
- 每次改动后至少运行相关测试；重要节点运行全量测试。
- 提交前运行：

```powershell
git diff --check
.\.venv\Scripts\python.exe -m pytest -q
git status --short
```

密钥扫描建议：

```powershell
rg "FOFA_API_KEY|known_key_prefix|token|secret" . -g "!artifacts/**" -g "!*.pyc"
```

如果搜索到的是 README 中的占位符 `<key>` 或测试中的 `"secret"`，通常可以保留；真实密钥必须删除。

## 8. Git 约定

当前主分支是 `master`，远端是：

```text
git@github.com:davidliao404/security-toolbox-resource-discovery.git
```

建议小步提交，便于回滚。提交信息示例：

- `feat: add signed gateway http adapter`
- `fix: generate unique gateway task ids`
- `docs: add toolbox integration handoff`
- `chore: add live fofa validation script`

除非用户明确要求，不要重写历史，不要 `git reset --hard`，不要回滚用户未授权的改动。

## 9. 下一步优先级

从 PoC 走向第一版生产化，优先级建议如下：

1. 接入真实 HTTP 框架，例如 FastAPI，并复用 `GatewayHttpHandler` 的路由语义。
2. 替换内存队列为可靠队列，例如 Redis、RabbitMQ、SQS 或 Celery broker。
3. 替换文件 repository 为数据库 / 对象存储 repository。
4. 实现租户级配额、供应商级限速、worker 重试和死信队列。
5. 将签名鉴权接入真实 HTTP middleware，并接入客户端密钥管理。
6. 实现 scope profile 后台管理 API 和审批记录。
7. 接入集中审计、指标、日志、告警和留存清理定时任务。
8. 继续评估第二供应商，但 PoC 阶段仍以 FOFA 为主。

不建议过早做：

- 多供应商大规模扩展。
- 云端主动扫描。
- 云端漏洞验证。
- 自动攻击链验证。
- 复杂管理者报告迭代。

## 10. 术语提醒

- `lastupdatetime`：FOFA 或兼容供应商返回的最后更新时间，不是资产当前在线证明。
- `freshness.stale`：测绘情报陈旧，不代表资产已关停。
- `source_evidence`：证据链，应保留来源、查询、时间、置信度和归一化字段。
- `TenantScopeProfile`：安全人员根据客户访谈录入的授权范围，是工具箱请求的上限。
- `requested_scope`：工具箱用户发起任务时提交的缩小范围。
- `result_type`：结果分页类型，当前为 `assets`、`services`、`source_evidence`。

## 11. 完成前检查

给用户汇报前确认：

- 全量测试是否通过。
- 工作树是否干净或明确列出未提交文件。
- 是否已推送用户需要同步的提交。
- 是否有真实 Key 或快照被误加入 Git。
- 是否仍符合“不做云端主动扫描、不做未授权探测”的边界。
