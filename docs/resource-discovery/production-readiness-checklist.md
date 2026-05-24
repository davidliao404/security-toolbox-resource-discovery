# 资源发现网关生产准备清单

## 1. 使用方式

本文用于把当前 PoC 推进到第一版生产可用前的评审。每一项建议在上线前由产品、安全、研发、运维和交付共同确认。

状态约定：

- `已完成`：已在代码、文档或流程中实现。
- `原型可用`：已有雏形，但不应直接按生产标准使用。
- `待补齐`：上线前必须补齐。
- `待决策`：需要业务或合规决策。

## 2. 总览

| 领域 | 当前状态 | 上线前要求 |
| --- | --- | --- |
| API 契约 | `已完成` | 与工具箱团队冻结字段和错误码 |
| 租户范围控制 | `原型可用` | 接入真实后台配置和审批记录 |
| 异步任务 | `原型可用` | 替换内存队列，支持重试和并发控制 |
| 结果持久化 | `原型可用` | 替换文件存储，使用数据库或对象存储 |
| 审计 | `原型可用` | 接入集中审计、权限检索和留存策略 |
| 留存策略 | `原型可用` | 接入定时清理任务和客户级策略 |
| FOFA/uncover | `原型可用` | 明确生产供应商配置、限速、重试和降级 |
| 鉴权签名 | `联调可用` | FastAPI 联调版已验签；生产需接入客户端密钥管理 |
| 运维观测 | `待补齐` | 增加指标、日志、告警和追踪 |
| 双区域合规 | `待决策` | 确认香港与内地区域部署边界 |

## 3. 鉴权与签名

- [x] 提供 HMAC-SHA256 签名、时间窗校验和 nonce 防重放基础库。
- [x] 防重放：nonce 在时间窗口内只能使用一次。
- [x] 请求体参与签名，避免中间层篡改范围和 `result_limit`。
- [x] 无框架 HTTP 适配器已接入签名校验和核心路由语义。
- [x] FastAPI 联调交付版已接入 HTTP 层签名校验。
- [ ] 客户端密钥按租户和工具箱实例隔离。
- [ ] 支持客户端密钥轮换。
- [ ] 鉴权失败不返回内部配置或签名计算细节。

## 4. 租户隔离

- [x] 任务、结果和审计事件包含 `tenant_id`。
- [x] 结果存储实现按租户目录隔离。
- [ ] 生产数据库表必须包含租户字段和索引。
- [ ] 所有查询必须带租户条件，禁止只按 `task_id` 查询。
- [ ] 管理后台跨租户访问必须使用单独权限和审计事件。
- [ ] 集成测试覆盖租户 A 无法读取租户 B 任务。

## 5. 授权范围控制

- [x] `TenantScopeProfile` 支持根域名、域名、IP 段、组织名、引擎和限额。
- [x] 客户请求只能缩小后台配置范围。
- [x] 越权范围返回 `scope_out_of_bounds`。
- [ ] 后台录入范围需要审批人、客户授权证明和有效期。
- [ ] 支持停用或版本化范围配置。
- [ ] 工具箱应在范围配置变更后重新拉取配置。

## 6. 供应商密钥管理

- [x] 工具箱不保存 FOFA API 密钥。
- [x] 真实调用验证脚本只从环境变量读取密钥。
- [ ] 生产环境使用云 KMS、Vault 或等效密钥服务。
- [ ] 密钥按区域、供应商、环境隔离。
- [ ] 密钥访问必须有审计。
- [ ] 错误日志不得输出密钥、认证头或完整签名串。
- [ ] 支持供应商密钥轮换和灰度验证。

## 7. 队列与任务执行

- [x] API 已采用异步 `queued` 模式。
- [x] PoC 工作进程可消费任务并写入结果。
- [x] 联调交付版提供 SQLite 队列和 Redis 队列适配器。
- [ ] 生产队列使用 Redis、RabbitMQ、SQS、Celery 消息代理或等效组件。
- [ ] 工作进程支持并发上限、租户级限流和供应商级限流。
- [ ] 任务重试策略区分可恢复错误和不可恢复错误。
- [ ] 支持任务取消。
- [ ] 支持任务超时和死信队列。
- [ ] 工作进程重启后不能丢任务。

## 8. 数据库与结果存储

- [x] PoC 文件存储已拆分任务元数据和结果数据。
- [x] 结果按 `assets`、`services`、`source_evidence` 类型分页。
- [x] 联调交付版提供 SQLite 任务、结果、范围、nonce 和审计持久化实现。
- [ ] 生产任务元数据表：任务状态、租户、范围配置、配额、错误、时间戳。
- [ ] 生产结果表或对象存储：资产、服务、证据分别存储。
- [ ] 对 `tenant_id + task_id`、`tenant_id + created_at` 建索引。
- [ ] 明确哪些字段加密存储。
- [ ] 结果导出和删除需要审计。

## 9. 留存与清理

- [x] 默认策略：任务元数据 180 天、结果快照 90 天、审计日志 365 天。
- [x] PoC 提供过期文件清理函数。
- [ ] 生产定时任务定期执行清理。
- [ ] 支持租户级留存策略。
- [ ] 清理动作写入审计。
- [ ] 删除客户数据前保留必要证明，但不保留完整结果。
- [ ] 停用租户后的清理和匿名化流程需单独确认。

## 10. 审计

- [x] 网关 API 审计范围查看、任务请求、拒绝、排队和结果拉取。
- [x] 工作进程审计任务开始、完成和失败。
- [ ] 审计日志接入集中日志或审计数据库。
- [ ] 审计日志支持按租户、任务、操作者和事件类型检索。
- [ ] 审计日志留存期和访问权限按合同配置。
- [ ] 管理后台修改密钥、配额、范围配置、留存策略必须审计。

## 11. 配额与限速

- [x] 范围配置包含 `max_results_per_task` 和 `max_queries_per_task`。
- [x] 本地安全护栏限制种子数量、CIDR 范围和查询页数。
- [ ] 实现租户级日配额、月配额和并发任务数。
- [ ] 实现供应商级速率限制。
- [ ] `provider_rate_limited` 应触发延迟重试，而不是立即失败。
- [ ] 管理后台展示配额消耗和即将耗尽提示。

## 12. 错误模型

- [x] 已定义 `ApiError` 和首批错误码。
- [x] 范围越权和范围配置不匹配返回结构化错误。
- [x] FOFA 原生错误映射到 `provider_auth_failed`、`provider_rate_limited`、`provider_timeout`、`provider_bad_response`。
- [x] uncover 边车进程超时、非零退出和异常 JSONL 已转换为可解释错误或可降级解析。
- [x] 执行层任务错误保留供应商标准 `code` 和 `recoverable` 标识。
- [ ] 工作进程失败时补充更完整的重试建议和调度策略。
- [ ] 对工具箱返回错误不包含供应商原始敏感响应。

## 13. 观测与告警

- [ ] 指标：任务创建数、成功率、失败率、平均耗时。
- [ ] 指标：供应商调用次数、错误率、限速次数、超时次数。
- [ ] 指标：队列长度、工作进程并发、任务等待时间。
- [ ] 日志：每个任务具备关联 ID。
- [ ] 告警：供应商认证失败、限速异常、失败率升高、队列堆积。
- [ ] 告警：租户异常范围请求和高频失败。

## 14. 双区域与合规

- [ ] 明确第一版生产部署区域：香港、内地，或先单区域。
- [ ] 香港客户数据不自动复制到内地区域。
- [ ] 内地客户任务默认在内地区域执行。
- [ ] 跨境 SaaS 调用需要显著提示和可配置禁用。
- [ ] 合同中明确供应商类别、处理区域、留存期限和删除流程。
- [ ] 香港客户关注个人资料最小化和保留期限。
- [ ] 内地客户关注数据出境、个人信息处理和等保相关控制。

## 15. 安全滥用防护

- [x] 客户请求不能超过后台授权范围。
- [x] 禁止云端主动扫描、漏洞验证、弱口令验证和攻击链验证。
- [ ] 后台支持暂停租户。
- [ ] 检测大量无关域名、大范围公网段和高频失败。
- [ ] 高风险关键词查询限制。
- [ ] 任务目的必填并进入审计。
- [ ] 可疑行为进入安全运营告警。

## 16. 灾备与恢复

- [ ] 任务队列可恢复，不因工作进程重启丢任务。
- [ ] 数据库定期备份。
- [ ] 审计日志不可被普通管理员静默删除。
- [ ] 供应商不可用时返回部分结果和清晰失败原因。
- [ ] 支持区域内故障转移或明确恢复时间目标。

## 17. 上线前最低门槛

第一版生产上线至少需要完成：

- HTTP API 层和签名鉴权。
- 持久化数据库或可靠对象存储。
- 可靠队列和工作进程重试策略。
- 生产级 FOFA/uncover 配置和错误映射。
- 租户级配额与供应商限速。
- 集中审计与留存清理。
- 工具箱端完成异步轮询和分页拉取。
- 明确部署区域和客户合同中的数据处理边界。

## 18. 当前结论

当前仓库已经具备“PoC 可验证”的主链路：范围约束、异步任务、工作进程执行、FOFA/uncover 固定样例数据、真实调用验证脚本、结果分页、新鲜度标注、审计和留存基线。

但它还不是生产部署件。下一步应优先建设 HTTP API 层、真实持久化、可靠队列、供应商错误映射和鉴权签名。

## 19. 生产上线准备版基线

- 日期：2026-05-23
- 分支：`codex/production-launch-ready-gateway`
- 基线提交：`f3f649d`
- Windows 环境说明：系统 PATH 中没有可用的 `pytest` 和 `py -m pytest`。安装项目开发依赖后，使用 Codex 自带 Python 环境执行验证。
- 基线修复：`f3f649d fix: preserve sqlite nonce replay window`。该修复让 SQLite nonce 清理逻辑与签名网关请求中的时间戳保持一致。
- 验证命令：`C:\Users\op827\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m pytest`
- 验证结果：`175 passed in 2.02s`

## 20. WSL 生产验证环境初始化

- 日期：2026-05-23
- 命令：`powershell -ExecutionPolicy Bypass -File scripts\wsl_bootstrap.ps1`
- 脚本行为：安装或选择 `Ubuntu-24.04`，从 WSL 进入仓库目录，安装 Docker Engine、Docker Compose 插件、PostgreSQL 客户端工具、Redis 工具、Python 3.12 和项目开发依赖，然后执行 Docker、Python 和 pytest 验证命令。
- 本地执行结果：启用 WSL2 所需 Windows 功能并重启主机后通过。
- WSL 发行版：`Ubuntu-24.04`，Ubuntu 24.04.4 LTS，WSL2。
- Docker 引擎：`Docker version 29.5.2`。
- Docker Compose：`Docker Compose version v5.1.4`。
- PostgreSQL 客户端：`psql (PostgreSQL) 16.14`。
- Redis 工具：`redis-cli 7.0.15`。
- Python：`Python 3.12.3`。
- WSL 初始化脚本中的 pytest 结果：`196 passed, 4 skipped in 8.25s`。
- 本地网络说明：当前网络路径会重置 Docker Hub 仓库服务直连请求。已在 WSL Docker 守护进程中配置可访问的镜像源，并保留标准本地镜像标签：`postgres:16`、`redis:7`、`python:3.12-slim`。

## 21. 类生产 CI 验证

- 工作流：`.github/workflows/prodlike.yml`
- 服务：PostgreSQL 16 和 Redis 7 服务容器。
- 验证内容：安装项目依赖，执行 Alembic 迁移，使用 PostgreSQL 和 Redis 集成地址运行完整 pytest 套件，并通过 `docker compose config` 校验 `docker-compose.prodlike.yml`。

## 22. 生产上线准备版验证记录 - 2026-05-23

- 分支：`codex/production-launch-ready-gateway`
- Windows 测试命令：`C:\Users\op827\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m pytest`
- Windows 测试结果：`196 passed, 4 skipped in 3.40s`
- WSL 测试命令：`python3.12 -m venv .venv-wsl && . .venv-wsl/bin/activate && python -m pip install -e '.[dev]' && python -m pytest -q`
- WSL 测试结果：`196 passed, 4 skipped in 9.28s`
- WSL 初始化命令：`powershell -ExecutionPolicy Bypass -File scripts\wsl_bootstrap.ps1`
- WSL 初始化结果：Docker 29.5.2、Compose v5.1.4、Python 3.12.3、pytest 9.0.3，`196 passed, 4 skipped in 8.25s`
- PostgreSQL/Redis 集成测试命令：`RESOURCE_DISCOVERY_DATABASE_URL=postgresql+psycopg://rd:rd@localhost:5432/rd RESOURCE_DISCOVERY_TEST_DATABASE_URL=postgresql+psycopg://rd:rd@localhost:5432/rd RESOURCE_DISCOVERY_TEST_REDIS_URL=redis://localhost:6379/0 python -m pytest tests/test_postgres_store.py tests/test_redis_queue.py tests/test_worker_retry.py -q`
- PostgreSQL/Redis 集成测试结果：`9 passed in 3.42s`
- Alembic 离线迁移命令：`python.exe -m alembic -c alembic.ini upgrade head --sql`
- Alembic 离线迁移结果：成功生成所有生产表和索引的 SQL。
- Compose 静态校验命令：`docker compose -p rd-prodlike -f docker-compose.prodlike.yml config`
- Compose 静态校验结果：在 WSL 内通过。
- 类生产 compose 启动命令：`docker compose -p rd-prodlike -f docker-compose.prodlike.yml up --build -d`
- 类生产 compose 启动结果：PostgreSQL 健康、Redis 健康、迁移完成、API 健康、工作进程已启动。
- 类生产冒烟测试命令：`python scripts/prodlike_smoke_test.py --base-url http://127.0.0.1:8000 --client-id toolbox --secret local-dev-secret`
- 类生产冒烟测试结果：`{"status": "success", "asset_count": 3}`。
- Compose 清理命令：`docker compose -p rd-prodlike -f docker-compose.prodlike.yml down -v`
- Compose 清理结果：容器、网络和 PostgreSQL 验证卷已删除。
- 路径兼容性说明：在 WSL 暴露的中文 Windows 路径下直接构建时，Docker Compose v5/BuildKit 会出现非 ASCII 项目名或会话错误。最终验证从 `/tmp/rd-prodlike-src` 执行，并显式指定 `-p rd-prodlike`，即使用 ASCII 项目目录和固定 compose 项目名完成验证。
- 敏感信息扫描命令：`rg -n "FOFA_API_KEY|local-dev-secret|secret-|token|api_key|password" . -g "!artifacts/**" -g "!.venv*/**" -g "!*.pyc" -g "!*.sqlite3"`
- 敏感信息扫描结果：通过。命中项均为占位符、示例客户端密钥、文档、测试数据、字段名和读取环境变量的代码；未发现真实供应商密钥或生产凭据。
