# 资源发现网关长期推进路线图

## 1. 当前状态

仓库已经完成：

- 第一阶段需求、架构、数据模型、安全合规和 PoC 文档。
- FOFA fixture / live 中转站验证。
- 原生 FOFA client fallback。
- uncover FOFA JSONL fixture 解析。
- uncover sidecar 命令客户端。
- 租户授权范围模型 `TenantScopeProfile`。
- 范围守卫 `ScopeGuard`，客户请求只能缩小后台配置范围。
- 面向安全工具箱的 API handler POC：
  - 查询范围配置。
  - 创建资产探测任务。
  - 查询任务状态。
  - 拉取资产探测结果。
- 任务快照 `FileTaskStore`。
- freshness 标注：`fresh`、`aging`、`stale`、`unknown`。
- 管理者报告、风险线索、整改建议保留为可选能力。
- 双轨分析和 LLM 增强扩展点，但当前不作为资产探测网关主路径。

当前最新验证：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

预期：`90 passed`。

## 2. 产品主线判断

资源发现网关的核心定位应是：

```text
安全工具箱的互联网资产探测任务服务
```

不是：

```text
长期资产库
管理者报告平台
漏洞验证平台
云端主动扫描平台
```

网关需要保存数据，但保存目的不同：

- 必须保存短期任务数据，支持异步查询、失败重试、审计和工具箱拉取结果。
- 不应保存长期客户资产主库。
- 工具箱应负责长期展示、确认、验证、处置和报告归档。

推荐边界：

```text
网关：短期任务持久化 + SaaS 聚合 + 结果归一化 + 审计 + 配额
工具箱：长期资产库 + 本地验证 + 处置闭环 + 用户展示
```

## 3. 异步策略

建议 API 契约按异步设计：

```text
POST /tasks -> 返回 task_id
GET /tasks/{task_id} -> 查询状态
GET /tasks/{task_id}/results -> 分页拉取结果
```

第一版实现采用轻量异步：

- 不立刻引入复杂消息队列。
- 用本地 worker / 线程 / 简单队列模拟异步。
- 存储抽象先做好，后续替换为数据库和队列。

保留同步执行仅用于开发调试：

- fixture。
- 小结果集。
- 单元测试。

正式工具箱对接主路径应是异步任务。

## 4. 长期阶段列表

### 阶段 1：API 契约冻结

目标：让工具箱团队可以开始按稳定契约对接。

范围：

- 明确四个 API：
  - `GET /api/v1/discovery/scope-profile`
  - `POST /api/v1/discovery/tasks`
  - `GET /api/v1/discovery/tasks/{task_id}`
  - `GET /api/v1/discovery/tasks/{task_id}/results`
- 明确字段命名、状态枚举、错误码、分页格式。
- 明确哪些字段工具箱需要长期保存。

输出：

- `docs/resource-discovery/toolbox-api-contract.md`
- API handler 测试继续覆盖契约。

验收：

- 工具箱团队不需要读 Python 代码也能知道如何对接。
- 所有 response 都是普通 JSON 类型，不包含 Python Enum。

### 阶段 2：任务持久化抽象

目标：把当前 `FileTaskStore` 升级为可替换的 repository 接口。

范围：

- 新增 `TaskRepository`。
- 新增 `ResultRepository`。
- 新增 `ScopeProfileRepository`。
- 保留文件实现：
  - `FileTaskRepository`
  - `FileResultRepository`
  - `FileScopeProfileRepository`

原则：

- POC 仍使用文件。
- 生产可替换为 PostgreSQL / MySQL / Redis / 对象存储。
- 不把真实 API Key 或客户密钥写入 repository。

验收：

- API handler 不直接依赖 `FileTaskStore`。
- 任务状态和结果可分别保存。
- 结果支持分页读取。

### 阶段 3：轻量异步执行器

目标：让 `POST /tasks` 不直接执行探测，而是创建任务并入队。

范围：

- 新增状态：
  - `queued`
  - `running`
  - `success`
  - `partial_success`
  - `failed`
  - `cancelled`
- 新增 `InMemoryTaskQueue`。
- 新增 `TaskWorker`。
- 新增执行锁，避免同一任务重复执行。
- 新增失败原因保存。

第一版行为：

```text
create_task()
-> 保存 queued task
-> 入队
-> worker 执行
-> 保存结果
```

验收：

- 创建任务立即返回 `queued`。
- worker 执行后状态变为 `success` 或 `partial_success`。
- 工具箱可在状态变化前后重复查询。

### 阶段 4：范围配置后台模型

目标：支持安全人员在网关后台录入客户授权范围。

范围：

- `TenantScopeProfile` 持久化。
- 后台配置字段：
  - 租户 ID。
  - 根域名。
  - 精确域名。
  - IP 段。
  - 组织名称。
  - 默认范围。
  - 允许引擎。
  - provider profile。
  - 配额。
  - 授权说明。
  - 安全人员操作者摘要。
- 后台操作审计。

暂不做复杂 UI：

- POC 可用 JSON 文件或 CLI 写入。
- 生产再接真实后台页面。

验收：

- 工具箱 API 只能读取摘要，不能读取 provider 密钥。
- 超范围请求稳定拒绝。

### 阶段 5：uncover sidecar 生产化

目标：把当前 fake runner / fixture 路径升级为可真实调用 uncover 的 sidecar。

范围：

- provider config 文件路径配置。
- uncover binary 路径配置。
- 命令超时。
- stderr 捕获。
- 非零退出码映射为任务错误。
- JSONL 行级解析失败隔离。
- 结果上限。
- 供应商来源字段保留。

安全要求：

- API Key 只存在本地 ignored provider config 或密钥系统。
- 命令日志不得输出 API Key。
- 不允许工具箱传入原生 FOFA 查询语句。

验收：

- 使用 fixture runner 的单元测试。
- 使用本地真实 uncover 的手工验证文档。
- 无 uncover 安装时测试仍可通过。

### 阶段 6：原生 FOFA fallback 加固

目标：在 uncover 不可用或中转站不兼容时，原生 FOFA client 仍能完成 POC。

范围：

- key-only 中转站支持继续保留。
- `lastupdatetime` 默认字段保留。
- `full=false` / `full=true` 策略文档化。
- 错误码和限速映射。
- 页面大小和页数上限。
- 结果字段兼容。

验收：

- 已授权域名真实验证。
- 结果 freshness 可用。
- 中转站返回异常时任务失败原因可读。

### 阶段 7：freshness 与复核语义

目标：明确测绘时间和资产当前可达性的区别。

范围：

- `fresh`：90 天内。
- `aging`：90 至 180 天。
- `stale`：超过 180 天。
- `unknown`：来源未返回时间。

原则：

- `stale` 不代表资产已下线。
- 网关不做云端主动探活。
- 工具箱可基于 `stale` 发起本地验证任务。

验收：

- 服务和证据中都有 freshness。
- API 文档明确 freshness 语义。
- 报告和工具箱结果不写“已关停”。

### 阶段 8：结果分页与大结果处理

目标：支持工具箱稳定拉取大结果集。

范围：

- cursor 分页。
- `limit` 上限。
- assets/services/source_evidence 分页策略。
- 可按类型拉取：
  - `?type=assets`
  - `?type=services`
  - `?type=evidence`
- 结果排序稳定。

验收：

- 1000 条结果不会一次性塞进响应。
- 重复请求同一个 cursor 结果稳定。
- 空结果有明确响应。

### 阶段 9：审计与配额

目标：让网关能回答“谁在什么时候查了什么范围，消耗了多少配额”。

范围：

- 审计事件：
  - 读取范围配置。
  - 创建任务。
  - ScopeGuard 拒绝。
  - 任务入队。
  - 任务开始。
  - 任务完成。
  - 任务失败。
  - 结果拉取。
- 配额字段：
  - planned_queries。
  - completed_queries。
  - failed_queries。
  - result_count。
  - provider。
  - engine。

验收：

- 审计日志不含 API Key。
- 超范围请求也有审计。
- 失败任务有错误原因。

### 阶段 10：错误模型与失败降级

目标：给工具箱稳定、可展示、可重试的错误结构。

错误类型：

- `scope_out_of_bounds`
- `provider_auth_failed`
- `provider_rate_limited`
- `provider_timeout`
- `provider_bad_response`
- `normalization_failed`
- `task_cancelled`
- `internal_error`

验收：

- API 不返回 Python traceback。
- 工具箱可以根据 `error.code` 展示中文说明。
- 部分成功时保留已有结果。

### 阶段 11：真实 FOFA / uncover 验证流程

目标：把真实验证变成可重复流程，不靠临时命令记忆。

范围：

- `artifacts/` 继续 ignored。
- 示例脚本只读取环境变量。
- 不提交密钥。
- 输出验证摘要：
  - 资产数。
  - 服务数。
  - freshness 分布。
  - 错误数。
  - 快照路径。

验收：

- 新机器 clone 后可按 README 复现 fixture 测试。
- 有密钥时可复现 live 测试。
- 无密钥时不会失败全量测试。

### 阶段 12：工具箱对接包

目标：给工具箱团队一份明确的对接资料。

范围：

- API contract。
- 状态流转图。
- 错误码表。
- 请求/响应样例。
- 分页说明。
- freshness 说明。
- 字段长期保存建议。

验收：

- 工具箱团队能独立开发调用页。
- 工具箱不需要知道 FOFA/uncover 细节。

### 阶段 13：生产化存储

目标：从文件存储迁移到可部署存储。

建议：

- PostgreSQL / MySQL：任务、范围配置、审计、索引字段。
- 对象存储：大结果快照。
- Redis：短期队列和锁。

迁移原则：

- repository 接口先稳定。
- 文件实现保留用于本地开发。
- 不在同一阶段引入复杂 UI。

验收：

- 单元测试可跑文件实现。
- 集成测试可跑数据库实现。

### 阶段 14：多供应商扩展

目标：在 FOFA 稳定后扩展其他测绘平台。

候选顺序：

1. Hunter / 鹰图。
2. Quake。
3. ZoomEye。
4. DayDayMap。

原则：

- 每个供应商单独开关。
- 每个供应商单独配额。
- 每条 evidence 保留来源。
- 不混淆 provider observation time。

验收：

- 多供应商同一资产去重。
- 单供应商失败不影响其他供应商结果。

### 阶段 15：安全和合规评审

目标：进入试点客户前做一次边界审查。

检查项：

- 是否有云端主动扫描。
- 是否保存了不必要原始响应。
- 是否可能越权查询。
- 是否泄露 provider API Key。
- 是否有足够审计。
- 是否能删除任务结果。
- 是否能解释 freshness。

验收：

- 形成安全评审记录。
- 高风险项关闭后再进入试点。

## 5. 推荐近期执行顺序

最近 5 个迭代建议：

1. 写 `toolbox-api-contract.md`，冻结 API 字段。
2. 抽象 `TaskRepository` / `ResultRepository` / `ScopeProfileRepository`。
3. 实现轻量异步 `InMemoryTaskQueue` + `TaskWorker`。
4. 改造 `DiscoveryGatewayApi.create_task` 为 queued 模式。
5. 增加结果分页和错误码模型。

每个迭代都应：

- 先写失败测试。
- 最小实现。
- 跑完整 pytest。
- 小步 commit。
- push 到 GitHub。

## 6. 暂缓事项

以下事项暂缓，避免过早复杂化：

- 真实后台 UI。
- 数据库迁移。
- 多供应商并发。
- 云端主动探活。
- 漏洞验证。
- LLM 自动分析作为主路径。
- 报告模板扩展。

## 7. 关键决策点

后续需要你确认的点：

1. 生产存储选型：PostgreSQL / MySQL / 现有系统数据库。
2. 生产队列选型：Redis / 数据库轮询 / 云队列。
3. uncover 是否作为生产主路径，还是只做 POC。
4. FOFA `full=true` 是否允许，以及费用和数据范围策略。
5. 多供应商扩展顺序。
6. 网关任务结果默认留存时长。
