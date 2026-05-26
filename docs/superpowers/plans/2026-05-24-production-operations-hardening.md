# 生产运维硬化实施计划

> **给 agentic worker 的要求：** 必须使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans` 按任务逐项实施。步骤使用 checkbox（`- [ ]`）跟踪。

**目标：** 在 2026-05-24 质量基线之后，补齐资源发现网关第一版生产运维控制能力。

**架构：** 保持现有 FastAPI 网关、repository 接口、PostgreSQL 表、Redis 队列和 ops CLI 边界。新增小而清晰的模块承载静态客户端密钥、范围审批、配额、任务操作、审计检索、留存清理和受控真实 FOFA 回归。

**技术栈：** Python 3.12、FastAPI、SQLAlchemy Core、PostgreSQL、Redis、pytest、coverage、Alembic、Docker Compose。

---

## 文件结构

- `src/resource_discovery/client_secrets.py`：静态客户端签名密钥记录、解析和轮换服务。
- `src/resource_discovery/postgres_store.py`：补充客户端密钥、配额 bucket、审计检索和留存策略 repository。
- `src/resource_discovery/quota.py`：租户任务配额和供应商查询配额判断逻辑。
- `src/resource_discovery/task_operations.py`：任务取消和死信队列运维辅助函数。
- `src/resource_discovery/ops_cli.py`：范围审批、密钥轮换、任务取消、死信查看、审计检索、留存清理和真实 FOFA 回归命令。
- `src/resource_discovery/http_app.py`：创建任务前执行配额校验，并返回结构化 429 错误。
- `src/resource_discovery/worker.py`：执行前识别已取消任务，补充任务完成、供应商错误和死信指标。
- `src/resource_discovery/metrics.py`：补充生产运维指标。
- `src/resource_discovery/live_validation.py`：受环境变量保护的真实 FOFA 回归入口。
- `tests/test_client_secrets.py`：客户端静态密钥和轮换测试。
- `tests/test_quota.py`：配额判断测试。
- `tests/test_task_operations.py`：任务取消和死信查看测试。
- `tests/test_ops_cli_production_ops.py`：生产运维 CLI 测试。
- `tests/test_production_audit_retention.py`：审计检索和留存清理测试。
- `tests/test_live_fofa_regression.py`：真实 FOFA 回归环境门禁和脱敏测试。
- `docs/resource-discovery/production-readiness-checklist.md`：只在测试通过后更新完成状态。

## 任务 1：客户端静态密钥管理与轮换

**文件：**
- 创建：`src/resource_discovery/client_secrets.py`
- 修改：`src/resource_discovery/postgres_store.py`
- 修改：`src/resource_discovery/ops_cli.py`
- 测试：`tests/test_client_secrets.py`
- 测试：`tests/test_ops_cli_production_ops.py`

- [x] **步骤 1：先写失败测试**

覆盖行为：

- `ClientSecretRotationService` 只解析 active 的 `tenant_id + client_id` 记录。
- `StaticSecretMaterialResolver` 使用静态 `secret_ref -> secret` 映射，不依赖 KMS/Vault。
- `PostgresClientSecretRepository` 只读取 active 记录。
- `rotate-client-secret` 只保存和打印 `secret_ref`，不接收明文 secret。

- [x] **步骤 2：运行测试确认失败**

运行：`.\.venv\Scripts\python.exe -m pytest tests/test_client_secrets.py tests/test_ops_cli_production_ops.py -q`

预期：因为模块和命令尚不存在而失败。

- [x] **步骤 3：实现静态密钥模块**

实现 `ClientSecretRecord`、`StaticSecretMaterialResolver` 和 `ClientSecretRotationService`。

- [x] **步骤 4：实现 PostgreSQL 仓储**

使用既有 `client_secrets` 表按 `(tenant_id, client_id)` upsert `secret_ref`，并只返回 active 记录。

- [x] **步骤 5：接入运维 CLI**

新增 `rotate-client-secret --database-url --tenant-id --client-id --secret-ref`。

- [x] **步骤 6：运行聚焦测试**

运行：`.\.venv\Scripts\python.exe -m pytest tests/test_client_secrets.py tests/test_ops_cli_production_ops.py tests/test_postgres_store.py -q`

当前结果：`19 passed, 1 skipped`。

## 任务 2：范围配置管理、审批和审计

**文件：**
- 修改：`src/resource_discovery/scope_guard.py`
- 修改：`src/resource_discovery/postgres_store.py`
- 修改：`src/resource_discovery/ops_cli.py`
- 测试：`tests/test_scope_profile_repository.py`
- 测试：`tests/test_ops_cli_production_ops.py`

- [x] **步骤 1：先写失败测试**

覆盖行为：

- scope profile 可携带 `approval` 字段。
- `approve-scope-profile` 会设置 `status=active`，写入 `approved_by`、`approved_at`、`ticket_id`。
- 审批命令写入 `scope_profile_approved` 审计事件。
- 审计详情不得包含完整授权范围。

- [x] **步骤 2：运行测试确认失败**

运行：`.\.venv\Scripts\python.exe -m pytest tests/test_scope_profile_repository.py tests/test_ops_cli_production_ops.py -q`

- [x] **步骤 3：实现 scope profile 审批字段和 CLI**

允许 `TenantScopeProfile` 保留 `approval` 字段；新增 `approve-scope-profile` 命令。

- [x] **步骤 4：运行聚焦测试**

运行：`.\.venv\Scripts\python.exe -m pytest tests/test_scope_profile_repository.py tests/test_ops_cli_production_ops.py -q`

## 任务 3：租户配额和供应商限速

**文件：**
- 创建：`src/resource_discovery/quota.py`
- 修改：`src/resource_discovery/postgres_store.py`
- 修改：`src/resource_discovery/http_app.py`
- 测试：`tests/test_quota.py`
- 测试：`tests/test_http_app.py`

- [x] **步骤 1：先写失败测试**

覆盖行为：

- 未超过日任务数、供应商查询数和并发数时允许创建任务。
- 超过租户日任务数返回 `tenant_daily_task_quota_exceeded`。
- 超过供应商查询日配额返回 `provider_daily_query_quota_exceeded`。
- 超过并发任务数返回 `tenant_concurrent_task_quota_exceeded`。
- FastAPI 创建任务超配额时返回 HTTP 429 和结构化错误。

- [x] **步骤 2：运行测试确认失败**

运行：`.\.venv\Scripts\python.exe -m pytest tests/test_quota.py tests/test_http_app.py -q`

- [x] **步骤 3：实现 `quota.py`**

实现 `TenantQuotaPolicy`、`QuotaDecision`、`QuotaExceeded` 和 `check_task_quota(...)`。

- [x] **步骤 4：实现 PostgreSQL bucket 仓储**

基于 `rate_limit_buckets` 表读写日级任务和供应商查询 bucket。

- [x] **步骤 5：接入 FastAPI**

在创建任务前执行可选配额校验；未配置配额仓储时保持现有联调行为。

- [x] **步骤 6：运行聚焦测试**

运行：`.\.venv\Scripts\python.exe -m pytest tests/test_quota.py tests/test_http_app.py tests/test_postgres_store.py -q`

## 任务 4：任务取消和死信队列运维

**文件：**
- 创建：`src/resource_discovery/task_operations.py`
- 修改：`src/resource_discovery/worker.py`
- 修改：`src/resource_discovery/ops_cli.py`
- 测试：`tests/test_task_operations.py`
- 测试：`tests/test_worker_retry.py`
- 测试：`tests/test_redis_queue.py`

- [x] **步骤 1：先写失败测试**

覆盖行为：

- `queued`、`retrying`、`running` 可取消为 `cancelled`。
- 终态任务不能取消，并返回结构化不可重试错误。
- dead letter 列表包含 `tenant_id`、`task_id`、`attempts`、`last_error`、`updated_at`。
- worker 执行前发现任务已取消时跳过供应商调用。

- [x] **步骤 2：运行测试确认失败**

运行：`.\.venv\Scripts\python.exe -m pytest tests/test_task_operations.py tests/test_worker_retry.py -q`

- [x] **步骤 3：实现任务操作模块**

实现 `cancel_task(...)` 和 `list_dead_letters(...)`。

- [x] **步骤 4：接入 worker 和 ops CLI**

新增 `cancel-task` 和 `list-dead-letters` 命令，worker 执行前识别取消状态。

- [x] **步骤 5：运行聚焦测试**

运行：`.\.venv\Scripts\python.exe -m pytest tests/test_task_operations.py tests/test_worker_retry.py tests/test_redis_queue.py tests/test_ops_cli_production_ops.py -q`

## 任务 5：审计检索、指标和留存清理

**文件：**
- 修改：`src/resource_discovery/postgres_store.py`
- 修改：`src/resource_discovery/metrics.py`
- 修改：`src/resource_discovery/ops_cli.py`
- 修改：`src/resource_discovery/http_app.py`
- 修改：`src/resource_discovery/worker.py`
- 测试：`tests/test_production_audit_retention.py`
- 测试：`tests/test_observability.py`

- [x] **步骤 1：先写失败测试**

覆盖行为：

- 审计检索必须按租户隔离，可按 event type 和 task_id 过滤。
- 留存清理只清理目标租户过期任务、结果、nonce，保留未过期审计。
- `/metrics` 暴露任务创建、任务完成、供应商错误、死信和配额拒绝计数器。

- [x] **步骤 2：运行测试确认失败**

运行：`.\.venv\Scripts\python.exe -m pytest tests/test_production_audit_retention.py tests/test_observability.py -q`

- [x] **步骤 3：实现 repository 和 CLI**

新增 `search_audit_events(...)`、`load_retention_policy(...)`、`cleanup_expired_rows(...)`、`search-audit` 和租户级 `cleanup-retention`。

- [x] **步骤 4：扩展指标**

补充 bounded-label 指标并接入 API/worker。

- [x] **步骤 5：运行聚焦测试**

运行：`.\.venv\Scripts\python.exe -m pytest tests/test_production_audit_retention.py tests/test_observability.py tests/test_ops_cli_production_ops.py -q`

## 任务 6：受控真实 FOFA 回归

**文件：**
- 修改：`src/resource_discovery/live_validation.py`
- 修改：`src/resource_discovery/ops_cli.py`
- 创建：`tests/test_live_fofa_regression.py`
- 修改：`docs/resource-discovery/production-readiness-checklist.md`

- [x] **步骤 1：先写失败测试**

覆盖行为：

- 未设置 `RESOURCE_DISCOVERY_LIVE_FOFA=1` 时拒绝运行。
- 缺少 `FOFA_EMAIL`、`FOFA_KEY` 或 `RESOURCE_DISCOVERY_LIVE_AUTHORIZED_DOMAIN` 时拒绝运行。
- 返回结果和日志摘要不得包含 `FOFA_KEY`。

- [x] **步骤 2：运行测试确认失败**

运行：`.\.venv\Scripts\python.exe -m pytest tests/test_live_fofa_regression.py -q`

- [x] **步骤 3：实现受控 runner 和 CLI**

新增 `run_live_fofa_regression(...)` 和 `live-fofa-regression` 命令。命令只从环境变量读取 FOFA 凭据。

- [x] **步骤 4：运行本地门禁测试**

运行：`.\.venv\Scripts\python.exe -m pytest tests/test_live_fofa_regression.py tests/test_live_validation.py -q`

- [x] **步骤 5：记录真实调用状态**

如果本地没有授权域名和真实 FOFA 凭据，在清单中记录 `not run`，不伪造结果。

## 最终验证

- [x] Windows 全量测试：`.\.venv\Scripts\python.exe -m pytest -q`，结果 `315 passed, 4 skipped in 4.58s`
- [x] 覆盖率门禁：`.\.venv\Scripts\python.exe -m coverage run -m pytest -q; .\.venv\Scripts\python.exe -m coverage report`，结果 `315 passed, 4 skipped`，总覆盖率 `98.32%`
- [x] WSL PostgreSQL/Redis：`RESOURCE_DISCOVERY_TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/resource_discovery RESOURCE_DISCOVERY_TEST_REDIS_URL=redis://localhost:6379/0 python -m pytest -q`，结果 `319 passed in 12.02s`
- [x] whitespace 检查：`git diff --check`
- [ ] 推送后确认 GitHub Actions `CI` 和 `production-like-gateway` 为绿色。
